"""Authenticated Local proxy protocol, bounds and revocation."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
from collections.abc import AsyncIterator

import pytest

from astrbot.core.computer.local_policy import (
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.computer.process_sandbox.proxy import (
    MAX_LEASES,
    LocalProxyServer,
    ProxyLimitError,
    ProxyProtocolError,
    _format_authority,
    _request_body_framing,
    parse_http_request_head,
    parse_proxy_authorization,
    parse_socks_auth,
    parse_socks_connect_request,
    parse_socks_greeting,
)

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="Proxy protocol tests require POSIX Unix sockets."
)


def _policy(port: int | None = None) -> LocalSandboxPolicy:
    domains = (f"localhost:{port}",) if port is not None else ("example.com:80",)
    return LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(
            mode="allowlist",
            allowed_domains=domains,
            allow_loopback=True,
        ),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )


def _authorization(token: str) -> bytes:
    return b"Basic " + base64.b64encode(f"{token}:".encode())


class OriginServer:
    def __init__(self) -> None:
        self.server: asyncio.AbstractServer | None = None
        self.port = 0
        self.requests: list[bytes] = []

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        self.requests.append(head)
        body = b"origin-response"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()


@contextlib.asynccontextmanager
async def _proxy() -> AsyncIterator[LocalProxyServer]:
    server = LocalProxyServer(platform="linux")
    server.start()
    try:
        yield server
    finally:
        await server.stop()


async def _http_request(
    socket_path: str,
    request: bytes,
) -> bytes:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write(request)
    await writer.drain()
    data = await reader.read(-1)
    writer.close()
    await writer.wait_closed()
    return data


def test_format_authority_brackets_ipv6_hosts() -> None:
    assert _format_authority("example.com", 80) == "example.com:80"
    assert _format_authority("2001:db8::1", 8080) == "[2001:db8::1]:8080"


def test_parse_authorization_and_protocol_helpers() -> None:
    token = "token-value"
    assert parse_proxy_authorization(_authorization(token)) == token
    assert parse_proxy_authorization(b"Bearer token") is None
    assert parse_proxy_authorization(b"Basic !!!") is None
    head = parse_http_request_head(
        b"GET http://example.com/path HTTP/1.1\r\nHost: example.com\r\n\r\n"
    )
    assert head.method == "GET"
    assert head.target.endswith("/path")
    with pytest.raises(ProxyProtocolError):
        parse_http_request_head(
            b"POST http://example.com/ HTTP/1.1\r\n"
            b"Content-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n"
        )
    with pytest.raises(ProxyProtocolError):
        parse_http_request_head(b"GET / HTTP/1.1\r\n" + b"X: y\r\n" * 200 + b"\r\n")
    with pytest.raises(ProxyProtocolError):
        parse_http_request_head(b"GET / HTTP/1.1\r\nX: a\nb\r\n\r\n")
    with pytest.raises(ProxyProtocolError):
        parse_http_request_head(b"GET /\x00 HTTP/1.1\r\n\r\n")
    with pytest.raises(ProxyProtocolError):
        parse_http_request_head(
            b"POST / HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\n"
        )
    with pytest.raises(ProxyProtocolError):
        parse_http_request_head(b"POST / HTTP/1.1\r\nContent-Length: 1\xff2\r\n\r\n")
    unsupported_te = parse_http_request_head(
        b"POST http://example.com/ HTTP/1.1\r\nTransfer-Encoding: identity\r\n\r\n"
    )
    with pytest.raises(ProxyProtocolError):
        _request_body_framing(unsupported_te)
    version, methods = parse_socks_greeting(b"\x05\x01\x02")
    assert version == 5 and methods == b"\x02"
    assert parse_socks_auth(b"\x01\x05token\x00") == ("token", "")
    assert parse_socks_connect_request(1, 3, b"example.com", 443) == (
        "example.com",
        443,
    )
    with pytest.raises(ProxyProtocolError):
        parse_socks_connect_request(2, 3, b"example.com", 443)


@pytest.mark.asyncio
async def test_http_proxy_auth_forwarding_and_loopback_policy() -> None:
    origin = OriginServer()
    await origin.start()
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(origin.port))
            request = (
                f"GET http://localhost:{origin.port}/demo HTTP/1.1\r\n"
                f"Host: localhost:{origin.port}\r\n"
                f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n"
                "Proxy-Connection: keep-alive\r\n\r\n"
            ).encode()
            response = await _http_request(str(server.http_socket), request)
            assert b"200 OK" in response
            assert b"origin-response" in response
            assert origin.requests
            assert b"Proxy-Authorization" not in origin.requests[0]
            assert b"Proxy-Connection" not in origin.requests[0]

            missing = request.replace(
                f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n".encode(),
                b"",
            )
            denied = await _http_request(str(server.http_socket), missing)
            assert b"407" in denied
            server.drop_lease(lease)
    finally:
        await origin.stop()


@pytest.mark.asyncio
async def test_http_proxy_preserves_client_half_close() -> None:
    seen = b""

    async def origin(reader, writer) -> None:
        nonlocal seen
        seen = await reader.read(-1)
        body = b"half-close-response"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(port))
            reader, writer = await asyncio.open_unix_connection(str(server.http_socket))
            request = (
                f"POST http://localhost:{port}/upload HTTP/1.0\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n\r\n"
                "body-bytes"
            ).encode()
            writer.write(request)
            await writer.drain()
            writer.write_eof()
            response = await asyncio.wait_for(reader.read(-1), 5)
            assert b"200 OK" in response
            assert b"half-close-response" in response
            assert seen.endswith(b"body-bytes")
            writer.close()
            await writer.wait_closed()
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()


@pytest.mark.asyncio
async def test_http_proxy_slow_body_keeps_the_idle_timer_alive(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.proxy.IDLE_TUNNEL_SECONDS",
        0.5,
    )
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.proxy._IDLE_CHECK_SECONDS",
        0.02,
    )

    async def origin(reader, writer) -> None:
        await reader.readuntil(b"\r\n\r\n")
        await reader.readexactly(10)
        body = b"slow-upload-ok"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(port))
            reader, writer = await asyncio.open_unix_connection(str(server.http_socket))
            writer.write(
                (
                    f"POST http://localhost:{port}/upload HTTP/1.1\r\n"
                    f"Host: localhost:{port}\r\n"
                    f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n"
                    "Content-Length: 10\r\n\r\n"
                ).encode()
            )
            await writer.drain()
            for _ in range(10):
                await asyncio.sleep(0.1)
                writer.write(b"x")
                await writer.drain()
            response = await asyncio.wait_for(reader.read(-1), 5)
            assert b"200 OK" in response
            assert b"slow-upload-ok" in response
            writer.close()
            await writer.wait_closed()
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()


@pytest.mark.asyncio
async def test_http_proxy_rejects_denied_targets_and_bad_framing() -> None:
    async with _proxy() as server:
        lease = server.create_lease(_policy())
        auth = _authorization(lease.token).decode()
        denied = await _http_request(
            str(server.http_socket),
            (
                "GET http://169.254.169.254/latest HTTP/1.1\r\n"
                f"Host: 169.254.169.254\r\n"
                f"Proxy-Authorization: {auth}\r\n\r\n"
            ).encode(),
        )
        assert b"403" in denied
        mismatch = await _http_request(
            str(server.http_socket),
            (
                "GET http://example.com/ HTTP/1.1\r\n"
                f"Host: other.example\r\n"
                f"Proxy-Authorization: {auth}\r\n\r\n"
            ).encode(),
        )
        assert b"400" in mismatch or b"403" in mismatch
        https_form = await _http_request(
            str(server.http_socket),
            (
                "GET https://example.com/ HTTP/1.1\r\n"
                f"Host: example.com\r\n"
                f"Proxy-Authorization: {auth}\r\n\r\n"
            ).encode(),
        )
        assert b"403" in https_form
        server.drop_lease(lease)


@pytest.mark.asyncio
async def test_socks5_authenticated_connect_and_revocation() -> None:
    origin = OriginServer()
    await origin.start()
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(origin.port))
            reader, writer = await asyncio.open_unix_connection(
                str(server.socks_socket)
            )
            writer.write(b"\x05\x01\x02")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x05\x02"
            token = lease.token.encode()
            writer.write(b"\x01" + bytes([len(token)]) + token + b"\x00")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x01\x00"
            host = b"localhost"
            writer.write(
                b"\x05\x01\x00\x03"
                + bytes([len(host)])
                + host
                + origin.port.to_bytes(2, "big")
            )
            await writer.drain()
            reply = await reader.readexactly(10)
            assert reply[:2] == b"\x05\x00"
            writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.readuntil(b"origin-response"), 5)
            assert b"origin-response" in data
            server.drop_lease(lease)
            writer.close()
            await writer.wait_closed()
    finally:
        await origin.stop()


@pytest.mark.asyncio
async def test_connect_closes_upstream_when_relay_never_runs(
    monkeypatch,
) -> None:
    closed = asyncio.Event()

    async def origin(reader, writer):
        await reader.read(-1)
        closed.set()
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    async with _proxy() as server:

        async def fail_relay(*_args, **_kwargs):
            raise RuntimeError("relay failure")

        monkeypatch.setattr(server, "_relay", fail_relay)
        lease = server.create_lease(_policy(port))
        response = await _http_request(
            str(server.http_socket),
            (
                f"CONNECT localhost:{port} HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n\r\n"
            ).encode(),
        )
        assert b"200 Connection Established" in response
        await asyncio.wait_for(closed.wait(), 2)
    listener.close()
    await listener.wait_closed()


def test_global_connection_cap_counts_unauthenticated_slots(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.proxy.MAX_CONNECTIONS_GLOBAL",
        2,
    )
    server = LocalProxyServer(platform="linux")
    assert server._reserve_global(authenticated=False)  # noqa: SLF001
    assert server._reserve_global(authenticated=True)  # noqa: SLF001
    assert not server._reserve_global(authenticated=True)  # noqa: SLF001


@pytest.mark.asyncio
async def test_connect_does_not_write_http_error_after_tunnel_start(
    monkeypatch,
) -> None:
    async def origin(reader, writer):
        await reader.read(-1)
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:

            async def fail_relay(*_args, **_kwargs):
                raise RuntimeError("relay failure")

            monkeypatch.setattr(server, "_relay", fail_relay)
            lease = server.create_lease(_policy(port))
            response = await _http_request(
                str(server.http_socket),
                (
                    f"CONNECT localhost:{port} HTTP/1.1\r\n"
                    f"Host: localhost:{port}\r\n"
                    f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n\r\n"
                ).encode(),
            )
            assert response == (
                b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: AstrBot\r\n\r\n"
            )
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()


@pytest.mark.asyncio
async def test_lease_registry_is_bounded_and_stops_cleanly() -> None:
    async with _proxy() as server:
        leases = [server.create_lease(_policy()) for _ in range(MAX_LEASES)]
        with pytest.raises(ProxyLimitError):
            server.create_lease(_policy())
        for lease in leases:
            server.drop_lease(lease)
        assert server.state == "running"
    assert server.state == "stopped"
    with pytest.raises(RuntimeError):
        server.start()


@pytest.mark.asyncio
async def test_stop_before_start_and_double_stop_are_safe() -> None:
    server = LocalProxyServer(platform="linux")
    await server.stop()
    assert server.state == "stopped"
    await server.stop()
    assert server.state == "stopped"


@pytest.mark.asyncio
async def test_revoke_closes_live_connect_tunnel() -> None:
    accepted = asyncio.Event()
    release = asyncio.Event()

    async def hold(reader, writer):
        accepted.set()
        await release.wait()
        writer.close()

    listener = await asyncio.start_server(hold, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    async with _proxy() as server:
        lease = server.create_lease(_policy(port))
        reader, writer = await asyncio.open_unix_connection(str(server.http_socket))
        writer.write(
            (
                f"CONNECT localhost:{port} HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n\r\n"
            ).encode()
        )
        await writer.drain()
        assert b"200 Connection Established" in await reader.readuntil(b"\r\n\r\n")
        await asyncio.wait_for(accepted.wait(), 5)
        lease.revoke("test revocation")
        assert await asyncio.wait_for(reader.read(), 5) == b""
        writer.close()
        await writer.wait_closed()
        release.set()
    listener.close()
    await listener.wait_closed()


@pytest.mark.asyncio
async def test_concurrent_leases_isolate_tokens_and_policies() -> None:
    first = OriginServer()
    second = OriginServer()
    await first.start()
    await second.start()
    try:
        async with _proxy() as server:
            lease_first = server.create_lease(_policy(first.port))
            lease_second = server.create_lease(_policy(second.port))

            def request(lease, port: int) -> bytes:
                return (
                    f"GET http://localhost:{port}/ HTTP/1.1\r\n"
                    f"Host: localhost:{port}\r\n"
                    f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n\r\n"
                ).encode()

            allowed = await _http_request(
                str(server.http_socket), request(lease_first, first.port)
            )
            assert b"200 OK" in allowed
            denied = await _http_request(
                str(server.http_socket), request(lease_first, second.port)
            )
            assert b"403" in denied

            server.drop_lease(lease_first)
            revoked = await _http_request(
                str(server.http_socket), request(lease_first, first.port)
            )
            assert b"407" in revoked
            still_allowed = await _http_request(
                str(server.http_socket), request(lease_second, second.port)
            )
            assert b"200 OK" in still_allowed
            server.drop_lease(lease_second)
    finally:
        await first.stop()
        await second.stop()


@pytest.mark.asyncio
async def test_stop_removes_sockets_thread_and_is_safe_when_concurrent() -> None:
    server = LocalProxyServer(platform="linux")
    server.start()
    http_socket = server.http_socket
    socks_socket = server.socks_socket
    assert http_socket is not None and socks_socket is not None
    await asyncio.gather(server.stop(), server.stop())
    assert server.state == "stopped"
    assert server._thread is None  # noqa: SLF001
    assert not http_socket.exists()
    assert not socks_socket.exists()


@pytest.mark.asyncio
async def test_http_proxy_does_not_forward_pipelined_credentials() -> None:
    received: list[bytes] = []

    async def origin(reader, writer) -> None:
        received.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        received.append(await reader.read(-1))
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(port))
            auth = _authorization(lease.token).decode()
            reader, writer = await asyncio.open_unix_connection(str(server.http_socket))
            first = (
                f"GET http://localhost:{port}/one HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {auth}\r\n\r\n"
            )
            second = (
                f"GET http://localhost:{port}/two HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {auth}\r\n\r\n"
            )
            writer.write((first + second).encode())
            await writer.drain()
            response = await asyncio.wait_for(reader.read(-1), 5)
            assert b"200 OK" in response
            writer.close()
            await writer.wait_closed()
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()
    assert len(received) == 2
    assert b"Proxy-Authorization" not in received[0]
    assert received[1] == b""


@pytest.mark.asyncio
async def test_http_proxy_forwards_only_the_declared_request_body() -> None:
    received: list[bytes] = []

    async def origin(reader, writer) -> None:
        received.append(await reader.readuntil(b"\r\n\r\n"))
        received.append(await reader.read(-1))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(port))
            auth = _authorization(lease.token).decode()
            reader, writer = await asyncio.open_unix_connection(str(server.http_socket))
            body = b"hello"
            head = (
                f"POST http://localhost:{port}/upload HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {auth}\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode()
            pipelined = (
                f"GET http://localhost:{port}/two HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {auth}\r\n\r\n"
            ).encode()
            writer.write(head + body + pipelined)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(-1), 5)
            assert b"200 OK" in response
            writer.close()
            await writer.wait_closed()
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()
    assert len(received) == 2
    assert received[1] == body


@pytest.mark.asyncio
async def test_http_proxy_forwards_chunked_request_body() -> None:
    received: list[bytes] = []

    async def origin(reader, writer) -> None:
        received.append(await reader.readuntil(b"\r\n\r\n"))
        received.append(await reader.read(-1))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:
            lease = server.create_lease(_policy(port))
            auth = _authorization(lease.token).decode()
            reader, writer = await asyncio.open_unix_connection(str(server.http_socket))
            body = b"5\r\nhello\r\n0\r\n\r\n"
            head = (
                f"POST http://localhost:{port}/upload HTTP/1.1\r\n"
                f"Host: localhost:{port}\r\n"
                f"Proxy-Authorization: {auth}\r\n"
                "Transfer-Encoding: chunked\r\n\r\n"
            ).encode()
            writer.write(head + body)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(-1), 5)
            assert b"200 OK" in response
            writer.close()
            await writer.wait_closed()
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()
    assert received[1] == body


@pytest.mark.asyncio
async def test_stalled_handshakes_release_unauthenticated_slots(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.proxy.READINESS_TIMEOUT_SECONDS",
        0.2,
    )
    async with _proxy() as server:
        socks_reader, socks_writer = await asyncio.open_unix_connection(
            str(server.socks_socket)
        )
        socks_writer.write(b"\x05\x01\x02")
        await socks_writer.drain()
        assert await socks_reader.readexactly(2) == b"\x05\x02"
        socks_writer.write(b"\x01\xff")
        await socks_writer.drain()
        http_reader, http_writer = await asyncio.open_unix_connection(
            str(server.http_socket)
        )
        http_writer.write(b"GET http://example.com/ HTTP/1.1\r\n")
        await http_writer.drain()
        for _ in range(100):
            if server._unauthenticated_connections == 0:  # noqa: SLF001
                break
            await asyncio.sleep(0.05)
        assert server._unauthenticated_connections == 0  # noqa: SLF001
        assert await asyncio.wait_for(socks_reader.read(), 2)
        assert await asyncio.wait_for(http_reader.read(), 2)
        socks_writer.close()
        http_writer.close()


@pytest.mark.asyncio
async def test_socks_connect_does_not_write_reply_after_success(
    monkeypatch,
) -> None:
    async def origin(reader, writer) -> None:
        await reader.read(-1)
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:

            async def fail_relay(*_args, **_kwargs):
                raise RuntimeError("relay failure")

            monkeypatch.setattr(server, "_relay", fail_relay)
            lease = server.create_lease(_policy(port))
            reader, writer = await asyncio.open_unix_connection(
                str(server.socks_socket)
            )
            writer.write(b"\x05\x01\x02")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x05\x02"
            token = lease.token.encode()
            writer.write(b"\x01" + bytes([len(token)]) + token + b"\x00")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x01\x00"
            host = b"localhost"
            writer.write(
                b"\x05\x01\x00\x03"
                + bytes([len(host)])
                + host
                + port.to_bytes(2, "big")
            )
            await writer.drain()
            reply = await reader.readexactly(10)
            assert reply[:2] == b"\x05\x00"
            assert await asyncio.wait_for(reader.read(), 2) == b""
            writer.close()
            await writer.wait_closed()
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()


@pytest.mark.asyncio
async def test_http_relay_failure_does_not_inject_proxy_error(monkeypatch) -> None:
    async def origin(reader, writer) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(origin, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        async with _proxy() as server:

            async def fail_relay(*_args, **_kwargs):
                raise RuntimeError("relay failure")

            monkeypatch.setattr(server, "_relay_plain_http", fail_relay)
            lease = server.create_lease(_policy(port))
            response = await _http_request(
                str(server.http_socket),
                (
                    f"GET http://localhost:{port}/ HTTP/1.1\r\n"
                    f"Host: localhost:{port}\r\n"
                    f"Proxy-Authorization: {_authorization(lease.token).decode()}\r\n\r\n"
                ).encode(),
            )
            assert response == b""
            server.drop_lease(lease)
    finally:
        listener.close()
        await listener.wait_closed()
