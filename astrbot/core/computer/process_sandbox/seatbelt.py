from __future__ import annotations

import shutil
import subprocess  # noqa: S404  # subprocess is an intentional runtime dependency
import sys
from pathlib import Path

from astrbot.core.computer.local_policy import expand_path_rule

from .base import SandboxSpec, sandbox_ca_file
from .fs_policy import DenyPolicyError, DenyRuleSet
from .unix import UnixProcessSandbox, build_resource_limited_argv

_PROFILE = """
(version 1)
(deny default)
(deny mach-priv-host-port)
(import "system.sb")

(allow process-fork)
(allow process-exec)
(allow process-info* (target self))
(deny process-exec
    (literal "/usr/bin/open")
    (literal "/usr/bin/osascript"))
(deny appleevent-send)
(deny mach-lookup
    (global-name "com.apple.coreservices.launchservicesd")
    (global-name "com.apple.lsd.mapdb")
    (global-name "com.apple.lsd.modifydb")
    (global-name "com.apple.lsd.open")
    (global-name "com.apple.lsd.xpc"))

(allow file-read-metadata file-test-existence)
(allow file-read* file-test-existence
    (subpath "/bin")
    (subpath "/usr/bin")
    (subpath "/usr/libexec")
    (literal (param "EXECUTABLE"))
    (subpath (param "WORKSPACE"))
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "PYTHON_BASE_PREFIX")))
(allow file-map-executable
    (subpath "/bin")
    (subpath "/usr/bin")
    (subpath "/usr/libexec")
    (literal (param "EXECUTABLE"))
    (subpath (param "WORKSPACE"))
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "PYTHON_BASE_PREFIX")))
(allow file-write*
    (subpath (param "WORKSPACE")))

(deny file-read*
    (literal "/private/etc/master.passwd")
    (literal "/private/etc/passwd"))
(deny network*)
"""
_MAX_PROFILE_BYTES = 1024 * 1024
_MAX_PROFILE_RULES = 4096
_BOOTSTRAP = """
import os
import sys

os.environ["HOME"] = sys.argv[1]
os.environ["TMPDIR"] = sys.argv[2]
os.environ["LANG"] = "C.UTF-8"
workload = sys.argv[4:]
os.execvpe(workload[0], workload, os.environ)
"""
_READ_ONLY_PROFILE = _PROFILE.replace(
    '(allow file-write*\n    (subpath (param "WORKSPACE")))',
    "(deny file-write*)",
)


class SeatbeltProcessSandbox(UnixProcessSandbox):
    """macOS restricted-process launcher backed by Seatbelt."""

    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
    ) -> list[str]:
        """Build the Seatbelt command for validated inputs."""
        seatbelt_path = shutil.which("sandbox-exec", path="/usr/bin")
        if seatbelt_path != "/usr/bin/sandbox-exec":
            raise RuntimeError(
                "Seatbelt (`/usr/bin/sandbox-exec`) is required for restricted "
                "Local execution on macOS."
            )
        if spec.policy.network.enabled and spec.proxy is None:
            raise RuntimeError(
                "Sandboxed network access requires the runtime Local proxy."
            )

        executable_path = (
            Path(argv[0]).resolve()
            if Path(argv[0]).is_absolute() and Path(argv[0]).exists()
            else Path(sys.executable).resolve()
        )
        profile = _PROFILE if spec.workspace_writable else _READ_ONLY_PROFILE
        if spec.policy.filesystem_scope == "host":
            profile = profile.replace(
                '(import "system.sb")',
                '(import "system.sb")\n\n'
                "(allow file-read* file-write* file-test-existence "
                "file-read-metadata file-map-executable)",
            ).replace(
                "(deny file-read*\n"
                '    (literal "/private/etc/master.passwd")\n'
                '    (literal "/private/etc/passwd"))\n',
                "",
            )
        if spec.proxy is not None:
            if spec.policy.network.enabled:
                allowed_endpoints = "\n".join(
                    (
                        f'(allow network-outbound (remote ip "localhost:{spec.proxy.http_port}"))',
                        f'(allow network-outbound (remote ip "localhost:{spec.proxy.socks_port}"))',
                    )
                )
                profile = profile.replace(
                    "(deny network*)",
                    f"(deny network*)\n{allowed_endpoints}",
                )
        if spec.policy.unix_sockets.mode == "allow_all":
            # socket(AF_UNIX, ...) is a system-socket operation without a path,
            # so the path/remote filters below cannot authorize creation.
            profile += (
                "\n(allow system-socket (socket-domain AF_UNIX))"
                "\n(allow network-outbound (remote unix-socket))\n"
            )
        else:
            escaped_sockets = "\n".join(
                f'(allow network-outbound (remote unix-socket (path-literal "{self._escape(Path(expand_path_rule(path)))}")))'
                for path in spec.policy.unix_sockets.allowed_paths
            )
            if escaped_sockets:
                profile += (
                    "\n(allow system-socket (socket-domain AF_UNIX))"
                    f"\n{escaped_sockets}\n"
                )

        ca_paths = tuple(
            path
            for path in (
                Path("/etc/ssl"),
                Path("/private/etc/ssl"),
                Path("/usr/local/share/ca-certificates"),
                Path("/System/Library/Keychains"),
                Path("/Library/Keychains"),
            )
            if path.exists()
        )
        custom_ca = sandbox_ca_file()
        if custom_ca is not None:
            ca_paths = (*ca_paths, custom_ca)
        if spec.proxy is not None:
            for path in ca_paths:
                profile += f'\n(allow file-read* (subpath "{self._escape(path)}"))\n'

        root_definitions: list[str] = []
        if spec.policy.filesystem_scope == "workspace":
            writable_roots = {root.resolve() for root in spec.writable_roots}
            readable_roots = {
                root.resolve()
                for root in (*spec.readable_roots, *spec.writable_roots)
                if root.is_dir()
            }
            for index, root in enumerate(sorted(readable_roots)):
                parameter = f"ALLOWED_ROOT_{index}"
                root_definitions.extend(("-D", f"{parameter}={root}"))
                operations = "file-read* file-map-executable"
                if root in writable_roots:
                    operations += " file-write*"
                profile += f'\n(allow {operations} (subpath (param "{parameter}")))\n'
            # Explicit denial also protects Python inside an otherwise writable root.
            profile += (
                '\n(deny file-write* (subpath (param "PYTHON_PREFIX")) '
                '(subpath (param "PYTHON_BASE_PREFIX")))\n'
            )

        executable_definitions: list[str] = []
        executable_rules: list[str] = []
        for index, read_path in enumerate(self._executable_read_paths(executable_path)):
            parameter = f"EXECUTABLE_{index}"
            executable_definitions.extend(("-D", f"{parameter}={read_path}"))
            executable_rules.append(f'(literal (param "{parameter}"))')
        profile = profile.replace(
            '(literal (param "EXECUTABLE"))',
            "\n    ".join(executable_rules),
        )

        for ca_path in ca_paths:
            selector = "subpath" if ca_path.is_dir() else "literal"
            profile += f'\n(deny file-write* ({selector} "{self._escape(ca_path)}"))\n'

        deny_rules = DenyRuleSet(spec.policy.filesystem)
        if not deny_rules.empty:
            try:
                denied = deny_rules.expand_for_launch()
            except DenyPolicyError as exc:
                raise RuntimeError(str(exc)) from exc
            for mask in denied:
                selector = "subpath" if mask.is_directory else "literal"
                path = self._escape(mask.target)
                operation = "file-read*" if mask.mode == "read" else "file-write*"
                profile += f'\n(deny {operation} ({selector} "{path}"))\n'

        if len(profile.encode("utf-8")) > _MAX_PROFILE_BYTES:
            raise RuntimeError("The Seatbelt profile exceeds its fixed size budget.")
        if profile.count("\n") > _MAX_PROFILE_RULES:
            raise RuntimeError("The Seatbelt profile exceeds its fixed rule budget.")
        bootstrap = [
            str(Path(sys.executable).resolve()),
            "-S",
            "-c",
            _BOOTSTRAP,
            str(workspace),
            str(workspace),
            "C.UTF-8",
            *argv,
        ]
        return [
            seatbelt_path,
            "-D",
            f"WORKSPACE={workspace}",
            *root_definitions,
            *executable_definitions,
            "-D",
            f"PYTHON_PREFIX={Path(sys.prefix).resolve()}",
            "-D",
            f"PYTHON_BASE_PREFIX={Path(sys.base_prefix).resolve()}",
            "-p",
            profile,
            *build_resource_limited_argv(bootstrap, spec.limits),
        ]

    @staticmethod
    def _escape(path: Path) -> str:
        """Escape a literal path for a Seatbelt string."""
        return (
            str(path)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    def _executable_read_paths(self, executable_path: Path) -> tuple[Path, ...]:
        """Collect executable and dynamic-library paths needed by Seatbelt.

        Args:
            executable_path: Executable launched inside Seatbelt.

        Returns:
            Existing absolute files that the dynamic loader may need to read.
        """
        read_paths = {executable_path, executable_path.resolve()}
        resolved_executable = executable_path.resolve()
        if any(
            resolved_executable.is_relative_to(root)
            for root in (
                Path("/bin"),
                Path("/usr"),
                Path(sys.prefix).resolve(),
                Path(sys.base_prefix).resolve(),
            )
        ):
            return tuple(sorted(read_paths, key=str))

        pending = [resolved_executable]
        inspected: set[Path] = set()
        while pending and len(inspected) < 64:
            current = pending.pop()
            if current in inspected:
                continue
            inspected.add(current)
            try:
                result = subprocess.run(  # noqa: S603  # argv is built internally; sandbox/blocklist is the boundary
                    ["/usr/bin/otool", "-L", str(current)],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            except OSError, subprocess.TimeoutExpired:
                continue
            if result.returncode != 0:
                continue
            for line in result.stdout.decode("utf-8", errors="replace").splitlines()[
                1:
            ]:
                dependency_text = line.strip().split(" (", 1)[0]
                if not dependency_text.startswith("/"):
                    continue
                dependency = Path(dependency_text)
                if not dependency.exists():
                    continue
                resolved_dependency = dependency.resolve()
                read_paths.update((dependency, resolved_dependency))
                if not (
                    resolved_dependency.is_relative_to("/usr")
                    or resolved_dependency.is_relative_to("/System")
                ):
                    pending.append(resolved_dependency)
        return tuple(sorted(read_paths, key=str))
