"""Domain matching and checked DNS resolution for the Local sandbox proxy."""

from __future__ import annotations

import asyncio
import ctypes
import ipaddress
import socket
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from astrbot.core.computer.local_policy import (
    DomainRule,
    LocalNetworkPolicy,
    normalize_hostname,
    parse_domain_rule,
)
from astrbot.core.computer.process_sandbox.violations import ViolationStore
from astrbot.core.utils.outbound_http import (
    expand_embedded_addresses,
    is_metadata_address,
    resolve_host_addresses,
)

Address = ipaddress.IPv4Address | ipaddress.IPv6Address

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_BROADCAST = ipaddress.ip_address("255.255.255.255")
_RESERVED_V4 = ipaddress.ip_network("240.0.0.0/4")


class NetworkPolicyError(ValueError):
    """Raised when a destination is not permitted by the Local policy."""


@dataclass(frozen=True, slots=True)
class CheckedDestination:
    """A destination that passed domain and address checks once.

    Args:
        hostname: Canonical requested hostname or literal.
        port: Destination port.
        addresses: Numeric addresses safe to dial; never resolved again.
    """

    hostname: str
    port: int
    addresses: tuple[Address, ...]


def _parse_rules(rules: tuple[str, ...]) -> tuple[DomainRule, ...]:
    return tuple(parse_domain_rule(rule) for rule in rules)


class DomainMatcher:
    """Exact, wildcard, IP and port-aware matcher with deny precedence."""

    def __init__(self, policy: LocalNetworkPolicy) -> None:
        """Compile a network policy into immutable rules."""
        self.policy = policy
        self.allowed = _parse_rules(policy.allowed_domains)
        self.denied = _parse_rules(policy.denied_domains)

    @property
    def enabled(self) -> bool:
        """Return whether any proxy destination may be authorized."""
        return self.policy.mode != "off"

    def matches_denied(self, hostname: str, port: int) -> bool:
        """Return whether an exact destination is denied."""
        normalized = normalize_hostname(hostname)
        return any(rule.matches(normalized, port) for rule in self.denied)

    def matches_allowed(self, hostname: str, port: int) -> bool:
        """Return whether an allowlist rule names the destination."""
        normalized = normalize_hostname(hostname)
        return any(rule.matches(normalized, port) for rule in self.allowed)

    def explicitly_allows_address(self, address: Address, port: int) -> bool:
        """Return whether a canonical IP literal and port are explicitly allowed."""
        if self.matches_denied(str(address), port):
            return False
        return any(
            rule.address is not None
            and normalize_hostname(rule.pattern) == normalize_hostname(str(address))
            and (rule.port is None or rule.port == port)
            for rule in self.allowed
        )

    def allows(self, hostname: str, port: int) -> bool:
        """Return whether the hostname rule class permits this destination."""
        if not self.enabled:
            return False
        if not 1 <= port <= 65535:
            return False
        if self.matches_denied(hostname, port):
            return False
        if self.policy.mode == "unrestricted":
            return True
        return self.matches_allowed(hostname, port)


def _nat64_embedded(address: Address) -> Address | None:
    if not isinstance(address, ipaddress.IPv6Address):
        return None
    if address in _NAT64 or address in _NAT64_LOCAL:
        packed = address.packed[-4:]
        return ipaddress.IPv4Address(packed)
    return None


def iter_address_forms(address: Address) -> Iterable[Address]:
    """Yield an address plus every embedded IPv4 representation."""
    yield from expand_embedded_addresses(address)
    embedded = _nat64_embedded(address)
    if embedded is not None:
        yield embedded


class _Sockaddr(ctypes.Structure):
    _fields_ = [("sa_family", ctypes.c_ushort), ("sa_data", ctypes.c_ubyte * 14)]


class _SockaddrIn(ctypes.Structure):
    _fields_ = [
        ("sin_family", ctypes.c_ushort),
        ("sin_port", ctypes.c_ushort),
        ("sin_addr", ctypes.c_ubyte * 4),
        ("sin_zero", ctypes.c_ubyte * 8),
    ]


class _SockaddrIn6(ctypes.Structure):
    _fields_ = [
        ("sin6_family", ctypes.c_ushort),
        ("sin6_port", ctypes.c_ushort),
        ("sin6_flowinfo", ctypes.c_uint32),
        ("sin6_addr", ctypes.c_ubyte * 16),
        ("sin6_scope_id", ctypes.c_uint32),
    ]


class _IfAddrs(ctypes.Structure):
    pass


_IfAddrs._fields_ = [
    ("ifa_next", ctypes.POINTER(_IfAddrs)),
    ("ifa_name", ctypes.c_char_p),
    ("ifa_flags", ctypes.c_uint),
    ("ifa_addr", ctypes.POINTER(_Sockaddr)),
]


@lru_cache(maxsize=1)
def _host_interface_addresses() -> set[Address]:
    """Return local interface addresses on Linux and macOS fail-closed.

    Enumerating through ``getifaddrs`` is non-blocking and does not depend on
    the host resolver. If the platform call is unavailable, callers retain the
    other address-class guards rather than discovering addresses via DNS.
    """
    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        return set()
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        getifaddrs = libc.getifaddrs
        freeifaddrs = libc.freeifaddrs
    except AttributeError, OSError:
        return set()
    head = ctypes.POINTER(_IfAddrs)()
    getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(_IfAddrs))]
    getifaddrs.restype = ctypes.c_int
    freeifaddrs.argtypes = [ctypes.POINTER(_IfAddrs)]
    freeifaddrs.restype = None
    if getifaddrs(ctypes.byref(head)) != 0:
        return set()
    addresses: set[Address] = set()
    try:
        current = head
        while current:
            entry = current.contents
            address_pointer = entry.ifa_addr
            if address_pointer:
                if sys.platform == "darwin":
                    # BSD sockaddr stores sa_len before an 8-bit sa_family.
                    family = ctypes.c_ubyte.from_address(
                        ctypes.addressof(address_pointer.contents) + 1
                    ).value
                else:
                    family = address_pointer.contents.sa_family
                if family == socket.AF_INET:
                    address = ctypes.cast(
                        address_pointer, ctypes.POINTER(_SockaddrIn)
                    ).contents
                    addresses.add(ipaddress.IPv4Address(bytes(address.sin_addr)))
                elif family == socket.AF_INET6:
                    address = ctypes.cast(
                        address_pointer, ctypes.POINTER(_SockaddrIn6)
                    ).contents
                    addresses.add(ipaddress.IPv6Address(bytes(address.sin6_addr)))
            current = entry.ifa_next
    finally:
        freeifaddrs(head)
    return {
        address
        for address in addresses
        if not address.is_loopback and not address.is_unspecified
    }


def _address_class(address: Address) -> str | None:
    """Return a denied class name, or None for a generally routable address."""
    if is_metadata_address(address):
        return "metadata"
    if address.is_multicast:
        return "multicast"
    if address.is_unspecified:
        return "unspecified"
    if address.is_link_local:
        return "link-local"
    if address == _BROADCAST:
        return "broadcast"
    if address.is_loopback:
        return "loopback"
    if address.is_reserved or (
        isinstance(address, ipaddress.IPv4Address) and address in _RESERVED_V4
    ):
        return "reserved"
    if address in _CGNAT or address.is_private:
        return "private"
    return None


class ResolvedAddressGuard:
    """Filter resolved addresses using flags, literals and embedded forms."""

    def __init__(
        self,
        policy: LocalNetworkPolicy,
        *,
        matcher: DomainMatcher | None = None,
        host_interfaces: set[Address] | None = None,
    ) -> None:
        """Store the policy and optional discovery override for tests."""
        self.policy = policy
        self.matcher = matcher or DomainMatcher(policy)
        self._host_interfaces = (
            host_interfaces
            if host_interfaces is not None
            else _host_interface_addresses()
        )

    def denial_reason(self, address: Address, port: int) -> str | None:
        """Return why an address is denied, or None when it may be dialed."""
        if self.matcher.explicitly_allows_address(address, port):
            return None
        # Embedded IPv4 forms can only add denials. Each candidate must pass.
        for candidate in iter_address_forms(address):
            if self.matcher.matches_denied(str(candidate), port):
                return "denied-address"
            if candidate in self._host_interfaces and not candidate.is_loopback:
                return "host-interface"
            candidate_class = _address_class(candidate)
            if candidate_class is None:
                continue
            if candidate_class == "loopback":
                if not self.policy.allow_loopback:
                    return "loopback"
                continue
            if candidate_class == "private":
                if not self.policy.allow_private_network:
                    return "private-network"
                continue
            return candidate_class
        return None

    def filter_addresses(
        self,
        addresses: Sequence[Address],
        port: int,
    ) -> tuple[Address, ...]:
        """Return only addresses permitted for the requested port."""
        permitted: list[Address] = []
        for address in addresses:
            if self.denial_reason(address, port) is None:
                permitted.append(address)
        return tuple(permitted)


def resolve_and_check(
    hostname: str,
    port: int,
    policy: LocalNetworkPolicy,
    *,
    resolver: Callable[[str, int], Sequence[Address]] | None = None,
    guard: ResolvedAddressGuard | None = None,
    violations: ViolationStore | None = None,
) -> CheckedDestination:
    """Authorize a hostname and resolve it exactly once through the guard.

    Args:
        hostname: Requested host or IP literal.
        port: Destination port.
        policy: Resolved network policy.
        resolver: Optional numeric resolver used by tests.
        guard: Optional pre-built guard (used to reuse host interface data).
        violations: Optional per-lease denial store.

    Returns:
        Approved numeric destinations. Callers must dial these addresses and
        never resolve the checked hostname again.

    Raises:
        NetworkPolicyError: If the destination class, domain, port, or every
            resolved address is denied.
    """
    canonical = normalize_hostname(hostname)
    if not canonical:
        raise NetworkPolicyError("The destination hostname is invalid.")
    if not 1 <= port <= 65535:
        raise NetworkPolicyError("The destination port is invalid.")
    matcher = guard.matcher if guard is not None else DomainMatcher(policy)
    if not matcher.allows(canonical, port):
        if violations is not None:
            violations.record("network", "destination not allowed", canonical)
        raise NetworkPolicyError(
            "The destination is not allowed by the network policy."
        )
    checked_guard = guard or ResolvedAddressGuard(policy, matcher=matcher)
    try:
        addresses = tuple((resolver or resolve_host_addresses)(canonical, port))
    except Exception as exc:
        if violations is not None:
            violations.record("network", "destination resolution failed", canonical)
        raise NetworkPolicyError(
            "The destination hostname could not be resolved."
        ) from exc
    if not addresses or len(addresses) > 32:
        if violations is not None:
            violations.record("network", "destination resolution rejected", canonical)
        raise NetworkPolicyError("The destination address set was rejected.")
    permitted = checked_guard.filter_addresses(addresses, port)
    if not permitted:
        if violations is not None:
            violations.record("network", "destination address denied", canonical)
        raise NetworkPolicyError("The destination address is not allowed.")
    if len(permitted) > 16:
        permitted = permitted[:16]
    return CheckedDestination(
        hostname=canonical,
        port=port,
        addresses=permitted,
    )


async def resolve_host_addresses_async(
    hostname: str,
    port: int,
) -> tuple[Address, ...]:
    """Resolve A/AAAA records without blocking the proxy event loop."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return (literal,)
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise NetworkPolicyError(
            "The destination hostname could not be resolved."
        ) from exc
    resolved: list[Address] = []
    seen: set[str] = set()
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        key = str(address)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(address)
    if not resolved:
        raise NetworkPolicyError("The destination hostname could not be resolved.")
    return tuple(resolved)


__all__ = (
    "Address",
    "CheckedDestination",
    "DomainMatcher",
    "NetworkPolicyError",
    "ResolvedAddressGuard",
    "iter_address_forms",
    "resolve_and_check",
    "resolve_host_addresses_async",
)
