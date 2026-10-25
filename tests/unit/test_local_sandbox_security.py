"""OS-parameterized Local sandbox security matrix.

CI runs this module directly on Linux and macOS and fails when the designated
integration cases are skipped. The backend prerequisite assertion below makes
an all-skip run impossible on those runners.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from astrbot.core.computer.booters.local import LocalShellComponent
from astrbot.core.computer.local_policy import (
    LocalFilesystemPolicy,
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.computer.process_sandbox import (
    SandboxSpec,
    create_process_sandbox,
    detect_local_runtime_info,
)
from astrbot.core.computer.process_sandbox.proxy import LocalProxyServer

pytestmark = pytest.mark.skipif(
    not (
        (sys.platform.startswith("linux") and shutil.which("bwrap"))
        or (sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists())
    ),
    reason="Requires the verified Local sandbox backend for this OS.",
)


def test_ci_backend_is_available() -> None:
    if not os.environ.get("CI"):
        pytest.skip("The backend prerequisite is asserted in CI.")
    info = detect_local_runtime_info()
    assert info["sandbox"]["status"] == "detected", info


def _policy(
    *,
    scope: str = "workspace",
    network: str = "off",
    allowed_domains: tuple[str, ...] = (),
    deny_read: tuple[str, ...] = (),
    deny_write: tuple[str, ...] = (),
) -> LocalSandboxPolicy:
    return LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope=scope,  # type: ignore[arg-type]
        network=LocalNetworkPolicy(
            mode=network,  # type: ignore[arg-type]
            allowed_domains=allowed_domains,
            allow_loopback=True,
        ),
        filesystem=LocalFilesystemPolicy(
            deny_read=deny_read,
            deny_write=deny_write,
        ),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )


class _Origin:
    def __init__(self) -> None:
        self.server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        await reader.readuntil(b"\r\n\r\n")
        body = b"sandbox-matrix-ok"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()


async def _shell_result(
    tmp_path: Path,
    proxy: LocalProxyServer,
    policy: LocalSandboxPolicy,
    command: str,
    *,
    env: dict[str, str] | None = None,
) -> dict:
    shell = LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        return await shell.exec_managed(
            command,
            owner_id="security-matrix",
            sender_id="member",
            spec=SandboxSpec(workspace=tmp_path, policy=policy),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            env=env,
            timeout=30,
        )
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_allowed_http_and_denied_domain(tmp_path: Path) -> None:
    origin = _Origin()
    await origin.start()
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    try:
        allowed = await _shell_result(
            tmp_path,
            proxy,
            _policy(
                network="allowlist",
                allowed_domains=(f"localhost:{origin.port}",),
            ),
            f"curl -sS --max-time 10 http://localhost:{origin.port}/",
        )
        assert allowed["exit_code"] == 0, allowed
        assert "sandbox-matrix-ok" in allowed["stdout"]

        denied = await _shell_result(
            tmp_path,
            proxy,
            _policy(
                network="allowlist",
                allowed_domains=(f"localhost:{origin.port}",),
            ),
            f"curl -fsS --max-time 5 http://denied.example:{origin.port}/",
        )
        assert denied["exit_code"] != 0
        assert denied["violations"]
    finally:
        await proxy.stop()
        await origin.stop()


@pytest.mark.asyncio
async def test_direct_host_loopback_is_blocked_by_proxy_mode(tmp_path: Path) -> None:
    listener = await asyncio.start_server(lambda _r, _w: None, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    try:
        result = await _shell_result(
            tmp_path,
            proxy,
            _policy(network="allowlist", allowed_domains=("example.com",)),
            shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import socket\n"
                    f"try:\n socket.create_connection(('127.0.0.1', {port}), timeout=2)\n"
                    "except OSError:\n print('direct-denied')\n"
                    "else:\n raise SystemExit('direct egress succeeded')\n",
                ]
            ),
        )
        assert result["exit_code"] == 0, result
        assert "direct-denied" in result["stdout"]
    finally:
        await proxy.stop()
        listener.close()
        await listener.wait_closed()


@pytest.mark.skipif(
    sys.platform.startswith("linux"),
    reason="macOS Seatbelt exercises this path in its own CI lane.",
)
def test_socket_deny_blocks_unix_sockets_on_macos(tmp_path: Path) -> None:
    code = (
        "import socket, tempfile, os\n"
        "path = os.path.join(tempfile.mkdtemp(), 'sock')\n"
        "try:\n"
        "    server = socket.socket(socket.AF_UNIX)\n"
        "    server.bind(path)\n"
        "except OSError:\n"
        "    print('unix-denied')\n"
        "else:\n"
        "    raise SystemExit('unix socket allowed')\n"
    )
    result = create_process_sandbox().run(
        [sys.executable, "-c", code],
        SandboxSpec(workspace=tmp_path, policy=_policy()),
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"unix-denied" in result.stdout


@pytest.mark.asyncio
async def test_filesystem_denies_apply_on_the_active_backend(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    code = f"""
from pathlib import Path
try:
    print(Path({str(secret)!r}).read_text())
except OSError:
    print('denied')
"""
    result = create_process_sandbox().run(
        [sys.executable, "-c", code],
        SandboxSpec(
            workspace=tmp_path,
            policy=_policy(deny_read=(str(secret),)),
        ),
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"TOPSECRET" not in result.stdout
    assert b"denied" in result.stdout


@pytest.mark.asyncio
async def test_natural_completion_releases_lease_without_another_poll(
    tmp_path: Path,
) -> None:
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    shell = LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        policy = _policy(network="allowlist", allowed_domains=("example.com",))
        result = await shell.exec_managed(
            shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(0.3); print('done')",
                ]
            ),
            owner_id="lease-test",
            sender_id="member",
            spec=SandboxSpec(workspace=tmp_path, policy=policy),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            yield_time_ms=0,
        )
        session = shell._sessions[result["session_id"]]  # noqa: SLF001
        await asyncio.wait_for(asyncio.shield(session.wait_task), 10)
        for _ in range(200):
            if session.lease_released:
                break
            await asyncio.sleep(0.01)
        assert session.lease_released is True
        assert session.lease is not None
        assert session.lease.snapshot_violations() == []
        assert proxy._leases == {}  # noqa: SLF001
    finally:
        await shell.shutdown_sessions()
        await proxy.stop()


@pytest.mark.asyncio
async def test_missing_runtime_proxy_fails_closed(tmp_path: Path) -> None:
    shell = LocalShellComponent(proxy_provider=None)
    policy = _policy(network="allowlist", allowed_domains=("example.com",))
    with pytest.raises(RuntimeError, match="proxy"):
        await shell.exec_managed(
            "true",
            owner_id="missing-proxy",
            spec=SandboxSpec(workspace=tmp_path, policy=policy),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
        )
    await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_verified_local_tls_succeeds_and_untrusted_ca_fails(
    monkeypatch, tmp_path: Path
) -> None:
    import datetime as dt
    import ipaddress
    import ssl

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    now = dt.datetime.now(dt.UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AstrBot Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path = tmp_path / "server.pem"
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path = tmp_path / "server.key"
    key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))

    async def tls_handler(reader, writer) -> None:
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            assert request.startswith(b"GET ")
            body = b"tls-ok"
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + body
            )
            await writer.drain()
        finally:
            writer.close()

    server = await asyncio.start_server(tls_handler, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    try:
        monkeypatch.setenv("ASTRBOT_SANDBOX_CA_FILE", str(ca_path))
        success = await _shell_result(
            tmp_path,
            proxy,
            _policy(network="allowlist", allowed_domains=(f"localhost:{port}",)),
            f"curl -sS --max-time 10 https://localhost:{port}/",
        )
        assert success["exit_code"] == 0, success
        assert "tls-ok" in success["stdout"]

        monkeypatch.delenv("ASTRBOT_SANDBOX_CA_FILE")
        failure = await _shell_result(
            tmp_path,
            proxy,
            _policy(network="allowlist", allowed_domains=(f"localhost:{port}",)),
            f"curl -sS --max-time 10 https://localhost:{port}/",
        )
        assert failure["exit_code"] != 0
        assert "tls-ok" not in failure["stdout"]
    finally:
        await proxy.stop()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_timeout_releases_lease_and_keeps_snapshot(tmp_path: Path) -> None:
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    shell = LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        result = await shell.exec_managed(
            shlex.join([sys.executable, "-c", "import time; time.sleep(5)"]),
            owner_id="timeout-test",
            sender_id="member",
            spec=SandboxSpec(
                workspace=tmp_path,
                policy=_policy(network="allowlist", allowed_domains=("example.com",)),
            ),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            timeout=1,
            yield_time_ms=0,
        )
        session = shell._sessions[result["session_id"]]  # noqa: SLF001
        for _ in range(300):
            if session.lease_released and session.process.returncode is not None:
                break
            await asyncio.sleep(0.01)
        assert session.lease_released is True
        assert session.lease is not None
        assert proxy._leases == {}  # noqa: SLF001
    finally:
        await shell.shutdown_sessions()
        await proxy.stop()


@pytest.mark.asyncio
async def test_cancelled_spawn_releases_lease(tmp_path: Path, monkeypatch) -> None:
    class CancellingSandbox:
        async def spawn_shell(self, *_args, **_kwargs):
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "astrbot.core.computer.booters.local.create_process_sandbox",
        lambda: CancellingSandbox(),
    )
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    shell = LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        with pytest.raises(asyncio.CancelledError):
            await shell.exec_managed(
                "true",
                owner_id="cancel-test",
                sender_id="member",
                spec=SandboxSpec(
                    workspace=tmp_path,
                    policy=_policy(
                        network="allowlist", allowed_domains=("example.com",)
                    ),
                ),
                cwd=str(tmp_path),
                allowed_root=str(tmp_path),
            )
        assert proxy._leases == {}  # noqa: SLF001
    finally:
        await shell.shutdown_sessions()
        await proxy.stop()


@pytest.mark.asyncio
async def test_denied_write_blocks_modification_rename_and_delete(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    backup = tmp_path / "backup.txt"
    code = f"""
from pathlib import Path
secret = Path({str(secret)!r})
backup = Path({str(backup)!r})
for operation in ("write", "rename", "delete"):
    try:
        if operation == "write":
            secret.write_text("changed")
        elif operation == "rename":
            secret.rename(backup)
        else:
            secret.unlink()
    except OSError:
        print("denied", operation)
    else:
        raise SystemExit("write denial bypassed: " + operation)
"""
    result = create_process_sandbox().run(
        [sys.executable, "-c", code],
        SandboxSpec(
            workspace=tmp_path,
            policy=_policy(deny_write=(str(secret),)),
        ),
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"denied write" in result.stdout
    assert b"denied rename" in result.stdout
    assert b"denied delete" in result.stdout
    assert secret.read_text() == "TOPSECRET"
    assert not backup.exists()


@pytest.mark.asyncio
async def test_final_snapshot_survives_until_output_is_polled(tmp_path: Path) -> None:
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    shell = LocalShellComponent(proxy_provider=lambda: proxy)
    try:
        result = await shell.exec_managed(
            shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(1); print('done')",
                ]
            ),
            owner_id="snapshot-test",
            sender_id="member",
            spec=SandboxSpec(
                workspace=tmp_path,
                policy=_policy(network="allowlist", allowed_domains=("example.com",)),
            ),
            cwd=str(tmp_path),
            allowed_root=str(tmp_path),
            yield_time_ms=0,
        )
        session = shell._sessions[result["session_id"]]  # noqa: SLF001
        await asyncio.wait_for(session.wait_task, 10)
        assert session.lease_released is True
        final = await shell.poll_session(
            owner_id="snapshot-test",
            sender_id="member",
            session_id=result["session_id"],
        )
        assert final["status"] == "completed"
        assert "done" in final["stdout"]
        assert final.get("violations") == []
    finally:
        await shell.shutdown_sessions()
        await proxy.stop()


@pytest.mark.asyncio
async def test_redirect_target_is_reauthorized(tmp_path: Path) -> None:
    async def redirect(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        body = b"redirecting"
        writer.write(
            b"HTTP/1.1 302 Found\r\nLocation: http://blocked.example:9/\r\n"
            b"Content-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(redirect, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    proxy = LocalProxyServer(platform=sys.platform)
    proxy.start()
    try:
        result = await _shell_result(
            tmp_path,
            proxy,
            _policy(network="allowlist", allowed_domains=(f"localhost:{port}",)),
            f"curl -fsSL --max-time 10 http://localhost:{port}/",
        )
        assert result["exit_code"] != 0
        assert result["violations"]
        assert all(
            "blocked.example" not in str(violation) or violation["kind"] == "network"
            for violation in result["violations"]
        )
    finally:
        await proxy.stop()
        server.close()
        await server.wait_closed()
