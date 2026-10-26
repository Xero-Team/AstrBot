from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from astrbot.core.computer.local_policy import LocalSandboxPolicy

# Caller environment is inherited by platform launchers before the sandbox is
# active. Dynamic-loader and glibc module variables would execute caller-chosen
# code inside bwrap/sandbox-exec itself, so they never reach the launcher.
_LAUNCHER_ENV_PREFIXES = ("LD_", "DYLD_")
_LAUNCHER_ENV_NAMES = frozenset(
    {
        "GCONV_PATH",
        "LOCPATH",
        "NLSPATH",
        "MALLOC_CONF",
        "GLIBC_TUNABLES",
    }
)


def _unsafe_launcher_environment_name(name: str) -> bool:
    """Return whether a variable can inject code into the launcher process."""
    upper = name.upper()
    return upper.startswith(_LAUNCHER_ENV_PREFIXES) or upper in _LAUNCHER_ENV_NAMES


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """Resource ceilings applied to a sandboxed process tree.

    Args:
        cpu_seconds: Maximum CPU time in seconds.
        file_size_bytes: Maximum size of a file created by one process.
        memory_bytes: Maximum address space or job memory in bytes.
        open_files: Maximum number of open file descriptors or handles when
            supported by the platform.
        processes: Maximum number of processes in the sandbox.
    """

    cpu_seconds: int = 300
    file_size_bytes: int = 512 * 1024 * 1024
    memory_bytes: int = 8 * 1024 * 1024 * 1024
    open_files: int = 256
    processes: int = 256

    def __post_init__(self) -> None:
        """Validate that every resource ceiling is a positive integer.

        Raises:
            ValueError: If a resource ceiling is not a positive integer.
        """
        for name in (
            "cpu_seconds",
            "file_size_bytes",
            "memory_bytes",
            "open_files",
            "processes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"Sandbox limit `{name}` must be a positive integer.")


@dataclass(frozen=True, slots=True)
class SandboxProxyEndpoint:
    """Token-bearing proxy endpoint attached to one sandboxed invocation.

    The token is only ever delivered through inherited process environment
    values. It must not appear in launcher argv or Python ``-c`` source.
    """

    token: str
    http_socket: str | None = None
    socks_socket: str | None = None
    http_port: int = 31280
    socks_port: int = 31080
    platform: str = "linux"

    def http_url(self) -> str:
        """Return the HTTP proxy URL for this endpoint."""
        return f"http://{self.token}@127.0.0.1:{self.http_port}"

    def socks_url(self) -> str:
        """Return the SOCKS5h proxy URL for this endpoint."""
        return f"socks5h://{self.token}@127.0.0.1:{self.socks_port}"


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Permissions, workspace, and limits for a sandboxed process.

    Args:
        workspace: Directory exposed as the process working directory.
        policy: Complete immutable Local sandbox policy.
        workspace_writable: Whether the process may modify the workspace.
        limits: Resource ceilings enforced by the platform backend.
        readable_roots: Additional directories that may be read in workspace scope.
        writable_roots: Additional directories that may be read and modified in
            workspace scope. Missing writable directories are created before launch.
    """

    workspace: Path
    policy: LocalSandboxPolicy = field(default_factory=LocalSandboxPolicy)
    workspace_writable: bool = True
    proxy: SandboxProxyEndpoint | None = None
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    readable_roots: tuple[Path, ...] = ()
    writable_roots: tuple[Path, ...] = ()

    @property
    def filesystem_scope(self) -> str:
        """Return the resolved filesystem scope."""
        return self.policy.filesystem_scope

    @property
    def allow_network(self) -> bool:
        """Return whether sandboxed networking is enabled."""
        return self.policy.network.enabled


@dataclass(frozen=True, slots=True)
class SandboxRunResult:
    """Result returned by a synchronous sandbox execution.

    Args:
        returncode: Process exit status.
        stdout: Captured standard output.
        stderr: Captured standard error.
        stdout_limited: Whether standard output exceeded the requested limit.
        stderr_limited: Whether standard error exceeded the requested limit.
    """

    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    stdout_limited: bool = False
    stderr_limited: bool = False


class SandboxTimeoutError(TimeoutError):
    """Raised when a sandbox process exceeds its execution timeout."""


class SandboxStdin(Protocol):
    """Writable stream used by managed sandbox processes."""

    def write(self, data: bytes) -> None:
        """Buffer bytes for the process standard input."""
        ...

    async def drain(self) -> None:
        """Flush buffered bytes without blocking the event loop."""
        ...


class SandboxStdout(Protocol):
    """Readable stream used by managed sandbox processes."""

    async def read(self, n: int = -1) -> bytes:
        """Read up to ``n`` bytes from the process standard output."""
        ...


class SandboxProcess(Protocol):
    """Process operations used by managed Local shell sessions."""

    @property
    def pid(self) -> int:
        """Return the process identifier."""
        ...

    @property
    def returncode(self) -> int | None:
        """Return the exit status, or ``None`` while the process is running."""
        ...

    @property
    def stdin(self) -> SandboxStdin | None:
        """Return the process standard-input stream when configured."""
        ...

    @property
    def stdout(self) -> SandboxStdout | None:
        """Return the process standard-output stream when configured."""
        ...

    async def wait(self) -> int:
        """Wait for the process to exit."""
        ...

    def interrupt(self) -> None:
        """Interrupt the sandbox process tree."""
        ...

    def terminate(self) -> None:
        """Request graceful termination of the sandbox process tree."""
        ...

    def kill(self) -> None:
        """Force termination of the sandbox process tree."""
        ...


def sandbox_ca_file() -> Path | None:
    """Return the verified CA bundle path exposed to sandboxed clients."""
    candidates: list[Path] = []
    override = os.environ.get("ASTRBOT_SANDBOX_CA_FILE")
    if override:
        candidates.append(Path(override))
    try:
        import certifi

        candidates.append(Path(certifi.where()))
    except Exception:  # noqa: BLE001  # optional runtime dependency lookup
        pass
    candidates.extend(
        (
            Path("/etc/ssl/certs/ca-certificates.crt"),
            Path("/etc/pki/tls/certs/ca-bundle.crt"),
            Path("/etc/ssl/cert.pem"),
        )
    )
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


class ProcessSandbox(ABC):
    """Platform-independent launcher for restricted child processes."""

    def _launch_environment(
        self,
        spec: SandboxSpec,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Return minimal inherited environment for launcher secrets.

        Tokens and CA paths travel through inherited parent environment only;
        platform commands never place them in argv or inline Python source.
        Case variants of proxy variables are always overridden after caller
        environment values so an explicit ``no_proxy`` cannot bypass policy.
        Dynamic-loader and glibc module variables are dropped from the launcher
        environment; platform launchers pass caller variables to the workload
        through their own sandbox-only mechanism.
        """
        python_path = str(Path(sys.executable).parent)
        fallback_paths = [
            entry for entry in os.defpath.split(os.pathsep) if entry and entry != "."
        ]
        caller_environment = {
            str(key): str(value)
            for key, value in (extra or {}).items()
            if not _unsafe_launcher_environment_name(str(key))
        }
        environment = {
            "PATH": os.pathsep.join((python_path, *fallback_paths)),
            **caller_environment,
        }
        if spec.proxy is not None:
            proxy = spec.proxy
            environment["ASTRBOT_SANDBOX_PROXY_TOKEN"] = proxy.token
            ca_file = sandbox_ca_file()
            if ca_file is not None:
                environment["ASTRBOT_SANDBOX_CA_FILE"] = str(ca_file)
                environment["SSL_CERT_FILE"] = str(ca_file)
                environment["REQUESTS_CA_BUNDLE"] = str(ca_file)
                environment["CURL_CA_BUNDLE"] = str(ca_file)
            for key in list(environment):
                if key.lower() in {
                    "http_proxy",
                    "https_proxy",
                    "all_proxy",
                    "no_proxy",
                }:
                    environment.pop(key, None)
            http_url = proxy.http_url()
            socks_url = proxy.socks_url()
            environment.update(
                {
                    "HTTP_PROXY": http_url,
                    "HTTPS_PROXY": http_url,
                    "ALL_PROXY": socks_url,
                    "http_proxy": http_url,
                    "https_proxy": http_url,
                    "all_proxy": socks_url,
                    "NO_PROXY": "",
                    "no_proxy": "",
                }
            )
        return environment

    def _prepare_command(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> tuple[list[str], Path, dict[str, str]]:
        """Validate and normalize a command before platform-specific launch.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem and network access granted to the process.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Normalized arguments, workspace, and environment values.

        Raises:
            RuntimeError: If the workspace does not exist.
            ValueError: If the command, scope, or environment is invalid.
        """
        if not argv:
            raise ValueError("A sandbox command is required.")
        if spec.filesystem_scope not in {"workspace", "host"}:
            raise ValueError(
                f"Invalid Local filesystem scope: {spec.filesystem_scope}."
            )

        sandbox_argv = list(argv)
        workspace = spec.workspace.resolve()
        if not workspace.is_dir():
            raise RuntimeError(f"Sandbox workspace does not exist: {workspace}")
        if spec.filesystem_scope == "workspace":
            for root in spec.writable_roots:
                root.mkdir(parents=True, exist_ok=True)

        normalized_env: dict[str, str] = {}
        for raw_key, raw_value in (env or {}).items():
            key = str(raw_key)
            value = str(raw_value)
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError(f"Invalid sandbox environment variable name: {key!r}.")
            normalized_env[key] = value

        return sandbox_argv, workspace, normalized_env

    @abstractmethod
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
        """Run a restricted process synchronously.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem and network access granted to the process.
            env: Additional environment variables exposed inside the sandbox.
            timeout: Maximum wall-clock runtime in seconds.
            output_limit: Maximum captured bytes for each output stream.
            discard_stdout: Whether to discard standard output.

        Returns:
            Platform-independent process result.

        Raises:
            SandboxTimeoutError: If the process exceeds ``timeout``.
        """
        ...

    @abstractmethod
    async def spawn_shell(
        self,
        command: str,
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> SandboxProcess:
        """Start a managed shell command asynchronously.

        Args:
            command: Shell command to execute inside the sandbox.
            spec: Filesystem and network access granted to the process.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Running restricted process.
        """
        ...
