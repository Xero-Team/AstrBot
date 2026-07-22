import asyncio
import fnmatch
import locale
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot import logger
from astrbot.core.computer.file_read_utils import (
    detect_text_encoding,
    read_local_text_range_sync,
)
from astrbot.core.utils.astrbot_path import get_astrbot_root

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


def _is_safe_command(command: str) -> bool:
    normalized_command = re.sub(r"\s+", " ", command.strip().lower())
    if ":(){:|:&};:" in normalized_command:
        return False
    return not any(
        pattern.search(normalized_command) for pattern in _BLOCKED_COMMAND_PATTERNS
    )


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
        for encoding in ("mbcs", "cp936", "gbk", "gb18030", preferred):
            if decoded := _try_decode(encoding):
                return decoded
    elif decoded := _try_decode(preferred):
        return decoded

    return output.decode("utf-8", errors="replace")


def _decode_shell_output(output: bytes | str | None) -> str:
    return _decode_bytes_with_fallback(output, preferred_encoding="utf-8")


@dataclass
class LocalShellComponent(ShellComponent):
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
            working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
            popen_kwargs: dict[str, Any] = {
                "shell": shell,
                "cwd": working_dir,
                "env": run_env,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            if background:
                # `command` is intentionally executed through the current shell so
                # local computer-use behavior matches existing tool semantics.
                # Safety relies on `_is_safe_command()` and the allowed-root checks.
                proc = subprocess.Popen(  # noqa: S602  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                    command,
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
                command,
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


@dataclass
class LocalPythonComponent(PythonComponent):
    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout_seconds: int = 30,
        silent: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            try:
                working_dir = os.path.abspath(cwd) if cwd else get_astrbot_root()
                result = subprocess.run(
                    [os.environ.get("PYTHON", sys.executable), "-c", code],
                    timeout=timeout_seconds,
                    capture_output=True,
                    cwd=working_dir,
                )
                stdout = "" if silent else _decode_shell_output(result.stdout)
                stderr = (
                    _decode_shell_output(result.stderr)
                    if result.returncode != 0
                    else ""
                )
                return {
                    "data": {
                        "output": {"text": stdout, "images": []},
                        "error": stderr,
                    }
                }
            except subprocess.TimeoutExpired:
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
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            detected_encoding = encoding
            if encoding == "utf-8":
                with open(abs_path, "rb") as f:
                    raw_sample = f.read(8192)
                detected_encoding = detect_text_encoding(raw_sample) or encoding
            return {
                "success": True,
                "content": read_local_text_range_sync(
                    abs_path,
                    encoding=detected_encoding,
                    offset=offset,
                    limit=limit,
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
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            search_path = Path(path or get_astrbot_root()).resolve(strict=False)
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

                result = subprocess.run(
                    command,
                    capture_output=True,
                    cwd=get_astrbot_root(),
                )
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
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            with open(abs_path, encoding=encoding) as f:
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
            with open(abs_path, "w", encoding=encoding) as f:
                f.write(updated)
            return {
                "success": True,
                "path": abs_path,
                "replacements": replacements,
            }

        return await asyncio.to_thread(_run)

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            abs_path = os.path.abspath(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, mode, encoding=encoding) as f:
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
