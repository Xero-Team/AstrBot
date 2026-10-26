"""Authenticated per-invocation HTTP/SOCKS proxy for sandboxed Local code.

The proxy binds a dedicated Unix socket on Linux or loopback ports on macOS.
Every invocation receives a random bearer token bound to one immutable policy
and one bounded violation store. Proxy authorization is consumed, never
forwarded, and every destination is resolved exactly once inside the checked
address guard before a numeric connection is dialed.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hmac
import ipaddress
import os
import secrets
import shutil
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot import logger
from astrbot.core.computer.local_policy import LocalSandboxPolicy, normalize_hostname
from astrbot.core.computer.process_sandbox.network import (
    CheckedDestination,
    NetworkPolicyError,
    ResolvedAddressGuard,
    resolve_and_check,
    resolve_host_addresses_async,
)
from astrbot.core.computer.process_sandbox.violations import ViolationStore

MAX_LEASES = 256
MAX_CONNECTIONS_PER_LEASE = 32
MAX_CONNECTIONS_GLOBAL = 512
MAX_UNAUTHENTICATED = 64
MAX_DNS_LOOKUPS_PER_LEASE = 64
MAX_HEADER_BYTES = 32 * 1024
MAX_REQUEST_LINE = 8 * 1024
MAX_HEADERS = 100
READINESS_TIMEOUT_SECONDS = 10.0
IDLE_TUNNEL_SECONDS = 300.0
_IDLE_CHECK_SECONDS = 1.0

_HOP_BY_HOP_HEADERS = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"proxy-connection",
        b"te",
        b"trailer",
        b"upgrade",
    }
)
_SOCKS_VERSION = 5
_SOCKS_AUTH_VERSION = 1
_SOCKS_CMD_CONNECT = 1
_SOCKS_ATYP_IPV4 = 1
_SOCKS_ATYP_DOMAIN = 3
_SOCKS_ATYP_IPV6 = 4

ProxyState = str


class ProxyProtocolError(ValueError):
    """Raised for malformed or unsupported proxy protocol input."""


class ProxyLimitError(RuntimeError):
    """Raised when a bounded proxy registry or connection ceiling is reached."""


@dataclass(frozen=True, slots=True)
class HttpRequestHead:
    """A bounded parsed HTTP proxy request line and headers."""

    method: str
    target: str
    version: str
    headers: tuple[tuple[bytes, bytes], ...]

    def header(self, name: bytes) -> bytes | None:
        """Return the first case-insensitive header value."""
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return None


def _read_until_headers(
    buffer: bytes,
    *,
    max_header_bytes: int = MAX_HEADER_BYTES,
) -> tuple[bytes, bytes] | None:
    """Split a bounded header block from buffered bytes."""
    if len(buffer) > max_header_bytes and b"\r\n\r\n" not in buffer:
        raise ProxyProtocolError("Proxy request headers are too large.")
    marker = buffer.find(b"\r\n\r\n")
    if marker < 0:
        if len(buffer) >= max_header_bytes:
            raise ProxyProtocolError("Proxy request headers are too large.")
        return None
    if marker + 4 > max_header_bytes:
        raise ProxyProtocolError("Proxy request headers are too large.")
    return buffer[:marker], buffer[marker + 4 :]


def parse_http_request_head(head: bytes) -> HttpRequestHead:
    """Parse one HTTP/1.1 proxy request head with bounded framing."""
    if not head:
        raise ProxyProtocolError("The proxy request is empty.")
    lines = head.split(b"\r\n")
    if not lines or len(lines[0]) > MAX_REQUEST_LINE:
        raise ProxyProtocolError("The proxy request line is too long.")
    try:
        request_line = lines[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProxyProtocolError("The proxy request line is not ASCII.") from exc
    parts = request_line.split(" ")
    if len(parts) != 3:
        raise ProxyProtocolError("Malformed proxy request line.")
    method, target, version = parts
    if not method or not target or version not in {"HTTP/1.0", "HTTP/1.1"}:
        raise ProxyProtocolError("Unsupported proxy request line.")
    if any(character in target for character in ("\x00", "\r", "\n")):
        raise ProxyProtocolError("Malformed proxy request target.")
    if len(lines) - 1 > MAX_HEADERS:
        raise ProxyProtocolError("The proxy request has too many headers.")
    headers: list[tuple[bytes, bytes]] = []
    content_lengths: set[str] = set()
    content_length_count = 0
    has_transfer_encoding = False
    host_headers = 0
    for line in lines[1:]:
        if not line:
            continue
        if b":" not in line:
            raise ProxyProtocolError("Malformed proxy header.")
        if b"\x00" in line or b"\r" in line or b"\n" in line:
            raise ProxyProtocolError("Malformed proxy header.")
        name, value = line.split(b":", 1)
        if not name or b" " in name or b"\x00" in name:
            raise ProxyProtocolError("Malformed proxy header name.")
        lowered = name.lower()
        if lowered == b"content-length":
            content_length_count += 1
            content_lengths.add(value.strip().decode("ascii", errors="ignore"))
        if lowered == b"transfer-encoding":
            has_transfer_encoding = True
        if lowered == b"host":
            host_headers += 1
        headers.append((name, value.strip()))
    if content_lengths and has_transfer_encoding:
        raise ProxyProtocolError(
            "Ambiguous proxy request framing (Content-Length and Transfer-Encoding)."
        )
    if content_length_count > 1:
        raise ProxyProtocolError("Conflicting Content-Length headers.")
    if host_headers > 1:
        raise ProxyProtocolError("Conflicting Host headers.")
    for raw in content_lengths:
        if not raw.isdigit():
            raise ProxyProtocolError("Invalid Content-Length header.")

    parsed = HttpRequestHead(
        method=method.upper(),
        target=target,
        version=version,
        headers=tuple(headers),
    )
    connection_tokens = parsed.header(b"connection")
    if connection_tokens:
        for token in connection_tokens.split(b","):
            normalized = token.strip().lower()
            if normalized in {b"proxy-authorization", b"proxy-connection"}:
                continue
            if normalized in {b"content-length", b"host"}:
                raise ProxyProtocolError("Unsafe Connection header token.")
    return parsed


def parse_proxy_authorization(value: bytes | None) -> str | None:
    """Decode a Basic proxy credential and return its non-empty token."""
    if not value:
        return None
    try:
        text = value.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    scheme, _, credential = text.partition(" ")
    if scheme.lower() != "basic" or not credential:
        return None
    try:
        decoded = base64.b64decode(credential, validate=True).decode("utf-8")
    except binascii.Error, UnicodeDecodeError, ValueError:
        return None
    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return username or password or None


def _parse_authority(target: str, default_port: int | None = None) -> tuple[str, int]:
    if not target or any(character in target for character in "\r\n\x00"):
        raise ProxyProtocolError("Malformed proxy authority.")
    if target.startswith("["):
        closing = target.find("]")
        if closing < 0:
            raise ProxyProtocolError("Malformed bracketed IPv6 authority.")
        host = target[1:closing]
        remainder = target[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise ProxyProtocolError("Malformed proxy authority.")
            raw_port = remainder[1:]
        elif default_port is None:
            raise ProxyProtocolError("The proxy authority requires a port.")
        else:
            raw_port = str(default_port)
    else:
        host, separator, raw_port = target.rpartition(":")
        if not separator:
            if default_port is None:
                raise ProxyProtocolError("The proxy authority requires a port.")
            host, raw_port = target, str(default_port)
        if ":" in host:
            raise ProxyProtocolError("IPv6 proxy authorities must use brackets.")
    if (
        not host
        or any(part in host for part in ("/", "\\", "@", "%", "\x00"))
        or any(character.isspace() for character in host)
    ):
        raise ProxyProtocolError("Malformed proxy authority hostname.")
    if not raw_port.isascii() or not raw_port.isdigit():
        raise ProxyProtocolError("Malformed proxy authority port.")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ProxyProtocolError("Proxy authority port is out of range.")
    return host, port


def parse_socks_greeting(data: bytes) -> tuple[int, bytes]:
    """Validate a SOCKS5 greeting and return the offered methods."""
    if len(data) < 2 or data[0] != _SOCKS_VERSION:
        raise ProxyProtocolError("Malformed SOCKS5 greeting.")
    count = data[1]
    if count == 0 or len(data) < 2 + count:
        raise ProxyProtocolError("Malformed SOCKS5 method list.")
    return _SOCKS_VERSION, data[2 : 2 + count]


def parse_socks_auth(data: bytes) -> tuple[str, str]:
    """Parse a SOCKS5 username/password payload."""
    if len(data) < 3 or data[0] != _SOCKS_AUTH_VERSION:
        raise ProxyProtocolError("Malformed SOCKS5 authentication.")
    username_length = data[1]
    if len(data) < 2 + username_length + 1:
        raise ProxyProtocolError("Malformed SOCKS5 authentication.")
    username = data[2 : 2 + username_length].decode("utf-8", errors="strict")
    password_length = data[2 + username_length]
    start = 3 + username_length
    if len(data) < start + password_length:
        raise ProxyProtocolError("Malformed SOCKS5 authentication.")
    password = data[start : start + password_length].decode("utf-8", errors="strict")
    return username, password


def parse_socks_connect_request(
    command: int,
    address_type: int,
    address: bytes,
    port: int,
) -> tuple[str, int]:
    """Turn a SOCKS5 CONNECT request into a checked destination."""
    if command != _SOCKS_CMD_CONNECT:
        raise ProxyProtocolError("Only SOCKS5 CONNECT is supported.")
    if not 1 <= port <= 65535:
        raise ProxyProtocolError("SOCKS5 destination port is out of range.")
    if address_type == _SOCKS_ATYP_IPV4:
        if len(address) != 4:
            raise ProxyProtocolError("Malformed SOCKS5 IPv4 address.")
        return str(ipaddress.IPv4Address(address)), port
    if address_type == _SOCKS_ATYP_IPV6:
        if len(address) != 16:
            raise ProxyProtocolError("Malformed SOCKS5 IPv6 address.")
        return str(ipaddress.IPv6Address(address)), port
    if address_type == _SOCKS_ATYP_DOMAIN:
        if not address or len(address) > 255:
            raise ProxyProtocolError("Malformed SOCKS5 domain name.")
        try:
            host = address.decode("idna")
        except UnicodeError as exc:
            raise ProxyProtocolError("Malformed SOCKS5 domain name.") from exc
        if any(character in host for character in "\r\n\x00"):
            raise ProxyProtocolError("Malformed SOCKS5 domain name.")
        return host, port
    raise ProxyProtocolError("Unsupported SOCKS5 address type.")


class ProxyLease:
    """One bounded, revocable authorization and policy scope."""

    def __init__(
        self,
        token: str,
        policy: LocalSandboxPolicy,
        release_callback: Callable[[], None] | None = None,
    ) -> None:
        """Create an inactive lease; the server registers it."""
        self.token = token
        self.policy = policy
        self.violations = ViolationStore()
        self._release_callback = release_callback
        self._lock = threading.Lock()
        self._revoked = False
        self._released = False
        self._connections = 0
        self._dns_lookups = 0
        self._tunnels: set[Callable[[], None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._guard = ResolvedAddressGuard(policy.network)

    @property
    def revoked(self) -> bool:
        """Return whether the lease no longer authorizes any work."""
        with self._lock:
            return self._revoked

    @property
    def active_connections(self) -> int:
        """Return the number of authenticated connections using this lease."""
        with self._lock:
            return self._connections

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the single proxy event loop that owns tunnel closers."""
        self._loop = loop

    def register_connection(self) -> bool:
        """Reserve one authenticated connection slot."""
        with self._lock:
            if self._revoked or self._connections >= MAX_CONNECTIONS_PER_LEASE:
                return False
            self._connections += 1
            return True

    def release_connection(self) -> None:
        """Release an authenticated connection slot."""
        with self._lock:
            if self._connections:
                self._connections -= 1

    def register_tunnel(self, closer: Callable[[], None]) -> bool:
        """Register a tunnel closer so revocation can terminate it."""
        with self._lock:
            if self._revoked:
                return False
            self._tunnels.add(closer)
            return True

    def unregister_tunnel(self, closer: Callable[[], None]) -> None:
        """Remove a closed tunnel closer."""
        with self._lock:
            self._tunnels.discard(closer)

    def reserve_dns_lookup(self) -> bool:
        """Reserve one bounded DNS lookup for this lease."""
        with self._lock:
            if self._revoked or self._dns_lookups >= MAX_DNS_LOOKUPS_PER_LEASE:
                return False
            self._dns_lookups += 1
            return True

    async def resolve(self, hostname: str, port: int) -> CheckedDestination:
        """Authorize first, then resolve one destination without blocking."""
        if not self.reserve_dns_lookup():
            raise NetworkPolicyError("The destination DNS lookup limit was reached.")
        if self.revoked:
            raise NetworkPolicyError("The proxy lease has been revoked.")
        canonical = normalize_hostname(hostname)
        if not self._guard.matcher.allows(canonical, port):
            self.violations.record("network", "destination not allowed", canonical)
            raise NetworkPolicyError(
                "The destination is not allowed by the network policy."
            )
        addresses = await resolve_host_addresses_async(canonical, port)
        return resolve_and_check(
            canonical,
            port,
            self.policy.network,
            guard=self._guard,
            resolver=lambda _host, _port: addresses,
            violations=self.violations,
        )

    def revoke(self, reason: str = "lease revoked") -> None:
        """Idempotently stop new work and close every active tunnel."""
        with self._lock:
            if self._revoked:
                return
            self._revoked = True
            tunnels = list(self._tunnels)
            self._tunnels.clear()
        if reason and reason != "completed":
            self.violations.record("lifecycle", reason)
        loop = self._loop
        for closer in tunnels:
            try:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(closer)
                else:
                    closer()
            except Exception:  # noqa: BLE001  # best-effort tunnel teardown
                continue
        self.release(reason)

    def release(self, reason: str = "completed") -> None:
        """Run the owner's release callback exactly once."""
        with self._lock:
            if self._released:
                return
            self._released = True
            callback = self._release_callback
        if callback is not None:
            try:
                callback()
            except Exception as exc:  # noqa: BLE001  # cleanup must not mask the original failure
                logger.warning("Local proxy lease release callback failed: %s", exc)

    def snapshot_violations(self) -> list[dict[str, object]]:
        """Return a bounded redacted snapshot that survives revocation."""
        return self.violations.as_result()


class LocalProxyServer:
    """Runtime-owned proxy listener with a bounded per-invocation registry."""

    def __init__(
        self,
        *,
        socket_dir: Path | None = None,
        platform: str | None = None,
    ) -> None:
        """Create a stopped proxy server.

        Args:
            socket_dir: Directory for Linux Unix sockets. A private temporary
                directory is created when omitted.
            platform: Platform override used by tests.
        """
        self._platform = platform or sys.platform
        self._socket_dir = socket_dir
        self._owns_socket_dir = socket_dir is None
        self._state: ProxyState = "new"
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self._startup_error: BaseException | None = None
        self._leases: dict[str, ProxyLease] = {}
        self._leases_lock = threading.Lock()
        self._connection_tasks: set[asyncio.Task[Any]] = set()
        self._global_connections = 0
        self._unauthenticated_connections = 0
        self._limits_lock = threading.Lock()
        self.http_socket: Path | None = None
        self.socks_socket: Path | None = None
        self.http_port: int | None = None
        self.socks_port: int | None = None
        self._servers: list[asyncio.AbstractServer] = []

    @property
    def state(self) -> ProxyState:
        """Return the current lifecycle state."""
        with self._state_lock:
            return self._state

    def _set_state(self, expected: ProxyState, new_state: ProxyState) -> None:
        with self._state_lock:
            if self._state != expected:
                raise RuntimeError(
                    f"Invalid Local proxy state transition {self._state!r} -> "
                    f"{new_state!r}."
                )
            self._state = new_state

    def start(self) -> None:
        """Start the listener and wait for a bounded readiness handshake."""
        self._set_state("new", "starting")
        if self._platform not in {"linux", "darwin"}:
            self._set_state("starting", "stopped")
            raise RuntimeError(
                "The Local sandbox proxy is not supported on this platform."
            )
        if self._platform == "linux":
            self._prepare_unix_directory()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="astrbot-local-proxy",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(READINESS_TIMEOUT_SECONDS):
            self._set_state("starting", "stopped")
            if self._thread is not None:
                self._thread.join(1)
            self._cleanup_paths()
            raise RuntimeError("The Local sandbox proxy did not become ready.")
        if self._startup_error is not None:
            self._set_state("starting", "stopped")
            self._cleanup_paths()
            raise RuntimeError("The Local sandbox proxy failed to start.") from (
                self._startup_error
            )
        self._set_state("starting", "running")

    def _prepare_unix_directory(self) -> None:
        if self._socket_dir is None:
            self._socket_dir = Path(
                tempfile.mkdtemp(prefix="astrbot-proxy-", dir=tempfile.gettempdir())
            )
        else:
            self._socket_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self._socket_dir, stat.S_IRWXU)
        self.http_socket = self._socket_dir / "http.sock"
        self.socks_socket = self._socket_dir / "socks.sock"

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:  # surfaced to the starting caller
            self._startup_error = exc
            self._ready.set()
            self._cleanup_paths()

    async def _serve(self) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._stop_event = asyncio.Event()
        try:
            if self._platform == "linux":
                self.http_socket = self._socket_dir / "http.sock"  # type: ignore[union-attr]
                self.socks_socket = self._socket_dir / "socks.sock"  # type: ignore[union-attr]
                http_server = await asyncio.start_unix_server(
                    self._handle_http,
                    path=str(self.http_socket),
                )
                self._servers.append(http_server)
                socks_server = await asyncio.start_unix_server(
                    self._handle_socks,
                    path=str(self.socks_socket),
                )
                self._servers.append(socks_server)
            else:
                http_server = await asyncio.start_server(
                    self._handle_http,
                    host="127.0.0.1",
                    port=0,
                )
                self._servers.append(http_server)
                socks_server = await asyncio.start_server(
                    self._handle_socks,
                    host="127.0.0.1",
                    port=0,
                )
                self._servers.append(socks_server)
                self.http_port = http_server.sockets[0].getsockname()[1]
                self.socks_port = socks_server.sockets[0].getsockname()[1]
            if self.http_socket is not None:
                os.chmod(self.http_socket, stat.S_IRUSR | stat.S_IWUSR)
            if self.socks_socket is not None:
                os.chmod(self.socks_socket, stat.S_IRUSR | stat.S_IWUSR)
            self._ready.set()
            if self.state in {"stopping", "stopped"}:
                self._stop_event.set()
            await self._stop_event.wait()
        except Exception as exc:  # readiness reports startup failure
            self._startup_error = exc
            self._ready.set()
        finally:
            await self._close_servers()
            await self._cancel_connections()
            self._revoke_all()
            self._cleanup_paths()
            self._loop = None

    async def stop(self) -> None:
        """Stop new work, close every tunnel and join the dedicated thread."""
        with self._state_lock:
            if self._state in {"new", "stopped"}:
                self._state = "stopped"
                self._cleanup_paths()
                return
            if self._state == "stopping":
                stopping = True
            else:
                self._state = "stopping"
                stopping = False
        if not stopping:
            loop = self._loop
            if loop is not None and self._stop_event is not None:
                loop.call_soon_threadsafe(self._stop_event.set)
        thread = self._thread
        if thread is not None:
            await asyncio.to_thread(thread.join, READINESS_TIMEOUT_SECONDS)
        self._thread = None
        with self._state_lock:
            self._state = "stopped"
        self._cleanup_paths()

    def shutdown(self) -> None:
        """Synchronous best-effort stop used by process teardown."""
        if self.state in {"new", "stopped"}:
            with self._state_lock:
                self._state = "stopped"
            self._cleanup_paths()
            return
        loop = self._loop
        if loop is not None and self._stop_event is not None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._stop_event.set)
        thread = self._thread
        if thread is not None:
            thread.join(READINESS_TIMEOUT_SECONDS)
        self._thread = None
        with self._state_lock:
            self._state = "stopped"
        self._cleanup_paths()

    async def _close_servers(self) -> None:
        for server in self._servers:
            server.close()
        for server in self._servers:
            with contextlib.suppress(Exception):
                await server.wait_closed()
        self._servers.clear()

    async def _cancel_connections(self) -> None:
        tasks = list(self._connection_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._connection_tasks.clear()

    def _revoke_all(self) -> None:
        with self._leases_lock:
            leases = list(self._leases.values())
            self._leases.clear()
        for lease in leases:
            lease.revoke("proxy shutdown")

    def _cleanup_paths(self) -> None:
        for path in (self.http_socket, self.socks_socket):
            if path is not None:
                with contextlib.suppress(FileNotFoundError, OSError):
                    path.unlink()
        if self._owns_socket_dir and self._socket_dir is not None:
            with contextlib.suppress(OSError):
                shutil.rmtree(self._socket_dir, ignore_errors=True)
        if self._owns_socket_dir:
            self._socket_dir = None
        self.http_socket = None
        self.socks_socket = None

    def create_lease(
        self,
        policy: LocalSandboxPolicy,
        *,
        release_callback: Callable[[], None] | None = None,
    ) -> ProxyLease:
        """Register one bounded lease for an active proxy."""
        if self.state != "running":
            raise ProxyLimitError("The Local sandbox proxy is not running.")
        if not policy.network.enabled:
            raise ValueError("A proxy lease requires enabled network access.")
        token = secrets.token_urlsafe(32)
        lease = ProxyLease(token, policy, release_callback)
        if self._loop is not None:
            lease.bind_loop(self._loop)
        with self._leases_lock:
            if len(self._leases) >= MAX_LEASES:
                raise ProxyLimitError("The Local proxy lease limit was reached.")
            if token in self._leases:
                raise ProxyLimitError("The Local proxy lease token collided.")
            self._leases[token] = lease
        return lease

    def drop_lease(self, lease: ProxyLease) -> None:
        """Remove and revoke a lease after its invocation completes."""
        with self._leases_lock:
            if self._leases.get(lease.token) is lease:
                self._leases.pop(lease.token, None)
        lease.revoke("completed")

    def _lookup_lease(self, token: str | None) -> ProxyLease | None:
        if not token:
            return None
        with self._leases_lock:
            leases = list(self._leases.values())
        matched: ProxyLease | None = None
        for lease in leases:
            if hmac.compare_digest(lease.token, token):
                matched = lease
        if matched is None or matched.revoked:
            return None
        return matched

    def _track_connection(self, task: asyncio.Task[Any]) -> None:
        self._connection_tasks.add(task)
        task.add_done_callback(self._connection_tasks.discard)

    def _reserve_global(self, *, authenticated: bool) -> bool:
        with self._limits_lock:
            total = self._global_connections + self._unauthenticated_connections
            if authenticated:
                if total >= MAX_CONNECTIONS_GLOBAL:
                    return False
                self._global_connections += 1
                return True
            if (
                self._unauthenticated_connections >= MAX_UNAUTHENTICATED
                or total >= MAX_CONNECTIONS_GLOBAL
            ):
                return False
            self._unauthenticated_connections += 1
            return True

    def _finish_global(self, *, authenticated: bool) -> None:
        with self._limits_lock:
            if authenticated and self._global_connections:
                self._global_connections -= 1
            elif not authenticated and self._unauthenticated_connections:
                self._unauthenticated_connections -= 1

    async def _handle_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._track_connection(task)
        lease: ProxyLease | None = None
        authenticated = False
        if not self._reserve_global(authenticated=False):
            await self._close(writer)
            return
        try:
            head = await self._read_http_head(reader)
            if head is None:
                await self._http_error(writer, 400, "Bad Request")
                return
            token = parse_proxy_authorization(head.header(b"proxy-authorization"))
            lease = self._lookup_lease(token)
            if lease is None:
                await self._http_error(
                    writer,
                    407,
                    "Proxy Authentication Required",
                    extra_headers=(b"Proxy-Authenticate: Basic realm=astrbot",),
                )
                return
            reserved = self._reserve_global(authenticated=True)
            if not reserved or not lease.register_connection():
                if reserved:
                    self._finish_global(authenticated=True)
                await self._http_error(writer, 503, "Service Unavailable")
                return
            authenticated = True
            self._finish_global(authenticated=False)
            await self._serve_http_request(head, reader, writer, lease)
        except ProxyProtocolError, NetworkPolicyError, ValueError:
            with contextlib.suppress(Exception):
                await self._http_error(writer, 403, "Forbidden")
        except TimeoutError, ConnectionError, OSError:
            with contextlib.suppress(Exception):
                await self._http_error(writer, 504, "Gateway Timeout")
        except asyncio.CancelledError:
            raise
        except Exception:
            with contextlib.suppress(Exception):
                await self._http_error(writer, 502, "Bad Gateway")
        finally:
            if lease is not None and authenticated:
                lease.release_connection()
            self._finish_global(authenticated=authenticated)
            await self._close(writer)

    async def _read_http_head(
        self,
        reader: asyncio.StreamReader,
    ) -> HttpRequestHead | None:
        buffer = b""
        while True:
            chunk = await asyncio.wait_for(
                reader.read(4096),
                timeout=READINESS_TIMEOUT_SECONDS,
            )
            if not chunk:
                return None
            buffer += chunk
            split = _read_until_headers(buffer)
            if split is None:
                continue
            head, remainder = split
            if remainder:
                reader.feed_data(remainder)
            return parse_http_request_head(head)

    async def _serve_http_request(
        self,
        head: HttpRequestHead,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        lease: ProxyLease,
    ) -> None:
        if head.method == "CONNECT":
            target = _parse_authority(head.target)
            host_header = head.header(b"host")
            if host_header:
                try:
                    host_authority = _parse_authority(
                        host_header.decode("ascii"),
                        default_port=target[1],
                    )
                except (UnicodeDecodeError, ProxyProtocolError) as exc:
                    raise ProxyProtocolError(
                        "Host header does not match CONNECT."
                    ) from exc
                if host_authority[0].lower() != target[0].lower() or (
                    host_authority[1] != target[1]
                ):
                    raise ProxyProtocolError("Host header does not match CONNECT.")
            destination = await lease.resolve(*target)
            try:
                upstream_reader, upstream_writer = await self._dial(destination)
            except OSError:
                await self._http_error(writer, 502, "Bad Gateway")
                return
            try:
                writer.write(
                    b"HTTP/1.1 200 Connection Established\r\n"
                    b"Proxy-Agent: AstrBot\r\n\r\n"
                )
                await writer.drain()
                await self._relay(
                    reader,
                    writer,
                    upstream_reader,
                    upstream_writer,
                    lease,
                )
            finally:
                upstream_writer.close()
                with contextlib.suppress(Exception):
                    await upstream_writer.wait_closed()
            return

        parsed = _split_absolute_target(head)
        if parsed is None:
            raise ProxyProtocolError(
                "The proxy accepts CONNECT or absolute-form http:// requests only."
            )
        host, port, origin_target = parsed
        host_header = head.header(b"host")
        if host_header:
            try:
                header_authority = _parse_authority(
                    host_header.decode("ascii"),
                    default_port=port,
                )
            except (UnicodeDecodeError, ProxyProtocolError) as exc:
                raise ProxyProtocolError(
                    "Host header does not match the target."
                ) from exc
            if (
                header_authority[0].lower() != host.lower()
                or header_authority[1] != port
            ):
                raise ProxyProtocolError("Host header does not match the target.")
        destination = await lease.resolve(host, port)
        try:
            upstream_reader, upstream_writer = await self._dial(destination)
        except OSError:
            await self._http_error(writer, 502, "Bad Gateway")
            return
        try:
            headers = self._forward_headers(
                head.headers,
                authority=_format_authority(host, port),
            )
            request = (
                f"{head.method} {origin_target} {head.version}\r\n".encode("latin-1")
                + b"".join(name + b": " + value + b"\r\n" for name, value in headers)
                + b"\r\n"
            )
            upstream_writer.write(request)
            await upstream_writer.drain()
            await self._relay(
                reader,
                writer,
                upstream_reader,
                upstream_writer,
                lease,
            )
        finally:
            upstream_writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()

    def _forward_headers(
        self,
        headers: tuple[tuple[bytes, bytes], ...],
        *,
        authority: str,
    ) -> list[tuple[bytes, bytes]]:
        connection_tokens: set[bytes] = set()
        for name, value in headers:
            if name.lower() == b"connection":
                connection_tokens.update(
                    token.strip().lower() for token in value.split(b",")
                )
        forwarded: list[tuple[bytes, bytes]] = []
        for name, value in headers:
            lowered = name.lower()
            if lowered in _HOP_BY_HOP_HEADERS or lowered in connection_tokens:
                continue
            if lowered == b"host":
                forwarded.append((b"Host", authority.encode("latin-1", "replace")))
                continue
            forwarded.append((name, value))
        if not any(name.lower() == b"host" for name, _ in forwarded):
            forwarded.insert(0, (b"Host", authority.encode("latin-1", "replace")))
        return forwarded

    async def _dial(
        self,
        destination: CheckedDestination,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        last_error: OSError | None = None
        for address in destination.addresses:
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(
                        str(address),
                        destination.port,
                    ),
                    timeout=READINESS_TIMEOUT_SECONDS,
                )
            except OSError as exc:
                last_error = exc
                continue
        raise last_error or OSError("Unable to connect to the approved destination.")

    async def _relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
        lease: ProxyLease,
    ) -> None:
        closed = False

        def close_tunnel() -> None:
            nonlocal closed
            if closed:
                return
            closed = True
            upstream_writer.close()
            client_writer.close()

        if not lease.register_tunnel(close_tunnel):
            close_tunnel()
            return
        try:
            await self._pump_both(
                client_reader,
                client_writer,
                upstream_reader,
                upstream_writer,
                idle_timeout=IDLE_TUNNEL_SECONDS,
            )
        except TimeoutError:
            lease.violations.record("network", "idle tunnel timed out")
        finally:
            lease.unregister_tunnel(close_tunnel)
            close_tunnel()
            for stream_writer in (client_writer, upstream_writer):
                with contextlib.suppress(Exception):
                    await stream_writer.wait_closed()

    @staticmethod
    async def _pump_both(
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
        *,
        idle_timeout: float = IDLE_TUNNEL_SECONDS,
    ) -> None:
        activity = [time.monotonic()]

        async def pump(
            source: asyncio.StreamReader,
            destination: asyncio.StreamWriter,
        ) -> None:
            try:
                while chunk := await source.read(65536):
                    activity[0] = time.monotonic()
                    destination.write(chunk)
                    await destination.drain()
                    activity[0] = time.monotonic()
            finally:
                # Forward EOF without tearing down the opposite direction.
                # HTTP clients may signal the end of a request body with a
                # write half-close and still wait for the response.
                if destination.can_write_eof():
                    with contextlib.suppress(Exception):
                        destination.write_eof()

        tasks = {
            asyncio.create_task(pump(client_reader, upstream_writer)),
            asyncio.create_task(pump(upstream_reader, client_writer)),
        }
        pending = set(tasks)
        try:
            while pending:
                done, still_pending = await asyncio.wait(
                    pending,
                    timeout=_IDLE_CHECK_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                pending = set(still_pending)
                for task in done:
                    try:
                        task.result()
                    except Exception:
                        for other in pending:
                            other.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        pending.clear()
                        raise
                if not done and time.monotonic() - activity[0] >= idle_timeout:
                    raise TimeoutError
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_socks(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._track_connection(task)
        lease: ProxyLease | None = None
        authenticated = False
        if not self._reserve_global(authenticated=False):
            await self._close(writer)
            return
        try:
            greeting = await asyncio.wait_for(
                reader.readexactly(2),
                timeout=READINESS_TIMEOUT_SECONDS,
            )
            methods = await reader.readexactly(greeting[1])
            version, methods = parse_socks_greeting(greeting + methods)
            if version != _SOCKS_VERSION or 0x02 not in methods:
                writer.write(b"\x05\xff")
                await writer.drain()
                return
            writer.write(b"\x05\x02")
            await writer.drain()
            username, password = await self._read_socks_credentials(reader)
            lease = self._lookup_lease(username) or self._lookup_lease(password)
            if lease is None:
                writer.write(b"\x01\x01")
                await writer.drain()
                return
            reserved = self._reserve_global(authenticated=True)
            if not reserved or not lease.register_connection():
                if reserved:
                    self._finish_global(authenticated=True)
                writer.write(b"\x01\x01")
                await writer.drain()
                return
            authenticated = True
            self._finish_global(authenticated=False)
            writer.write(b"\x01\x00")
            await writer.drain()
            host, port = await self._read_socks_request(reader)
            try:
                destination = await lease.resolve(host, port)
            except NetworkPolicyError:
                writer.write(b"\x05\x02\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                return
            try:
                upstream_reader, upstream_writer = await self._dial(destination)
            except OSError:
                writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                return
            try:
                writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                await self._relay(
                    reader,
                    writer,
                    upstream_reader,
                    upstream_writer,
                    lease,
                )
            finally:
                upstream_writer.close()
                with contextlib.suppress(Exception):
                    await upstream_writer.wait_closed()
        except ProxyProtocolError, UnicodeError, ValueError:
            with contextlib.suppress(Exception):
                writer.write(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
        except TimeoutError, ConnectionError, OSError:
            with contextlib.suppress(Exception):
                writer.write(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
        except asyncio.CancelledError:
            raise
        except Exception:
            with contextlib.suppress(Exception):
                writer.write(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
        finally:
            if lease is not None and authenticated:
                lease.release_connection()
            self._finish_global(authenticated=authenticated)
            await self._close(writer)

    @staticmethod
    async def _read_socks_credentials(
        reader: asyncio.StreamReader,
    ) -> tuple[str, str]:
        version_and_length = await asyncio.wait_for(
            reader.readexactly(2),
            timeout=READINESS_TIMEOUT_SECONDS,
        )
        username = await reader.readexactly(version_and_length[1])
        password_length = (await reader.readexactly(1))[0]
        password = await reader.readexactly(password_length)
        payload = version_and_length + username + bytes([password_length]) + password
        return parse_socks_auth(payload)

    @staticmethod
    async def _read_socks_request(
        reader: asyncio.StreamReader,
    ) -> tuple[str, int]:
        header = await asyncio.wait_for(
            reader.readexactly(4),
            timeout=READINESS_TIMEOUT_SECONDS,
        )
        version, command, _reserved, address_type = header
        if version != _SOCKS_VERSION:
            raise ProxyProtocolError("Malformed SOCKS5 request.")
        if address_type == _SOCKS_ATYP_IPV4:
            address = await reader.readexactly(4)
        elif address_type == _SOCKS_ATYP_IPV6:
            address = await reader.readexactly(16)
        elif address_type == _SOCKS_ATYP_DOMAIN:
            length = (await reader.readexactly(1))[0]
            address = await reader.readexactly(length)
        else:
            raise ProxyProtocolError("Unsupported SOCKS5 address type.")
        port = int.from_bytes(await reader.readexactly(2), "big")
        return parse_socks_connect_request(command, address_type, address, port)

    @staticmethod
    async def _http_error(
        writer: asyncio.StreamWriter,
        status: int,
        reason: str,
        *,
        extra_headers: tuple[bytes, ...] = (),
    ) -> None:
        body = f"{status} {reason}\n".encode("ascii")
        headers = [
            f"HTTP/1.1 {status} {reason}\r\n".encode("ascii"),
            b"Content-Type: text/plain; charset=utf-8\r\n",
            f"Content-Length: {len(body)}\r\n".encode("ascii"),
            b"Connection: close\r\n",
            *extra_headers,
            b"\r\n",
        ]
        writer.write(b"".join(headers) + body)
        await writer.drain()

    @staticmethod
    async def _close(writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()


def _format_authority(host: str, port: int) -> str:
    """Return an HTTP Host authority, bracketing IPv6 literals."""
    formatted_host = f"[{host}]" if ":" in host else host
    return f"{formatted_host}:{port}"


def _split_absolute_target(
    head: HttpRequestHead,
) -> tuple[str, int, str] | None:
    target = head.target
    if not target.startswith("http://"):
        if target.startswith("https://"):
            raise ProxyProtocolError(
                "Absolute-form https:// is not supported; use CONNECT."
            )
        return None
    remainder = target[len("http://") :]
    authority_end = len(remainder)
    for delimiter in ("/", "?", "#"):
        index = remainder.find(delimiter)
        if index >= 0:
            authority_end = min(authority_end, index)
    authority = remainder[:authority_end]
    suffix = remainder[authority_end:] or "/"
    if "#" in target:
        raise ProxyProtocolError("Proxy request targets must not include fragments.")
    host, port = _parse_authority(authority, default_port=80)
    origin_target = suffix if suffix.startswith("/") else f"/{suffix}"
    if "?" in suffix:
        path, _, query = origin_target.partition("?")
        origin_target = f"{path}?{query}"
    return host, port, origin_target


__all__ = (
    "IDLE_TUNNEL_SECONDS",
    "MAX_CONNECTIONS_GLOBAL",
    "MAX_CONNECTIONS_PER_LEASE",
    "MAX_DNS_LOOKUPS_PER_LEASE",
    "MAX_HEADERS",
    "MAX_HEADER_BYTES",
    "MAX_LEASES",
    "MAX_REQUEST_LINE",
    "MAX_UNAUTHENTICATED",
    "HttpRequestHead",
    "LocalProxyServer",
    "ProxyLease",
    "ProxyLimitError",
    "ProxyProtocolError",
    "parse_http_request_head",
    "parse_proxy_authorization",
    "parse_socks_auth",
    "parse_socks_connect_request",
    "parse_socks_greeting",
)
