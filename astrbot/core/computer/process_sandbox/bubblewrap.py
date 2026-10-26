from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .base import SandboxSpec, sandbox_ca_file
from .fs_policy import DenyPolicyError, DenyRuleSet
from .unix import UnixProcessSandbox, build_resource_limited_argv

_TMP_BYTES = 256 * 1024 * 1024
_SANDBOX_RUNTIME_ROOT = "/tmp/astrbot-sandbox-runtime"  # noqa: S108  # nosec B108


class BubblewrapProcessSandbox(UnixProcessSandbox):
    """Linux restricted-process launcher backed by bubblewrap."""

    _uses_bridge_ready_path = True

    @staticmethod
    def _ca_readonly_paths() -> tuple[Path, ...]:
        """Return existing CA stores that sandboxed clients must not write."""
        paths = [
            path
            for path in (
                Path("/etc/ssl"),
                Path("/etc/pki"),
                Path("/etc/ca-certificates"),
                Path("/usr/local/share/ca-certificates"),
            )
            if path.exists()
        ]
        ca_file = sandbox_ca_file()
        if ca_file is not None:
            paths.append(ca_file)
        return tuple(dict.fromkeys(paths))

    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
        *,
        ready_path: Path | None = None,
    ) -> list[str]:
        """Build the bubblewrap command for validated inputs."""
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            raise RuntimeError(
                "bubblewrap (`bwrap`) is required for restricted Local execution."
            )
        if not Path("/bin/sh").exists():
            raise RuntimeError("The Local bubblewrap sandbox requires /bin/sh.")
        if spec.policy.network.enabled and spec.proxy is None:
            raise RuntimeError(
                "Sandboxed network access requires the runtime Local proxy."
            )

        executable_path = (
            Path(argv[0]).resolve()
            if Path(argv[0]).is_absolute() and Path(argv[0]).exists()
            else Path(sys.executable).resolve()
        )
        command = [
            bwrap_path,
            "--unshare-all",
            "--new-session",
            "--die-with-parent",
        ]
        ca_paths = self._ca_readonly_paths()
        if spec.policy.filesystem_scope == "host":
            command.extend(
                (
                    "--bind",
                    "/",
                    "/",
                    "--proc",
                    "/proc",
                    "--dev",
                    "/dev",
                )
            )
            for path in ca_paths:
                command.extend(("--ro-bind", str(path), str(path)))
            command.extend(("--chdir", str(workspace)))
        else:
            command.extend(
                (
                    "--dir",
                    "/tmp",  # noqa: S108  # nosec B108
                    "--size",
                    str(_TMP_BYTES),
                    "--tmpfs",
                    "/tmp",  # noqa: S108  # nosec B108
                )
            )

        readonly_paths = {
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc/alternatives"),
            Path("/etc/ld.so.cache"),
            Path("/etc/ld.so.conf"),
            Path("/etc/ld.so.conf.d"),
            Path("/etc/localtime"),
            Path("/etc/nsswitch.conf"),
            Path("/etc/passwd"),
            Path("/etc/group"),
            Path(sys.prefix).resolve(),
            Path(sys.base_prefix).resolve(),
        }
        if spec.policy.filesystem_scope == "workspace":
            if spec.proxy is not None:
                readonly_paths.update(ca_paths)
            readonly_paths.update(root.resolve() for root in spec.readable_roots)
            writable_paths = {root.resolve() for root in spec.writable_roots}
            if spec.workspace_writable:
                writable_paths.add(workspace)
            else:
                readonly_paths.add(workspace)
            readonly_paths.difference_update(writable_paths)
            if not any(
                executable_path == path or executable_path.is_relative_to(path)
                for path in readonly_paths
            ):
                readonly_paths.add(executable_path)
            # Keep the venv entry point usable when uv links its interpreter
            # through a directory alias outside the mounted Python prefixes.
            pending = [Path(sys.executable)]
            seen_links: set[Path] = set()
            while pending:
                path = pending.pop()
                for link in (path, *path.parents):
                    if link in seen_links or not link.is_symlink():
                        continue
                    seen_links.add(link)
                    target = link.parent / link.readlink() / path.relative_to(link)
                    pending.append(Path(os.path.abspath(target)))
                    if not any(link.is_relative_to(root) for root in readonly_paths):
                        readonly_paths.add(link)
            readonly_paths = {path for path in readonly_paths if path.exists()}

            required_directories = {
                Path("/tmp"),  # noqa: S108  # nosec B108
                Path("/tmp/home"),  # noqa: S108  # nosec B108
            }
            for path in (*readonly_paths, *writable_paths):
                required_directories.update(
                    parent
                    for parent in path.parents
                    if parent != Path("/") and parent not in readonly_paths
                )
            for directory in sorted(
                required_directories,
                key=lambda path: len(path.parts),
            ):
                if directory != Path("/tmp"):  # noqa: S108  # nosec B108
                    command.extend(("--dir", str(directory)))
            command.extend(("--proc", "/proc", "--dev", "/dev"))

            for path in sorted(readonly_paths, key=lambda item: len(item.parts)):
                # Resolver files often link into /run. Bind their contents without
                # exposing the rest of the host service's runtime directory.
                if path.is_symlink():
                    command.extend(("--symlink", os.readlink(path), str(path)))
                else:
                    command.extend(("--ro-bind", str(path), str(path)))
            for path in sorted(writable_paths, key=lambda item: len(item.parts)):
                command.extend(("--bind", str(path), str(path)))
            # A writable workspace or attachment root must not make AstrBot's
            # Python installation writable when it contains that installation.
            for path in sorted(
                {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()},
                key=lambda item: len(item.parts),
            ):
                if any(
                    path.is_relative_to(root) or root.is_relative_to(path)
                    for root in writable_paths
                ):
                    command.extend(("--ro-bind", str(path), str(path)))
            command.extend(("--chdir", str(workspace)))

        needs_filter = spec.policy.unix_sockets.mode == "deny"
        if spec.proxy is not None or needs_filter:
            command.extend(self._bridge_mounts(spec, workspace))

        deny_rules = DenyRuleSet(spec.policy.filesystem)
        if not deny_rules.empty:
            try:
                masks = deny_rules.expand_for_launch()
            except DenyPolicyError as exc:
                raise RuntimeError(str(exc)) from exc
            command.extend(DenyRuleSet.bwrap_arguments(masks))

        for key, value in sorted(env.items()):
            command.extend(("--setenv", key, value))
        command.extend(
            (
                "--setenv",
                "PATH",
                f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin",
                "--setenv",
                "HOME",
                str(workspace)
                if spec.policy.filesystem_scope == "host"
                else "/tmp/home",  # noqa: S108  # nosec B108
                "--setenv",
                "TMPDIR",
                "/tmp",  # noqa: S108  # nosec B108
                "--setenv",
                "LANG",
                "C.UTF-8",
                "--",
                *self._workload_argv(argv, spec, ready_path),
            )
        )
        return command

    def _bridge_mounts(
        self,
        spec: SandboxSpec,
        workspace: Path,
    ) -> list[str]:
        """Mount dedicated proxy sockets and the bridge runner source."""
        proxy = spec.proxy
        runtime_root = _SANDBOX_RUNTIME_ROOT
        extra: list[str] = ["--tmpfs", runtime_root]
        if proxy is not None:
            if not proxy.http_socket or not proxy.socks_socket:
                raise RuntimeError("The sandbox proxy did not expose Unix sockets.")
            extra.extend(
                (
                    "--ro-bind",
                    proxy.http_socket,
                    f"{_SANDBOX_RUNTIME_ROOT}/http.sock",  # noqa: S108  # nosec B108
                    "--ro-bind",
                    proxy.socks_socket,
                    f"{_SANDBOX_RUNTIME_ROOT}/socks.sock",  # noqa: S108  # nosec B108
                )
            )
        extra.extend(
            (
                "--ro-bind",
                str(Path(__file__).resolve().parent),
                f"{_SANDBOX_RUNTIME_ROOT}/bridge",  # noqa: S108  # nosec B108
            )
        )
        return extra

    def _workload_argv(
        self,
        argv: list[str],
        spec: SandboxSpec,
        ready_path: Path | None,
    ) -> list[str]:
        """Build either the direct workload or the unfiltered bridge runner."""
        if spec.proxy is None:
            if spec.policy.unix_sockets.mode != "deny":
                return build_resource_limited_argv(argv, spec.limits)
            filter_argv = [
                str(sys.executable),
                "-I",
                "-S",
                f"{_SANDBOX_RUNTIME_ROOT}/bridge/bridge.py",  # noqa: S108  # nosec B108
                "--filter-only",
                "--sockets",
                spec.policy.unix_sockets.mode,
                "--",
                *argv,
            ]
            return build_resource_limited_argv(filter_argv, spec.limits)
        if ready_path is None:
            raise RuntimeError("The sandbox bridge readiness path is missing.")
        bridge_argv = [
            str(sys.executable),
            "-I",
            "-S",
            f"{_SANDBOX_RUNTIME_ROOT}/bridge/bridge.py",  # noqa: S108  # nosec B108
            "--http-socket",
            f"{_SANDBOX_RUNTIME_ROOT}/http.sock",  # noqa: S108  # nosec B108
            "--socks-socket",
            f"{_SANDBOX_RUNTIME_ROOT}/socks.sock",  # noqa: S108  # nosec B108
            "--http-port",
            str(spec.proxy.http_port),
            "--socks-port",
            str(spec.proxy.socks_port),
            "--ready-file",
            str(ready_path),
            "--sockets",
            spec.policy.unix_sockets.mode,
            "--",
            *argv,
        ]
        return build_resource_limited_argv(bridge_argv, spec.limits)
