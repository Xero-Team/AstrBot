"""Unix socket, inherited descriptor and io_uring denial tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from astrbot.core.computer.local_policy import (
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.computer.process_sandbox import SandboxSpec, create_process_sandbox

pytestmark = pytest.mark.skipif(
    not (sys.platform.startswith("linux") or sys.platform == "darwin"),
    reason="Unix socket policy tests require Linux or macOS Seatbelt.",
)


def _spec(
    tmp_path: Path, *, scope: str = "workspace", mode: str = "deny"
) -> SandboxSpec:
    return SandboxSpec(
        workspace=tmp_path,
        policy=LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope=scope,  # type: ignore[arg-type]
            network=LocalNetworkPolicy(mode="off"),
            unix_sockets=LocalUnixSocketPolicy(mode=mode),  # type: ignore[arg-type]
        ),
    )


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux seccomp socket family checks run on Linux.",
)
def test_socketpair_and_io_uring_denied_in_workload(tmp_path: Path) -> None:
    code = """
import ctypes
import socket
try:
    socket.socketpair(socket.AF_UNIX)
except OSError as exc:
    print("socketpair", exc.errno)
else:
    raise SystemExit("socketpair allowed")
libc = ctypes.CDLL(None, use_errno=True)
result = libc.syscall(425, ctypes.c_uint(8), ctypes.c_void_p(0))
print("io_uring", result, ctypes.get_errno())
path = '/var/run/docker.sock'
try:
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.connect(path)
except OSError as exc:
    print("pathname", exc.errno)
else:
    raise SystemExit('docker socket reachable')
"""
    result = create_process_sandbox().run(
        [sys.executable, "-c", code],
        _spec(tmp_path, scope="host"),
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"socketpair 13" in result.stdout
    assert b"io_uring -1 13" in result.stdout
    # Host+off cannot create AF_UNIX at all, so the pathname conn fails at
    # socket creation with EACCES regardless of whether the socket exists.
    assert b"pathname 13" in result.stdout


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux allow_all uses no seccomp filter.",
)
def test_allow_all_does_not_install_a_socket_filter(tmp_path: Path) -> None:
    result = create_process_sandbox().run(
        [
            sys.executable,
            "-c",
            "import socket; a,b=socket.socketpair(); print('allowed')",
        ],
        _spec(tmp_path, mode="allow_all"),
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"allowed" in result.stdout


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Repeated bridge connections are Linux-specific.",
)
@pytest.mark.asyncio
async def test_bridge_keeps_working_after_workload_filter(tmp_path: Path) -> None:
    import http.server
    import socketserver
    import threading

    from astrbot.core.computer.booters.local import LocalShellComponent
    from astrbot.core.computer.process_sandbox.proxy import LocalProxyServer

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"bridge-open"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    origin = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    port = origin.server_address[1]
    proxy = LocalProxyServer(platform="linux")
    proxy.start()
    shell = LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        policy = LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="workspace",
            network=LocalNetworkPolicy(
                mode="allowlist",
                allowed_domains=(f"localhost:{port}",),
                allow_loopback=True,
            ),
            unix_sockets=LocalUnixSocketPolicy(mode="deny"),
        )
        result = await shell.exec_managed(
            "curl -sS --max-time 10 "
            f"http://localhost:{port}/one; curl -sS --max-time 10 "
            f"http://localhost:{port}/two",
            owner_id="bridge-repeat",
            sender_id="member",
            spec=SandboxSpec(workspace=tmp_path, policy=policy),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            timeout=30,
        )
        assert result["exit_code"] == 0, result
        assert result["stdout"].count("bridge-open") == 2
    finally:
        await shell.shutdown_sessions()
        await proxy.stop()
        origin.shutdown()
        origin.server_close()
