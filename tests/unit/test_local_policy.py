"""Tests for the immutable Local sandbox policy model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from astrbot.core.computer.local_policy import (
    MAX_DOMAIN_RULES,
    MAX_PATH_RULES,
    MAX_RULE_CHARACTERS,
    MAX_UNIX_PATHS,
    MAX_VALIDATION_ERRORS,
    LocalFilesystemPolicy,
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
    build_local_network_notice,
    default_policy,
    default_policy_dict,
    normalize_path_rule,
    parse_domain_rule,
    path_rule_matches,
    sandbox_policy_from_config,
)


def test_fresh_member_and_admin_defaults() -> None:
    member = default_policy("member")
    admin = default_policy("admin")
    assert member.filesystem_scope == "workspace"
    assert member.allow_execution is False
    assert member.network.mode == "off"
    assert member.network.allow_private_network is False
    assert member.unix_sockets.mode == "deny"
    assert admin.filesystem_scope == "host"
    assert admin.allow_execution is True
    assert admin.network.mode == "unrestricted"
    assert admin.network.allow_private_network is True
    assert admin.network.allow_loopback is True
    assert admin.unix_sockets.mode == "allow_all"
    assert admin.is_native is True
    assert admin.requires_sandbox is False


def test_defaults_are_independent_mutable_documents() -> None:
    first = default_policy_dict("member")
    first["network"]["allowed_domains"].append("example.com")
    assert default_policy_dict("member")["network"]["allowed_domains"] == []


def test_requires_sandbox_truth_table() -> None:
    native = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="host",
        network=LocalNetworkPolicy(
            mode="unrestricted",
            allow_private_network=True,
            allow_loopback=True,
        ),
        unix_sockets=LocalUnixSocketPolicy(mode="allow_all"),
    )
    assert native.requires_sandbox is False
    assert native.is_native is True

    cases = [
        LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="workspace",
            network=native.network,
            unix_sockets=native.unix_sockets,
        ),
        LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="host",
            network=LocalNetworkPolicy(
                mode="restricted" if False else "allowlist",
                allow_private_network=True,
                allow_loopback=True,
            ),
            unix_sockets=native.unix_sockets,
        ),
        LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="host",
            network=LocalNetworkPolicy(
                mode="unrestricted",
                allow_private_network=False,
                allow_loopback=True,
            ),
            unix_sockets=native.unix_sockets,
        ),
        LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="host",
            network=native.network,
            filesystem=LocalFilesystemPolicy(deny_read=("/secret",)),
            unix_sockets=native.unix_sockets,
        ),
        LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="host",
            network=native.network,
            unix_sockets=LocalUnixSocketPolicy(mode="deny"),
        ),
    ]
    assert all(policy.requires_sandbox for policy in cases)
    assert LocalSandboxPolicy(allow_execution=False).requires_sandbox is False


def test_parse_network_rule_forms_and_deny_precedence() -> None:
    rule = parse_domain_rule("*.Example.COM.:443")
    assert rule.pattern == "example.com"
    assert rule.wildcard is True
    assert rule.port == 443
    ipv6 = parse_domain_rule("[2001:db8::1]:8443")
    assert str(ipv6.address) == "2001:db8::1"
    assert ipv6.port == 8443
    assert parse_domain_rule("*").pattern == "*"


@pytest.mark.parametrize(
    "rule",
    [
        "",
        "example.com:0",
        "example.com:70000",
        "example.com:abc",
        "[2001:db8::1",
        "user@example.com",
        "**example.com",
        "example..com",
        "bad_label.example.com",
        "01.02.03.04",
    ],
)
def test_parse_domain_rule_rejects_malformed_values(rule: str) -> None:
    with pytest.raises(ValueError):
        parse_domain_rule(rule)


def test_sandbox_policy_validation_reports_unknown_keys_and_caps() -> None:
    value = {
        "allow_execution": "yes",
        "filesystem_scope": "elsewhere",
        "network": {
            "mode": "sometimes",
            "allowed_domains": [f"host{index}.example.com" for index in range(300)],
            "denied_domains": ["bad host"],
            "allow_private_network": "yes",
            "allow_loopback": 1,
            "unexpected": True,
        },
        "filesystem": {
            "deny_read": ["" for _ in range(MAX_PATH_RULES + 1)],
            "deny_write": "/etc/passwd",
            "unexpected": [],
        },
        "unix_sockets": {
            "mode": "maybe",
            "allowed_paths": ["/tmp/socket" for _ in range(MAX_UNIX_PATHS + 1)]
            if sys.platform != "darwin"
            else [],
            "unexpected": True,
        },
        "unknown": True,
    }
    _policy, errors = sandbox_policy_from_config(value, role="member")
    assert errors
    assert len(errors) <= MAX_VALIDATION_ERRORS
    joined = "\n".join(errors)
    assert "Unknown Local permission key" in joined
    assert "allow_execution must be a boolean" in joined
    assert "network.mode" in joined
    assert f"at most {MAX_DOMAIN_RULES}" in joined
    assert "filesystem_scope" in joined


def test_validation_never_silently_drops_a_deny_rule(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("value", encoding="utf-8")
    value = {
        "allow_execution": True,
        "filesystem_scope": "workspace",
        "network": {"mode": "off"},
        "filesystem": {"deny_read": [str(secret), "relative-path"]},
        "unix_sockets": {"mode": "deny", "allowed_paths": []},
    }
    policy, errors = sandbox_policy_from_config(value, role="member")
    assert policy.filesystem.deny_read == (secret.as_posix(),)
    assert any("filesystem.deny_read" in error for error in errors)


def test_scope_none_and_execution_off_force_network_off() -> None:
    value = {
        "allow_execution": True,
        "filesystem_scope": "none",
        "network": {
            "mode": "unrestricted",
            "allow_private_network": True,
            "allow_loopback": True,
        },
        "unix_sockets": {"mode": "allow_all", "allowed_paths": []},
    }
    policy, errors = sandbox_policy_from_config(value, role="admin")
    assert errors == []
    assert policy.allow_execution is False
    assert policy.network.mode == "off"
    assert policy.unix_sockets.mode == "deny"


def test_fresh_restricted_policy_keeps_address_flags_off() -> None:
    value = {
        "allow_execution": True,
        "filesystem_scope": "workspace",
        "network": {"mode": "allowlist"},
    }
    policy, errors = sandbox_policy_from_config(value, role="member")
    assert errors == []
    assert policy.network.allow_private_network is False
    assert policy.network.allow_loopback is False
    assert policy.requires_sandbox is True


def test_path_rules_require_anchors_and_reject_bad_forms(tmp_path: Path) -> None:
    assert normalize_path_rule("~/.ssh") == "~/.ssh"
    assert normalize_path_rule(f"{tmp_path}/*.env")
    for rule in (
        "relative/path",
        "**/.env",
        "/tmp/../secret",
        "/tmp/trailing/",
        "/tmp/nul\x00byte",
        "/tmp/[",
    ):
        with pytest.raises(ValueError):
            normalize_path_rule(rule)


def test_path_rule_matching_supports_globs_and_descendants(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("value", encoding="utf-8")
    assert path_rule_matches(str(secret), secret)
    assert path_rule_matches(str(secret), secret / "child")
    assert path_rule_matches(str(tmp_path / "*"), secret)
    assert not path_rule_matches(str(tmp_path / "*.txt"), secret / "child.txt")


def test_macos_only_socket_paths_are_rejected_on_linux(tmp_path: Path) -> None:
    socket_path = tmp_path / "socket"
    value = {
        "allow_execution": True,
        "filesystem_scope": "workspace",
        "network": {"mode": "allowlist", "allowed_domains": ["example.com"]},
        "unix_sockets": {"mode": "deny", "allowed_paths": [str(socket_path)]},
    }
    _policy, errors = sandbox_policy_from_config(value, role="member", platform="linux")
    assert any("supported only on macOS" in error for error in errors)
    policy, mac_errors = sandbox_policy_from_config(
        value, role="member", platform="darwin"
    )
    assert mac_errors == []
    assert policy.unix_sockets.allowed_paths == (socket_path.as_posix(),)


def test_socket_allow_all_rejects_allowed_paths(tmp_path: Path) -> None:
    value = {
        "unix_sockets": {
            "mode": "allow_all",
            "allowed_paths": [str(tmp_path / "socket")],
        }
    }
    _policy, errors = sandbox_policy_from_config(value, role="admin", platform="darwin")
    assert any("requires socket mode deny" in error for error in errors)


def test_network_notice_never_contains_rules() -> None:
    secret_domain = "private.internal.example"
    secret_path = "/home/operator/.ssh/id_ed25519"
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(
            mode="allowlist",
            allowed_domains=(secret_domain,),
            denied_domains=("blocked.example",),
        ),
        filesystem=LocalFilesystemPolicy(deny_read=(secret_path,)),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )
    notice = build_local_network_notice(policy)
    assert "allowlist" in notice
    assert secret_domain not in notice
    assert secret_path not in notice
    native_notice = build_local_network_notice(default_policy("admin"))
    assert "natively" in native_notice
    assert "no sandbox guarantee" in native_notice.lower()


def test_long_rules_are_bounded() -> None:
    _policy, errors = sandbox_policy_from_config(
        {"network": {"allowed_domains": ["a" * (MAX_RULE_CHARACTERS + 1)]}},
        role="member",
    )
    assert any("at most" in error for error in errors)


def test_unrestricted_mode_ignores_stale_allowlist_but_keeps_denies() -> None:
    policy, errors = sandbox_policy_from_config(
        {
            "allow_execution": True,
            "filesystem_scope": "host",
            "network": {
                "mode": "unrestricted",
                "allowed_domains": ["stale.example"],
                "denied_domains": ["blocked.example"],
                "allow_private_network": True,
                "allow_loopback": True,
            },
            "unix_sockets": {"mode": "allow_all"},
        },
        role="admin",
    )
    assert errors == []
    assert policy.network.allowed_domains == ()
    assert policy.network.denied_domains == ("blocked.example",)
    assert policy.requires_sandbox is True


def test_nested_rule_values_round_trip(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("value", encoding="utf-8")
    socket_path = tmp_path / "api.sock"
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(
            mode="allowlist",
            allowed_domains=("*.example.com:8443",),
            denied_domains=("blocked.example.com",),
        ),
        filesystem=LocalFilesystemPolicy(
            deny_read=(secret.as_posix(),),
            deny_write=(tmp_path.as_posix(),),
        ),
        unix_sockets=LocalUnixSocketPolicy(
            mode="deny", allowed_paths=(socket_path.as_posix(),)
        ),
    )
    parsed, errors = sandbox_policy_from_config(
        policy.to_dict(),
        role="member",
        platform="darwin",
    )
    assert errors == []
    assert parsed == policy
