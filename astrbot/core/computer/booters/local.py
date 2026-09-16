from __future__ import annotations

import asyncio
import fnmatch
import locale
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from _thread import LockType
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, cast

from astrbot import logger
from astrbot.core.computer.file_read_utils import (
    detect_text_encoding,
    read_local_text_range_sync,
)
from astrbot.core.computer.local_file_security import read_fd_at
from astrbot.core.computer.process_sandbox import (
    SandboxProcess,
    SandboxSpec,
    SandboxTimeoutError,
    create_process_sandbox,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_root,
    get_astrbot_system_tmp_path,
)

from ..olayer import FileSystemComponent, PythonComponent, ShellComponent
from .base import ComputerBooter
from .shipyard_search_file_util import _truncate_long_lines

_BLOCKED_COMMAND_PATTERNS = [
    re.compile(r"(^|[;&|() ])rm(?:\.exe)?\s+-[a-z-]*r[a-z-]*(?:\s|$)"),
    re.compile(r"(^|[;&|() ])mkfs(?:\.[a-z0-9_+-]+)?(?:\s|$)"),
    re.compile(r"(^|[;&|() ])dd\s+if="),
    re.compile(r"(^|[;&|() ])(?:shutdown|reboot|poweroff|halt)(?:\s|$)"),
    re.compile(r"(^|[;&|() ])sudo(?:\s|$)"),
    re.compile(r"(^|[;&|() ])kill\s+-9(?:\s|$)"),
    re.compile(r"(^|[;&|() ])killall(?:\s|$)"),
]
_LOCAL_SANDBOX_MAX_OUTPUT_BYTES = 10 * 1024 * 1024


def _is_safe_command(command: str) -> bool:
    normalized_command = re.sub(r"\s+", " ", command.strip().lower())
    if ":(){:|:&};:" in normalized_command:
        return False
    return not any(
        pattern.search(normalized_command) for pattern in _BLOCKED_COMMAND_PATTERNS
    )


def resolve_windows_shell() -> str:
    """Resolve PowerShell 7 when available, with the inbox fallback."""
    for candidate in ("pwsh", "powershell.exe"):
        try:
            resolved = shutil.which(candidate)
        except AttributeError, OSError:
            resolved = None
        if resolved:
            return resolved
    return "powershell.exe"


def _decode_bytes_with_fallback(
    output: bytes | str | None,
    *,
    preferred_encoding: str | None = None,
) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output

    preferred = locale.getpreferredencoding(False) or "utf-8"
    attempted_encodings: list[str] = []

    def _try_decode(encoding: str) -> str | None:
        normalized = encoding.lower()
        if normalized in attempted_encodings:
            return None
        attempted_encodings.append(normalized)
        try:
            return output.decode(encoding)
        except LookupError, UnicodeDecodeError:
            return None

    for encoding in filter(None, [preferred_encoding, "utf-8", "utf-8-sig"]):
        if decoded := _try_decode(encoding):
            return decoded

    if os.name == "nt":
        # Native commands use the Windows system code page. Python children
        # are forced to UTF-8 by the callers above, so prefer the system code
        # page here instead of guessing GBK for every non-UTF-8 byte sequence.
        for encoding in (preferred, "mbcs", "cp936", "gbk", "gb18030"):
            if decoded := _try_decode(encoding):
                return decoded
    elif decoded := _try_decode(preferred):
        return decoded

    return output.decode("utf-8", errors="replace")


def _decode_shell_output(output: bytes | str | None) -> str:
    # Normalize CRLF so tool text output is identical across platforms.
    return _decode_bytes_with_fallback(output, preferred_encoding="utf-8").replace(
        "\r\n", "\n"
    )


def _signal_asyncio_process(
    process: asyncio.subprocess.Process, *, terminate: bool
) -> None:
    """Signal an asyncio subprocess, ignoring processes that already exited."""
    if process.returncode is not None:
        return
    try:
        if terminate:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        return


def _signal_posix_process_group(pid: int, sig: int) -> bool:
    """Signal a POSIX process group.

    Returns:
        True when ``killpg`` was delivered. macOS reports an already-reaped
        group as ``PermissionError`` rather than ``ProcessLookupError``.
    """
    try:
        os.killpg(pid, sig)
        return True
    except ProcessLookupError, PermissionError:
        return False


@dataclass
class LocalShellComponent(ShellComponent):
    _sessions: dict[str, _LocalShellSession] = field(default_factory=dict, init=False)
    _sessions_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    max_sessions: int = 16
    max_output_bytes: int = 4 * 1024 * 1024
    session_ttl_seconds: int = 30 * 60
    disk_quota_bytes: int = 32 * 1024 * 1024

    async def exec(  # noqa: ASYNC109
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
        timeout_seconds: int | None = 300,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")

        def _run() -> dict[str, Any]:
            run_env = os.environ.copy()
            if env:
                run_env.update({str(k): str(v) for k, v in env.items()})
            if sys.platform == "win32":
                # Python children otherwise emit text in the ANSI code page
                # (e.g. cp1252) and crash printing non-ASCII output.
                run_env.setdefault("PYTHONIOENCODING", "utf-8")
            working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
            popen_command: str | list[str] = command
            popen_shell = shell
            if sys.platform == "win32" and shell:
                popen_command = [
                    resolve_windows_shell(),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                ]
                popen_shell = False
            popen_kwargs: dict[str, Any] = {
                "shell": popen_shell,
                "cwd": working_dir,
                "env": run_env,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                )
            else:
                popen_kwargs["start_new_session"] = True
            if background:
                # `command` is intentionally executed through the current shell so
                # local computer-use behavior matches existing tool semantics.
                # Safety relies on `_is_safe_command()` and the allowed-root checks.
                proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    popen_command,
                    # Controlled local computer-use command.
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **popen_kwargs,  # nosec B602
                )
                return {"pid": proc.pid, "stdout": "", "stderr": "", "exit_code": None}
            # `command` is intentionally executed through the current shell so
            # local computer-use behavior matches existing tool semantics.
            # Safety relies on `_is_safe_command()` and the allowed-root checks.
            proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                popen_command,
                # Controlled local computer-use command.
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_kwargs,  # nosec B602
            )
            effective_timeout = timeout if timeout is not None else timeout_seconds
            try:
                stdout, stderr = proc.communicate(timeout=effective_timeout or 300)
            except subprocess.TimeoutExpired:
                should_kill_parent = sys.platform != "win32"
                if sys.platform == "win32":
                    try:
                        taskkill_result = subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                        should_kill_parent = taskkill_result.returncode != 0
                    except Exception:
                        should_kill_parent = True
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                        should_kill_parent = False
                    except OSError:
                        should_kill_parent = True
                if should_kill_parent:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                raise
            return {
                "stdout": _decode_shell_output(stdout),
                "stderr": _decode_shell_output(stderr),
                "exit_code": proc.returncode,
            }

        return await asyncio.to_thread(_run)

    async def exec_managed(
        self,
        command: str,
        *,
        owner_id: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
        yield_time_ms: int = 10_000,
        max_output_chars: int = 10_000,
        runtime_id: str = "local",
        sender_id: str = "",
        allowed_root: str | None = None,
        creator_is_admin: bool = False,
        sandboxed: bool = False,
        permission_check: Callable[[], bool] | None = None,
        allow_network: bool = False,
        filesystem_scope: str = "workspace",
        readable_roots: tuple[Path, ...] = (),
        writable_roots: tuple[Path, ...] = (),
    ) -> dict[str, Any]:  # noqa: ASYNC109
        """Start a runtime-owned interactive shell session."""
        if not _is_safe_command(command):
            raise PermissionError("Blocked unsafe shell command.")
        if not 0 <= yield_time_ms <= 30_000:
            raise ValueError("yield_time_ms must be between 0 and 30000")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        max_output_chars = max(1, min(max_output_chars, 100_000))
        working_dir = Path(cwd or get_astrbot_root()).resolve(strict=False)
        boundary = Path(allowed_root or get_astrbot_root()).resolve(strict=False)
        if not working_dir.is_relative_to(boundary):
            raise PermissionError("Shell cwd is outside the allowed workspace")
        working_dir.mkdir(parents=True, exist_ok=True)
        owner_runtime_id = str(runtime_id or "local")
        owner_sender_id = str(sender_id or "")
        session_id = f"sh_{uuid.uuid4().hex[:16]}"
        output_dir = Path(get_astrbot_system_tmp_path())
        output_dir.mkdir(parents=True, exist_ok=True)

        async with self._sessions_lock:
            if len(self._sessions) >= self.max_sessions:
                raise ValueError("Managed shell session limit reached")
            if permission_check is not None and not permission_check():
                raise PermissionError(
                    "Local shell permissions changed; retry the command."
                )
            output_file = tempfile.TemporaryFile(mode="w+b", dir=output_dir)
            output_lock = threading.Lock()
            try:
                if sandboxed:
                    process = await create_process_sandbox().spawn_shell(
                        command,
                        SandboxSpec(
                            workspace=working_dir,
                            allow_network=allow_network,
                            filesystem_scope=filesystem_scope,
                            readable_roots=readable_roots,
                            writable_roots=writable_roots,
                        ),
                        env={str(k): str(v) for k, v in (env or {}).items()},
                    )
                else:
                    run_env = {
                        **os.environ,
                        **{str(k): str(v) for k, v in (env or {}).items()},
                    }
                    process_kwargs: dict[str, Any] = {
                        "stdin": asyncio.subprocess.PIPE,
                        "stdout": asyncio.subprocess.PIPE,
                        "stderr": asyncio.subprocess.STDOUT,
                        "cwd": str(working_dir),
                        "env": run_env,
                    }
                    if sys.platform == "win32":
                        run_env.setdefault("PYTHONIOENCODING", "utf-8")
                        process_kwargs["creationflags"] = getattr(
                            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                        )
                        process = await asyncio.create_subprocess_exec(
                            resolve_windows_shell(),
                            "-NoLogo",
                            "-NoProfile",
                            "-NonInteractive",
                            "-Command",
                            command,
                            **process_kwargs,
                        )
                    else:
                        process_kwargs["start_new_session"] = True
                        process = await asyncio.create_subprocess_shell(
                            command, **process_kwargs
                        )
            except BaseException:
                output_file.close()
                raise

            output_event = asyncio.Event()

            async def capture_output() -> None:
                if process.stdout is None:
                    return
                output_size = 0
                try:
                    while chunk := await process.stdout.read(8192):
                        remaining = self.max_output_bytes - output_size
                        if remaining <= 0:
                            session.output_limited = True
                            await self._terminate_process(session)
                            return
                        if len(chunk) > remaining:
                            chunk = chunk[:remaining]
                            session.output_limited = True
                        with output_lock:
                            output_file.seek(0, os.SEEK_END)
                            output_file.write(chunk)
                            output_file.flush()
                        output_size += len(chunk)
                        output_event.set()
                        if session.output_limited:
                            await self._terminate_process(session)
                            return
                except asyncio.CancelledError:
                    raise

            reader_task = asyncio.create_task(
                capture_output(), name=f"shell-reader-{session_id}"
            )
            wait_task = asyncio.create_task(
                process.wait(), name=f"shell-wait-{session_id}"
            )
            wait_task.add_done_callback(lambda _: output_event.set())
            session = _LocalShellSession(
                session_id=session_id,
                runtime_id=owner_runtime_id,
                umo=owner_id,
                sender_id=owner_sender_id,
                creator_is_admin=creator_is_admin,
                sandboxed=sandboxed,
                process=process,
                output_file=output_file,
                output_lock=output_lock,
                started_at=time.monotonic(),
                last_activity=time.monotonic(),
                output_event=output_event,
                reader_task=reader_task,
                wait_task=wait_task,
                permission_check=permission_check,
            )
            self._sessions[session_id] = session

        if permission_check is not None and not permission_check():
            await self.shutdown_sessions(invalid_only=True)
            raise PermissionError("Local shell permissions changed; retry the command.")
        effective_ttl = timeout if timeout is not None else self.session_ttl_seconds
        if effective_ttl > 0:
            session.timeout_task = asyncio.create_task(
                self._timeout_session(session, effective_ttl),
                name=f"shell-timeout-{session_id}",
            )
        if yield_time_ms:
            try:
                await asyncio.wait_for(asyncio.shield(wait_task), yield_time_ms / 1000)
            except TimeoutError:
                pass
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            yield_time_ms=0,
            max_output_chars=max_output_chars,
            runtime_id=owner_runtime_id,
            sender_id=owner_sender_id,
        )

    async def list_sessions(
        self,
        owner_id: str,
        *,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        sessions = await self._owned_sessions(owner_id, runtime_id, sender_id)
        return {"sessions": [self._session_summary(session) for session in sessions]}

    async def poll_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        cursor: int | None = None,
        yield_time_ms: int = 0,
        max_output_chars: int = 10_000,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        if not 0 <= yield_time_ms <= 30_000:
            raise ValueError("yield_time_ms must be between 0 and 30000")
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        session.last_activity = time.monotonic()
        read_cursor = session.cursor if cursor is None else max(0, cursor)

        async def read_output() -> tuple[bytes, int, int]:
            def _read() -> tuple[bytes, int, int]:
                with session.output_lock:
                    if session.output_file.closed:
                        return b"", read_cursor, read_cursor
                    try:
                        size = os.fstat(session.output_file.fileno()).st_size
                    except OSError, ValueError:
                        return b"", read_cursor, read_cursor
                    start = min(read_cursor, size)
                    session.output_file.seek(start)
                    data = session.output_file.read(max_output_chars)
                return data, start + len(data), size

            return await asyncio.to_thread(_read)

        data, next_cursor, size = await read_output()
        if not data and session.process.returncode is None and yield_time_ms:
            session.output_event.clear()
            waiter = asyncio.create_task(session.output_event.wait())
            try:
                await asyncio.wait(
                    {waiter, session.wait_task},
                    timeout=yield_time_ms / 1000,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not waiter.done():
                    waiter.cancel()
                    try:
                        await waiter
                    except asyncio.CancelledError:
                        pass
            if session.wait_task.done():
                await session.reader_task
            data, next_cursor, size = await read_output()
        if session.process.returncode is not None:
            await session.reader_task
            data, next_cursor, size = await read_output()
        session.cursor = next_cursor
        status = self._session_status(session)
        has_more = next_cursor < size
        result = {
            "session_id": session.session_id,
            "pid": session.process.pid,
            "status": status,
            "stdout": _decode_shell_output(data),
            "stderr": "",
            "exit_code": session.process.returncode,
            "cursor": next_cursor,
            "has_more": has_more,
            "session_closed": session.process.returncode is not None and not has_more,
        }
        if result["session_closed"]:
            await self._remove_session(session)
        return result

    async def write_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        chars: str,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        session.last_activity = time.monotonic()
        if session.process.returncode is not None or session.process.stdin is None:
            raise ValueError("Shell session is not accepting input")
        session.process.stdin.write(chars.encode("utf-8"))
        await session.process.stdin.drain()
        return {
            "session_id": session_id,
            "status": "running",
            "written_chars": len(chars),
        }

    async def interrupt_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        yield_time_ms: int = 1000,
        max_output_chars: int = 10000,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        if session.process.returncode is None:
            if session.sandboxed:
                cast(SandboxProcess, session.process).interrupt()
            else:
                native_process = cast(asyncio.subprocess.Process, session.process)
                if sys.platform == "win32":
                    native_process.send_signal(
                        getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM)
                    )
                elif not _signal_posix_process_group(native_process.pid, signal.SIGINT):
                    try:
                        native_process.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        pass
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            yield_time_ms=yield_time_ms,
            max_output_chars=max_output_chars,
            runtime_id=runtime_id,
            sender_id=sender_id,
        )

    async def terminate_session(
        self,
        *,
        owner_id: str,
        session_id: str,
        max_output_chars: int = 10000,
        runtime_id: str = "local",
        sender_id: str = "",
    ) -> dict[str, Any]:
        session = await self._get_owned_session(
            session_id, owner_id, runtime_id, sender_id
        )
        session.terminated = True
        await self._terminate_process(session)
        return await self.poll_session(
            owner_id=owner_id,
            session_id=session_id,
            max_output_chars=max_output_chars,
            runtime_id=runtime_id,
            sender_id=sender_id,
        )

    async def shutdown_sessions(self, *, invalid_only: bool = False) -> None:
        async with self._sessions_lock:
            sessions = []
            for session in self._sessions.values():
                permission_check = session.permission_check
                if (
                    not invalid_only
                    or permission_check is None
                    or not permission_check()
                ):
                    sessions.append(session)
            for session in sessions:
                session.terminated = True
        termination_results = await asyncio.gather(
            *(self._terminate_process(session) for session in sessions),
            return_exceptions=True,
        )
        for session, result in zip(sessions, termination_results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to terminate managed local shell session %s: %s",
                    session.session_id,
                    result,
                )
        await asyncio.gather(
            *(session.reader_task for session in sessions),
            return_exceptions=True,
        )
        for session in sessions:
            await self._remove_session(session)

    async def _timeout_session(  # noqa: ASYNC109
        self,
        session: _LocalShellSession,
        timeout: int,  # noqa: ASYNC109
    ) -> None:
        try:
            while not session.wait_task.done():
                remaining = timeout - (time.monotonic() - session.last_activity)
                if remaining <= 0:
                    session.timed_out = True
                    await self._terminate_process(session)
                    return
                try:
                    await asyncio.wait_for(asyncio.shield(session.wait_task), remaining)
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise

    async def _owned_sessions(
        self, owner_id: str, runtime_id: str, sender_id: str
    ) -> list[_LocalShellSession]:
        async with self._sessions_lock:
            return [
                session
                for session in self._sessions.values()
                if session.runtime_id == runtime_id
                and session.umo == owner_id
                and session.sender_id == sender_id
            ]

    async def _get_owned_session(
        self, session_id: str, owner_id: str, runtime_id: str, sender_id: str
    ) -> _LocalShellSession:
        async with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None or (session.runtime_id, session.umo, session.sender_id) != (
            runtime_id,
            owner_id,
            sender_id,
        ):
            raise ValueError("Shell session was not found")
        permission_check = session.permission_check
        if permission_check is not None and not permission_check():
            await self.shutdown_sessions(invalid_only=True)
            raise ValueError(
                "Shell session expired after a permission change. "
                "Start a new shell session."
            )
        return session

    def _session_status(self, session: _LocalShellSession) -> str:
        if session.process.returncode is None:
            return "running"
        if session.timed_out:
            return "timed_out"
        if session.output_limited:
            return "output_limited"
        if session.terminated:
            return "terminated"
        return "completed" if session.process.returncode == 0 else "failed"

    def _session_summary(self, session: _LocalShellSession) -> dict[str, Any]:
        try:
            size = os.fstat(session.output_file.fileno()).st_size
        except OSError, ValueError:
            size = session.cursor
        return {
            "session_id": session.session_id,
            "pid": session.process.pid,
            "status": self._session_status(session),
            "exit_code": session.process.returncode,
            "started_at": session.started_at,
            "sandboxed": session.sandboxed,
            "unread_output_bytes": max(0, size - session.cursor),
        }

    async def _remove_session(self, session: _LocalShellSession) -> None:
        async with self._sessions_lock:
            if self._sessions.get(session.session_id) is session:
                self._sessions.pop(session.session_id, None)
        if (
            session.timeout_task
            and not session.timeout_task.done()
            and session.timeout_task is not asyncio.current_task()
        ):
            session.timeout_task.cancel()
            try:
                await session.timeout_task
            except asyncio.CancelledError:
                pass
        with session.output_lock:
            session.output_file.close()

    async def _terminate_process(self, session: _LocalShellSession) -> None:
        process = session.process
        if process.returncode is not None and not session.sandboxed:
            return
        if session.sandboxed:
            process.terminate()
        else:
            native_process = cast(asyncio.subprocess.Process, process)
            if sys.platform == "win32":
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/F", "/T", "/PID", str(native_process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )
                    if result.returncode != 0:
                        _signal_asyncio_process(native_process, terminate=True)
                except Exception:
                    _signal_asyncio_process(native_process, terminate=True)
            elif not _signal_posix_process_group(native_process.pid, signal.SIGTERM):
                _signal_asyncio_process(native_process, terminate=True)
        try:
            await asyncio.wait_for(asyncio.shield(session.wait_task), 5)
        except TimeoutError:
            if session.sandboxed:
                process.kill()
            else:
                native_process = cast(asyncio.subprocess.Process, process)
                if sys.platform == "win32":
                    _signal_asyncio_process(native_process, terminate=False)
                elif not _signal_posix_process_group(
                    native_process.pid, signal.SIGKILL
                ):
                    _signal_asyncio_process(native_process, terminate=False)
            try:
                await session.wait_task
            except ProcessLookupError:
                return
        except ProcessLookupError:
            return


@dataclass
class _LocalShellSession:
    session_id: str
    runtime_id: str
    umo: str
    sender_id: str
    creator_is_admin: bool
    sandboxed: bool
    process: SandboxProcess | asyncio.subprocess.Process
    output_file: BinaryIO
    output_lock: LockType
    started_at: float
    output_event: asyncio.Event
    reader_task: asyncio.Task
    wait_task: asyncio.Task
    last_activity: float
    permission_check: Callable[[], bool] | None = None
    timeout_task: asyncio.Task | None = None
    cursor: int = 0
    timed_out: bool = False
    terminated: bool = False
    output_limited: bool = False


@dataclass
class LocalPythonComponent(PythonComponent):
    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout_seconds: int = 30,
        silent: bool = False,
        cwd: str | None = None,
        sandboxed: bool = False,
        allow_network: bool = False,
        filesystem_scope: str = "workspace",
        readable_roots: tuple[Path, ...] = (),
        writable_roots: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            try:
                working_dir = Path(cwd).resolve() if cwd else Path(get_astrbot_root())
                if sandboxed:
                    result = create_process_sandbox().run(
                        [sys.executable, "-c", code],
                        SandboxSpec(
                            workspace=working_dir,
                            allow_network=allow_network,
                            filesystem_scope=filesystem_scope,
                            readable_roots=readable_roots,
                            writable_roots=writable_roots,
                        ),
                        timeout=timeout_seconds,
                        output_limit=_LOCAL_SANDBOX_MAX_OUTPUT_BYTES,
                        discard_stdout=silent,
                    )
                    stdout = _decode_shell_output(result.stdout)
                    stderr = _decode_shell_output(result.stderr)
                    stdout_limited = result.stdout_limited
                    stderr_limited = result.stderr_limited
                else:
                    child_env = os.environ.copy()
                    if sys.platform == "win32":
                        child_env.setdefault("PYTHONIOENCODING", "utf-8")
                    result = subprocess.run(
                        [os.environ.get("PYTHON", sys.executable), "-c", code],
                        timeout=timeout_seconds,
                        capture_output=True,
                        cwd=working_dir,
                        env=child_env,
                    )
                    stdout = "" if silent else _decode_shell_output(result.stdout)
                    stderr = _decode_shell_output(result.stderr)
                    stdout_limited = False
                    stderr_limited = False
                if stdout_limited or stderr_limited:
                    stderr = (
                        f"{stderr}\nExecution output exceeded "
                        f"{_LOCAL_SANDBOX_MAX_OUTPUT_BYTES} bytes."
                    ).strip()
                execution_error = (
                    stderr
                    if result.returncode != 0 or stdout_limited or stderr_limited
                    else ""
                )
                return {
                    "data": {
                        "output": {"text": stdout, "images": []},
                        "error": execution_error,
                    }
                }
            except SandboxTimeoutError, subprocess.TimeoutExpired:
                return {
                    "data": {
                        "output": {"text": "", "images": []},
                        "error": "Execution timed out.",
                    }
                }

        return await asyncio.to_thread(_run)


@dataclass
class LocalFileSystemComponent(FileSystemComponent):
    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(abs_path, mode)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
        file_descriptor: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            detected_encoding = encoding
            if encoding == "utf-8":
                if file_descriptor is None:
                    with open(abs_path, "rb") as f:
                        raw_sample = f.read(8192)
                else:
                    raw_sample = read_fd_at(file_descriptor, 8192, 0)
                detected_encoding = detect_text_encoding(raw_sample) or encoding
            return {
                "success": True,
                "content": read_local_text_range_sync(
                    abs_path,
                    encoding=detected_encoding,
                    offset=offset,
                    limit=limit,
                    file_descriptor=file_descriptor,
                ),
            }

        return await asyncio.to_thread(_run)

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
        sandboxed: bool = False,
        sandbox_root: str | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            search_path = Path(path or get_astrbot_root()).resolve(strict=False)
            if sandboxed:
                if not sandbox_root:
                    return {
                        "success": False,
                        "content": "",
                        "error": "A sandbox root is required for restricted Local search.",
                    }
                rg_path = shutil.which("rg")
                if not rg_path:
                    return {
                        "success": False,
                        "content": "",
                        "error": "The ripgrep (rg) executable is required for sandboxed file search.",
                    }
                command = [
                    str(Path(rg_path).resolve()),
                    "--color=never",
                    "-n",
                    "--max-columns",
                    "1000",
                    "-e",
                    pattern,
                ]
                if glob:
                    command.extend(["-g", glob])
                if after_context is not None:
                    command.extend(["-A", str(after_context)])
                if before_context is not None:
                    command.extend(["-B", str(before_context)])
                command.extend(["--", str(search_path)])
                try:
                    result = create_process_sandbox().run(
                        command,
                        SandboxSpec(
                            workspace=Path(sandbox_root),
                            workspace_writable=False,
                        ),
                        timeout=30,
                    )
                except (SandboxTimeoutError, OSError) as exc:
                    return {
                        "success": False,
                        "content": "",
                        "error": (
                            "File search timed out after 30 seconds."
                            if isinstance(exc, SandboxTimeoutError)
                            else f"Unable to start ripgrep: {exc}"
                        ),
                    }
                stdout = _decode_shell_output(result.stdout)
                if result.returncode in (0, 1):
                    return {
                        "success": True,
                        "content": _truncate_long_lines(
                            stdout if result.returncode == 0 else ""
                        ),
                    }
                return {
                    "success": False,
                    "content": "",
                    "error": _decode_shell_output(result.stderr)
                    or f"ripgrep exited with code {result.returncode}",
                    "exit_code": result.returncode,
                }
            rg_path = shutil.which("rg")
            if rg_path:
                command = [
                    rg_path,
                    "--color=never",
                    "-n",
                    "--max-columns",
                    "1000",
                    "-e",
                    pattern,
                ]
                if glob:
                    command.extend(["-g", glob])
                if after_context is not None:
                    command.extend(["-A", str(after_context)])
                if before_context is not None:
                    command.extend(["-B", str(before_context)])
                command.extend(["--", str(search_path)])

                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        cwd=get_astrbot_root(),
                        timeout=30,
                    )
                except subprocess.TimeoutExpired:
                    return {
                        "success": False,
                        "content": "",
                        "error": "File search timed out after 30 seconds.",
                    }
                if result.returncode in (0, 1):
                    return {
                        "success": True,
                        "content": _truncate_long_lines(
                            _decode_shell_output(result.stdout)
                        ),
                    }
                return {
                    "success": False,
                    "content": "",
                    "error": _decode_shell_output(result.stderr)
                    or f"command exited with code {result.returncode}",
                    "exit_code": result.returncode,
                }

            matcher = re.compile(pattern)
            output_lines: list[str] = []
            paths = (
                [search_path]
                if search_path.is_file()
                else sorted(
                    path_ for path_ in search_path.rglob("*") if path_.is_file()
                )
            )
            for file_path in paths:
                if glob and not fnmatch.fnmatch(file_path.name, glob):
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                lines = text.splitlines()
                matching_indexes = [
                    index
                    for index, line in enumerate(lines)
                    if matcher.search(line) is not None
                ]
                if not matching_indexes:
                    continue

                if after_context is None and before_context is None:
                    for index in matching_indexes:
                        output_lines.append(
                            f"{file_path}:{index + 1}:{lines[index][:1000]}\n"
                        )
                    continue

                trailing = after_context or 0
                leading = before_context or 0
                ranges: list[tuple[int, int]] = []
                for index in matching_indexes:
                    start = max(0, index - leading)
                    end = min(len(lines) - 1, index + trailing)
                    if ranges and start <= ranges[-1][1] + 1:
                        ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
                    else:
                        ranges.append((start, end))

                for range_index, (start, end) in enumerate(ranges):
                    for line_index in range(start, end + 1):
                        output_lines.append(
                            f"{file_path}:{line_index + 1}:{lines[line_index][:1000]}\n"
                        )
                    if range_index != len(ranges) - 1:
                        output_lines.append("--\n")

            return {"success": True, "content": "".join(output_lines)}

        return await asyncio.to_thread(_run)

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
        file_descriptor: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            if file_descriptor is None:
                file_obj = open(abs_path, encoding=encoding)
            else:
                file_obj = os.fdopen(
                    os.dup(file_descriptor),
                    mode="r+",
                    encoding=encoding,
                )
                file_obj.seek(0)
            with file_obj as f:
                content = f.read()
                occurrences = content.count(old_string)
                if occurrences == 0:
                    return {
                        "success": False,
                        "error": "old string not found in file",
                        "replacements": 0,
                    }
                if replace_all:
                    updated = content.replace(old_string, new_string)
                    replacements = occurrences
                else:
                    updated = content.replace(old_string, new_string, 1)
                    replacements = 1
                if file_descriptor is not None:
                    f.seek(0)
                    f.truncate()
                    f.write(updated)
                    return {
                        "success": True,
                        "path": abs_path,
                        "replacements": replacements,
                    }
            with open(abs_path, "w", encoding=encoding) as f:
                f.write(updated)
            return {
                "success": True,
                "path": abs_path,
                "replacements": replacements,
            }

        return await asyncio.to_thread(_run)

    async def write_file(
        self,
        path: str,
        content: str,
        mode: str = "w",
        encoding: str = "utf-8",
        file_descriptor: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            if file_descriptor is None:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                file_obj = open(abs_path, mode, encoding=encoding)
            else:
                file_obj = os.fdopen(
                    os.dup(file_descriptor),
                    mode=mode,
                    encoding=encoding,
                )
                if mode == "w":
                    file_obj.seek(0)
                    file_obj.truncate()
                elif mode == "a":
                    file_obj.seek(0, os.SEEK_END)
            with file_obj as f:
                f.write(content)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def delete_file(self, path: str) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            if os.path.isdir(abs_path):
                shutil.rmtree(abs_path)
            else:
                os.remove(abs_path)
            return {"success": True, "path": abs_path}

        return await asyncio.to_thread(_run)

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            entries = os.listdir(abs_path)
            if not show_hidden:
                entries = [e for e in entries if not e.startswith(".")]
            return {"success": True, "entries": entries}

        return await asyncio.to_thread(_run)


class LocalBooter(ComputerBooter):
    def __init__(self) -> None:
        self._fs = LocalFileSystemComponent()
        self._python = LocalPythonComponent()
        self._shell = LocalShellComponent()

    async def boot(self, session_id: str) -> None:
        logger.info(f"Local computer booter initialized for session: {session_id}")

    async def shutdown(self, **kwargs: Any) -> None:
        _ = kwargs
        await self._shell.shutdown_sessions()
        logger.info("Local computer booter shutdown complete.")

    @property
    def fs(self) -> FileSystemComponent:
        return self._fs

    @property
    def python(self) -> PythonComponent:
        return self._python

    @property
    def shell(self) -> ShellComponent:
        return self._shell

    async def upload_file(self, path: str, file_name: str) -> dict:
        raise NotImplementedError(
            "LocalBooter does not support upload_file operation. Use shell instead."
        )

    async def download_file(self, remote_path: str, local_path: str) -> None:
        raise NotImplementedError(
            "LocalBooter does not support download_file operation. Use shell instead."
        )

    async def available(self) -> bool:
        return True
