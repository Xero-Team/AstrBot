"""Linux proxy-only networking integration for sandboxed Local execution."""

from __future__ import annotations

import http.server
import shlex
import socketserver
import sys
import threading
from pathlib import Path

import pytest

from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import _attach_proxy_lease
from astrbot.core.computer.local_policy import (
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.computer.process_sandbox import SandboxProxyEndpoint, SandboxSpec
from astrbot.core.computer.process_sandbox.bridge import (
    BRIDGE_HTTP_PORT,
    BRIDGE_SOCKS_PORT,
)
from astrbot.core.computer.process_sandbox.proxy import LocalProxyServer

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux network namespace and bridge tests require Linux.",
)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"proxy-network-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _http_server() -> socketserver.TCPServer:
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _policy(port: int, *, mode: str = "allowlist") -> LocalSandboxPolicy:
    return LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(
            mode=mode,
            allowed_domains=(f"localhost:{port}",),
            allow_loopback=True,
        ),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )


async def _run(command: str, tmp_path: Path, proxy: LocalProxyServer, policy) -> dict:
    shell = local_booter.LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        return await shell.exec_managed(
            command,
            owner_id="network-test",
            sender_id="member",
            spec=SandboxSpec(workspace=tmp_path, policy=policy),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            timeout=30,
        )
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_allowed_http_succeeds_through_proxy_and_bypass_fails(tmp_path) -> None:
    origin = _http_server()
    port = origin.server_address[1]
    proxy = LocalProxyServer(platform="linux")
    proxy.start()
    try:
        result = await _run(
            f"curl -sS --max-time 10 http://localhost:{port}/",
            tmp_path,
            proxy,
            _policy(port),
        )
        assert result["exit_code"] == 0, result
        assert "proxy-network-ok" in result["stdout"]
        assert result["violations"] == []

        bypass = await _run(
            f"curl -sS --max-time 5 --noproxy '*' http://localhost:{port}/",
            tmp_path,
            proxy,
            _policy(port),
        )
        assert bypass["exit_code"] != 0
        assert "proxy-network-ok" not in bypass["stdout"]

        denied = await _run(
            f"curl -fsS --max-time 5 http://example.com:{port}/",
            tmp_path,
            proxy,
            _policy(port),
        )
        assert denied["exit_code"] != 0
        assert denied["violations"]
    finally:
        await proxy.stop()
        origin.shutdown()
        origin.server_close()


@pytest.mark.asyncio
async def test_direct_dns_and_host_loopback_egress_fail(tmp_path) -> None:
    origin = _http_server()
    port = origin.server_address[1]
    proxy = LocalProxyServer(platform="linux")
    proxy.start()
    try:
        code = (
            "import socket\n"
            "try:\n"
            "    socket.getaddrinfo('example.com', 443)\n"
            "except OSError:\n"
            "    print('dns-denied')\n"
            "else:\n"
            "    raise SystemExit('direct DNS succeeded')\n"
            f"try:\n"
            f"    socket.create_connection(('127.0.0.1', {port}), timeout=2)\n"
            "except OSError:\n"
            "    print('direct-ip-denied')\n"
            "else:\n"
            "    raise SystemExit('direct IP egress succeeded')\n"
        )
        result = await _run(
            shlex.join([sys.executable, "-c", code]),
            tmp_path,
            proxy,
            _policy(port),
        )
        assert result["exit_code"] == 0, result
        assert "dns-denied" in result["stdout"]
        assert "direct-ip-denied" in result["stdout"]
    finally:
        await proxy.stop()
        origin.shutdown()
        origin.server_close()


@pytest.mark.asyncio
async def test_caller_proxy_environment_cannot_override_policy(tmp_path) -> None:
    origin = _http_server()
    port = origin.server_address[1]
    proxy = LocalProxyServer(platform="linux")
    proxy.start()
    try:
        shell = local_booter.LocalShellComponent(proxy_provider=lambda: proxy)
        try:
            result = await shell.exec_managed(
                f"curl -sS --max-time 10 http://localhost:{port}/",
                owner_id="env-test",
                sender_id="member",
                spec=SandboxSpec(workspace=tmp_path, policy=_policy(port)),
                cwd=str(tmp_path),
                allowed_root=str(tmp_path),
                env={
                    "HTTP_PROXY": "http://127.0.0.1:9",
                    "http_proxy": "http://127.0.0.1:9",
                    "NO_PROXY": "*",
                    "no_proxy": "*",
                },
                timeout=30,
            )
            assert result["exit_code"] == 0, result
            assert "proxy-network-ok" in result["stdout"]
        finally:
            await shell.shutdown_sessions()
    finally:
        await proxy.stop()
        origin.shutdown()
        origin.server_close()


def test_proxy_token_is_inherited_but_not_in_launcher_argv(tmp_path) -> None:
    proxy = LocalProxyServer(platform="linux")
    proxy.start()
    try:
        spec = SandboxSpec(workspace=tmp_path, policy=_policy(12345))
        proxy_server, lease, effective = _attach_proxy_lease(spec, lambda: proxy)
        assert proxy_server is proxy and lease is not None
        command = local_booter.create_process_sandbox().build_command(
            [sys.executable, "-c", "pass"], effective
        )
        assert lease.token not in " ".join(command)
        environment = local_booter.create_process_sandbox()._launch_environment(
            effective, {}
        )
        assert environment["ASTRBOT_SANDBOX_PROXY_TOKEN"] == lease.token
        assert "--share-net" not in command
        assert str(proxy.http_socket) in command
        assert str(proxy.socks_socket) in command
        assert str(BRIDGE_HTTP_PORT) in command
        assert str(BRIDGE_SOCKS_PORT) in command
        proxy.drop_lease(lease)
    finally:
        proxy.shutdown()


def test_off_mode_uses_filter_without_proxy_sockets(tmp_path) -> None:
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="off"),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )
    command = local_booter.create_process_sandbox().build_command(
        ["/bin/true"], SandboxSpec(workspace=tmp_path, policy=policy)
    )
    assert "--share-net" not in command
    assert "astrbot-sandbox-proxy/http.sock" not in command
    assert any("bridge.py" in part for part in command)
    assert "--filter-only" in command


def test_host_scope_mounts_ca_stores_read_only(monkeypatch, tmp_path) -> None:
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("test", encoding="utf-8")
    monkeypatch.setenv("ASTRBOT_SANDBOX_CA_FILE", str(ca_file))
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="host",
        network=LocalNetworkPolicy(mode="unrestricted"),
        unix_sockets=LocalUnixSocketPolicy(mode="allow_all"),
    )
    command = local_booter.create_process_sandbox().build_command(
        ["/bin/true"],
        SandboxSpec(
            workspace=tmp_path,
            policy=policy,
            proxy=SandboxProxyEndpoint(
                token="test-token",
                http_socket=str(tmp_path / "http.sock"),
                socks_socket=str(tmp_path / "socks.sock"),
            ),
        ),
    )
    assert ["--ro-bind", str(ca_file), str(ca_file)] == command[
        command.index(str(ca_file)) - 1 : command.index(str(ca_file)) + 2
    ]
