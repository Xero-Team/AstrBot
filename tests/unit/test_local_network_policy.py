"""Domain and resolved-address enforcement for the Local sandbox proxy."""

from __future__ import annotations

import ipaddress

import pytest

from astrbot.core.computer.local_policy import LocalNetworkPolicy
from astrbot.core.computer.process_sandbox.network import (
    DomainMatcher,
    NetworkPolicyError,
    ResolvedAddressGuard,
    _host_interface_addresses,
    resolve_and_check,
    resolve_host_addresses_async,
)

PUBLIC = ipaddress.ip_address("93.184.216.34")
SECOND_PUBLIC = ipaddress.ip_address("1.1.1.1")


def test_exact_wildcard_port_idna_and_trailing_dot_matching() -> None:
    matcher = DomainMatcher(
        LocalNetworkPolicy(
            mode="allowlist",
            allowed_domains=(
                "example.com",
                "*.sub.example.com:8443",
                "münich.example:443",
            ),
        )
    )
    assert matcher.allows("example.com", 443)
    assert matcher.allows("EXAMPLE.COM.", 443)
    assert not matcher.allows("www.example.com", 443)
    assert matcher.allows("a.sub.example.com", 8443)
    assert not matcher.allows("a.sub.example.com", 443)
    assert matcher.allows("münich.example", 443)
    assert matcher.allows("xn--mnich-kva.example", 443)


def test_deny_rules_win_over_allowlist_and_unrestricted() -> None:
    policy = LocalNetworkPolicy(
        mode="allowlist",
        allowed_domains=("*.example.com",),
        denied_domains=("blocked.example.com",),
    )
    matcher = DomainMatcher(policy)
    assert matcher.allows("ok.example.com", 443)
    assert not matcher.allows("blocked.example.com", 443)

    unrestricted = DomainMatcher(
        LocalNetworkPolicy(mode="unrestricted", denied_domains=("blocked.example",))
    )
    assert unrestricted.allows("anything.example", 80)
    assert not unrestricted.allows("blocked.example", 80)


def test_ipv6_port_requires_brackets_and_ambiguous_forms_are_rejected() -> None:
    matcher = DomainMatcher(
        LocalNetworkPolicy(
            mode="allowlist",
            allowed_domains=("[2001:db8::1]:443",),
        )
    )
    assert matcher.allows("2001:db8::1", 443)
    assert not matcher.allows("2001:db8::1", 8443)


@pytest.mark.parametrize(
    ("address", "flags", "reason"),
    [
        (
            "169.254.169.254",
            {"allow_private_network": True, "allow_loopback": True},
            "metadata",
        ),
        (
            "100.100.100.200",
            {"allow_private_network": True, "allow_loopback": True},
            "metadata",
        ),
        (
            "fe80::1",
            {"allow_private_network": True, "allow_loopback": True},
            "link-local",
        ),
        (
            "224.0.0.1",
            {"allow_private_network": True, "allow_loopback": True},
            "multicast",
        ),
        (
            "0.0.0.0",
            {"allow_private_network": True, "allow_loopback": True},
            "unspecified",
        ),
        (
            "255.255.255.255",
            {"allow_private_network": True, "allow_loopback": True},
            "broadcast",
        ),
        (
            "240.0.0.1",
            {"allow_private_network": True, "allow_loopback": True},
            "reserved",
        ),
        (
            "127.0.0.1",
            {"allow_private_network": True, "allow_loopback": False},
            "loopback",
        ),
        (
            "10.0.0.1",
            {"allow_private_network": False, "allow_loopback": True},
            "private-network",
        ),
        (
            "100.64.0.1",
            {"allow_private_network": False, "allow_loopback": True},
            "private-network",
        ),
        (
            "fd00::1",
            {"allow_private_network": False, "allow_loopback": True},
            "private-network",
        ),
    ],
)
def test_address_classes_stay_denied(address, flags, reason) -> None:
    policy = LocalNetworkPolicy(mode="unrestricted", **flags)
    guard = ResolvedAddressGuard(policy, host_interfaces=set())
    assert guard.denial_reason(ipaddress.ip_address(address), 443) == reason


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("::ffff:127.0.0.1", True),
        ("::ffff:10.0.0.1", True),
        ("2002:7f00:1::", True),
        ("64:ff9b::7f00:1", True),
        ("64:ff9b:1::a00:1", True),
        ("93.184.216.34", False),
    ],
)
def test_embedded_ipv4_forms_only_add_denials(address, expected) -> None:
    policy = LocalNetworkPolicy(mode="unrestricted")
    guard = ResolvedAddressGuard(policy, host_interfaces=set())
    assert (
        guard.denial_reason(ipaddress.ip_address(address), 443) is not None
    ) is expected


def test_private_and_loopback_flags_opt_in() -> None:
    guard = ResolvedAddressGuard(
        LocalNetworkPolicy(
            mode="unrestricted",
            allow_private_network=True,
            allow_loopback=True,
        ),
        host_interfaces={ipaddress.ip_address("192.168.1.10")},
    )
    assert guard.denial_reason(ipaddress.ip_address("10.0.0.5"), 80) is None
    assert guard.denial_reason(ipaddress.ip_address("127.0.0.1"), 80) is None
    assert (
        guard.denial_reason(ipaddress.ip_address("192.168.1.10"), 80)
        == "host-interface"
    )


def test_explicit_ip_literal_exception_and_deny_precedence() -> None:
    policy = LocalNetworkPolicy(
        mode="allowlist",
        allowed_domains=("10.0.0.5:22", "10.0.0.6:22"),
        denied_domains=("10.0.0.6:22",),
    )
    guard = ResolvedAddressGuard(policy, host_interfaces=set())
    assert guard.denial_reason(ipaddress.ip_address("10.0.0.5"), 22) is None
    assert (
        guard.denial_reason(ipaddress.ip_address("10.0.0.5"), 23) == "private-network"
    )
    assert guard.denial_reason(ipaddress.ip_address("10.0.0.6"), 22) == "denied-address"


def test_resolution_is_checked_once_and_filters_denied_addresses() -> None:
    calls = []

    def resolver(hostname: str, port: int):
        calls.append((hostname, port))
        return [ipaddress.ip_address("169.254.169.254"), PUBLIC]

    result = resolve_and_check(
        "example.com",
        443,
        LocalNetworkPolicy(mode="allowlist", allowed_domains=("example.com",)),
        resolver=resolver,
    )
    assert calls == [("example.com", 443)]
    assert result.addresses == (PUBLIC,)
    assert result.hostname == "example.com"


def test_resolution_fails_when_every_address_is_denied() -> None:
    with pytest.raises(NetworkPolicyError):
        resolve_and_check(
            "example.com",
            443,
            LocalNetworkPolicy(mode="allowlist", allowed_domains=("example.com",)),
            resolver=lambda _host, _port: [ipaddress.ip_address("10.0.0.1")],
        )


def test_denied_domain_is_rejected_before_resolution() -> None:
    def resolver(_host: str, _port: int):
        raise AssertionError("denied destination must not be resolved")

    with pytest.raises(NetworkPolicyError):
        resolve_and_check(
            "blocked.example",
            443,
            LocalNetworkPolicy(
                mode="unrestricted",
                denied_domains=("blocked.example",),
            ),
            resolver=resolver,
        )


def test_resolution_result_cap_and_empty_result_fail() -> None:
    policy = LocalNetworkPolicy(mode="unrestricted")
    with pytest.raises(NetworkPolicyError):
        resolve_and_check("example.com", 443, policy, resolver=lambda _h, _p: [])
    with pytest.raises(NetworkPolicyError):
        resolve_and_check(
            "example.com",
            443,
            policy,
            resolver=lambda _h, _p: [PUBLIC] * 33,
        )


@pytest.mark.asyncio
async def test_async_resolver_handles_literals_and_dns() -> None:
    assert await resolve_host_addresses_async("93.184.216.34", 443) == (PUBLIC,)
    addresses = await resolve_host_addresses_async("localhost", 80)
    assert addresses
    assert all(address.is_loopback for address in addresses)


def test_host_interface_discovery_excludes_loopback() -> None:
    addresses = _host_interface_addresses()
    assert all(
        not address.is_loopback and not address.is_unspecified for address in addresses
    )
