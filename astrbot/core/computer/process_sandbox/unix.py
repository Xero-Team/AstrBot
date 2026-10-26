from __future__ import annotations

import asyncio
import contextlib
import os
import signal as signal_module
import subprocess  # noqa: S404  # subprocess is an intentional runtime dependency
import sys
import tempfile
import time
import uuid
from abc import abstractmethod
from pathlib import Path

from .base import (
    ProcessSandbox,
    SandboxLimits,
    SandboxProcess,
    SandboxRunResult,
    SandboxSpec,
    SandboxStdin,
    SandboxStdout,
    SandboxTimeoutError,
)
from .fs_policy import DenyRuleSet


class UnixSandboxProcess:
    """Adapt an asyncio process to process-tree sandbox semantics."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        """Store the session-leading asyncio process.

        Args:
            process: Process started in a new Unix session.
        """
        self._process = process

    @property
    def pid(self) -> int:
        """Return the process-group leader identifier."""
        return self._process.pid

    @property
    def returncode(self) -> int | None:
        """Return the process exit status when available."""
        return self._process.returncode

    @property
    def stdin(self) -> SandboxStdin | None:
        """Return the native asyncio standard-input stream."""
        return self._process.stdin

    @property
    def stdout(self) -> SandboxStdout | None:
        """Return the native asyncio standard-output stream."""
        return self._process.stdout

    async def wait(self) -> int:
        """Wait for the session-leading process to exit."""
        return await self._process.wait()

    def interrupt(self) -> None:
        """Send SIGINT to the complete Unix process group."""
        self._send_signal(signal_module.SIGINT)

    def terminate(self) -> None:
        """Send SIGTERM to the complete Unix process group."""
        self._send_signal(signal_module.SIGTERM)

    def kill(self) -> None:
        """Send SIGKILL to the complete Unix process group."""
        self._send_signal(signal_module.SIGKILL)

    def _send_signal(self, signal: int) -> None:
        """Send a Unix signal to the process group if it still exists.

        Args:
            signal: Unix signal number to send.
        """
        try:
            os.killpg(self.pid, signal)
        except ProcessLookupError, PermissionError:
            return


class UnixProcessSandbox(ProcessSandbox):
    """Common launcher behavior for Unix sandbox implementations."""

    _uses_bridge_ready_path = False

    def build_command(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build a Unix sandbox wrapper command.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem, network, and resource policy.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Platform sandbox command and arguments.
        """
        command, _ready_path = self._build_command_with_ready(argv, spec, env=env)
        return command

    def _build_command_with_ready(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> tuple[list[str], Path | None]:
        """Build a launcher command and its structured readiness path.

        The readiness path is generated here instead of being recovered from
        launcher argv. Scanning argv would let caller-controlled environment
        names or workload arguments spoof the path, and the path is later
        deleted after launch.
        """
        argv, workspace, env = self._prepare_command(argv, spec, env=env)
        ready_path = (
            self._ready_file_path(workspace, spec)
            if spec.proxy is not None and self._uses_bridge_ready_path
            else None
        )
        return (
            self._build_command(
                argv,
                workspace,
                spec,
                env,
                ready_path=ready_path,
            ),
            ready_path,
        )

    @staticmethod
    def _ready_file_path(workspace: Path, spec: SandboxSpec) -> Path:
        """Return a host-visible path for the bridge readiness marker.

        The marker must be written from inside the sandbox and observed by the
        host. A workspace-scoped sandbox only exposes its workspace and
        writable roots, so a configured deny rule can make the workspace
        read-only. Prefer the workspace, then fall back to a mounted writable
        root that the same deny policy does not cover.
        """
        rules = DenyRuleSet(spec.policy.filesystem)
        candidates: list[Path] = []
        if spec.workspace_writable or spec.policy.filesystem_scope == "host":
            candidates.append(workspace)
        candidates.extend(root.resolve() for root in spec.writable_roots)
        if spec.policy.filesystem_scope == "host":
            # Host scope sees the real temporary directory, so it remains a
            # valid marker location when a deny rule covers the workspace.
            candidates.append(Path(tempfile.gettempdir()).resolve())
        for candidate in dict.fromkeys(candidates):
            if not candidate.is_dir() or not os.access(candidate, os.W_OK):
                continue
            probe = candidate / ".astrbot-bridge-ready-probe"
            if not rules.matches(probe, "edit"):
                return candidate / f".astrbot-bridge-ready-{uuid.uuid4().hex}"
        raise RuntimeError(
            "No writable Local sandbox path is available for the bridge "
            "readiness marker; adjust the configured filesystem deny rules."
        )

    def run(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        output_limit: int | None = None,
        discard_stdout: bool = False,
    ) -> SandboxRunResult:
        """Run a command through the Unix sandbox wrapper.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem, network, and resource policy.
            env: Additional environment variables exposed inside the sandbox.
            timeout: Maximum wall-clock runtime in seconds.
            output_limit: Maximum captured bytes for each output stream.
            discard_stdout: Whether to discard standard output.

        Returns:
            Captured process result.

        Raises:
            SandboxTimeoutError: If the process exceeds ``timeout``.
            ValueError: If ``output_limit`` is not positive.
        """
        if output_limit is not None and output_limit <= 0:
            raise ValueError("Sandbox output limit must be greater than 0.")

        command, ready_path = self._build_command_with_ready(argv, spec, env=env)
        with (
            tempfile.TemporaryFile() as stdout_file,
            tempfile.TemporaryFile() as stderr_file,
        ):
            process = subprocess.Popen(  # noqa: S603  # argv is built internally; sandbox/blocklist is the boundary
                command,
                cwd=spec.workspace.resolve(),
                env=self._launch_environment(
                    spec,
                    {str(k): str(v) for k, v in (env or {}).items()},
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL if discard_stdout else stdout_file,
                stderr=stderr_file,
            )
            try:
                if ready_path is not None:
                    _wait_for_bridge_ready(process, ready_path)
                process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _kill_process_tree(process)
                raise SandboxTimeoutError(
                    f"Sandbox command timed out after {timeout} seconds."
                ) from exc
            except BaseException:
                _kill_process_tree(process)
                raise
            finally:
                _remove_ready_file(ready_path)

            read_size = None if output_limit is None else output_limit + 1
            if discard_stdout:
                stdout = b""
            else:
                stdout_file.seek(0)
                stdout = stdout_file.read(read_size)
            stderr_file.seek(0)
            stderr = stderr_file.read(read_size)
        return SandboxRunResult(
            returncode=process.returncode,
            stdout=stdout[:output_limit] if output_limit is not None else stdout,
            stderr=stderr[:output_limit] if output_limit is not None else stderr,
            stdout_limited=output_limit is not None and len(stdout) > output_limit,
            stderr_limited=output_limit is not None and len(stderr) > output_limit,
        )

    async def spawn_shell(
        self,
        command: str,
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> SandboxProcess:
        """Start a shell command in a separately managed process group.

        Args:
            command: Shell command to execute inside the sandbox.
            spec: Filesystem, network, and resource policy.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Process adapter whose lifecycle methods affect the process group.
        """
        platform_command, ready_path = self._build_command_with_ready(
            ["/bin/sh", "-c", command],
            spec,
            env=env,
        )
        process = await asyncio.create_subprocess_exec(
            *platform_command,
            cwd=spec.workspace.resolve(),
            env=self._launch_environment(
                spec,
                {str(k): str(v) for k, v in (env or {}).items()},
            ),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        if ready_path is not None:
            try:
                await asyncio.to_thread(
                    _wait_for_bridge_ready,
                    process,
                    ready_path,
                )
            except BaseException:
                _kill_process_tree(process)
                with contextlib.suppress(Exception):
                    await process.wait()
                _remove_ready_file(ready_path)
                raise
            _remove_ready_file(ready_path)
        return UnixSandboxProcess(process)

    @abstractmethod
    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
        *,
        ready_path: Path | None = None,
    ) -> list[str]:
        """Build a Unix sandbox command after common input validation."""


def _wait_for_bridge_ready(
    process: subprocess.Popen | asyncio.subprocess.Process,
    ready_path: Path,
    *,
    timeout: float = 10.0,
) -> None:
    """Wait for the in-sandbox bridge readiness marker or fail closed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_path.is_file():
            return
        returncode = process.returncode
        if returncode is None and isinstance(process, subprocess.Popen):
            # Popen only refreshes returncode when polled or waited.
            returncode = process.poll()
        if returncode is not None:
            raise RuntimeError("The Local sandbox bridge exited before becoming ready.")
        time.sleep(0.02)
    raise TimeoutError("The Local sandbox bridge did not become ready.")


def _remove_ready_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _kill_process_tree(process: subprocess.Popen | asyncio.subprocess.Process) -> None:
    """Terminate a launcher process group without masking the original error."""
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal_module.SIGKILL)
    except ProcessLookupError, PermissionError:
        try:
            process.kill()
        except ProcessLookupError:
            return
    try:
        if isinstance(process, subprocess.Popen):
            process.wait(timeout=5)
        else:
            # The caller owns waiting for asyncio processes.
            pass
    except OSError, subprocess.TimeoutExpired:
        return


def build_resource_limited_argv(
    argv: list[str],
    limits: SandboxLimits,
) -> list[str]:
    """Wrap a command with Unix resource-limit setup.

    Args:
        argv: Command and arguments to execute after applying limits.
        limits: Resource ceilings requested by the common sandbox policy.

    Returns:
        Python command that applies supported Unix limits and then executes
        ``argv``.
    """
    wrapper_code = f"""
import os
import resource
import sys

limits = [
    (resource.RLIMIT_CPU, {limits.cpu_seconds}),
    (resource.RLIMIT_FSIZE, {limits.file_size_bytes}),
    (resource.RLIMIT_NOFILE, {limits.open_files}),
    (resource.RLIMIT_CORE, 0),
]
if sys.platform.startswith("linux"):
    # macOS RLIMIT_NPROC counts every process owned by the host user, and its
    # Python process starts above this virtual-address limit.
    limits.extend(
        (
            (resource.RLIMIT_NPROC, {limits.processes}),
            (resource.RLIMIT_AS, {limits.memory_bytes}),
        )
    )
for kind, requested in limits:
    _, hard = resource.getrlimit(kind)
    value = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (value, value))
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
"""
    return [
        str(Path(sys.executable).resolve()),
        "-I",
        "-S",
        "-c",
        wrapper_code,
        *argv,
    ]
