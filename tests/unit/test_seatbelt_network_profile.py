"""Seatbelt network, CA, socket and environment handoff generation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from astrbot.core.computer.local_policy import (
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.computer.process_sandbox import SandboxProxyEndpoint, SandboxSpec
from astrbot.core.computer.process_sandbox.seatbelt import SeatbeltProcessSandbox

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Seatbelt profiles use macOS path and CA semantics.",
)


def _sandbox(monkeypatch) -> SeatbeltProcessSandbox:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.seatbelt.shutil.which",
        lambda _name, **_kwargs: "/usr/bin/sandbox-exec",
    )
    return SeatbeltProcessSandbox()


def _endpoint() -> SandboxProxyEndpoint:
    return SandboxProxyEndpoint(
        token="test-token",
        http_port=43210,
        socks_port=43211,
        platform="darwin",
    )


def _command(monkeypatch, spec: SandboxSpec) -> list[str]:
    return _sandbox(monkeypatch).build_command(
        [sys.executable, "-c", "pass"],
        spec,
    )


def _profile(command: list[str]) -> str:
    return command[command.index("-p") + 1]


def test_off_denies_all_network_and_adds_no_inbound_rule(monkeypatch, tmp_path) -> None:
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="off"),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )
    profile = _profile(
        _command(monkeypatch, SandboxSpec(workspace=tmp_path, policy=policy))
    )
    assert "(deny network*)" in profile
    assert "(allow network*)" not in profile
    assert "network-inbound" not in profile
    assert "network-bind" not in profile


def test_proxy_modes_allow_only_exact_loopback_ports(monkeypatch, tmp_path) -> None:
    for mode in ("allowlist", "unrestricted"):
        policy = LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="workspace",
            network=LocalNetworkPolicy(mode=mode, allowed_domains=("example.com",)),
            unix_sockets=LocalUnixSocketPolicy(mode="deny"),
        )
        spec = SandboxSpec(
            workspace=tmp_path,
            policy=policy,
            proxy=SandboxProxyEndpoint(
                token="secret-token",
                http_port=43210,
                socks_port=43211,
                platform="darwin",
            ),
        )
        command = _command(monkeypatch, spec)
        profile = _profile(command)
        assert "(deny network*)" in profile
        assert "localhost:43210" in profile
        assert "localhost:43211" in profile
        assert "(allow network*)" not in profile
        assert "secret-token" not in " ".join(command)


def test_ca_paths_are_read_only_and_token_is_not_in_argv(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ASTRBOT_SANDBOX_CA_FILE", str(tmp_path / "ca.pem"))
    (tmp_path / "ca.pem").write_text("test", encoding="utf-8")
    spec = SandboxSpec(
        workspace=tmp_path,
        policy=LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="workspace",
            network=LocalNetworkPolicy(mode="allowlist", allowed_domains=("a.com",)),
        ),
        proxy=SandboxProxyEndpoint(
            token="abc", http_port=1, socks_port=2, platform="darwin"
        ),
    )
    command = _command(monkeypatch, spec)
    profile = _profile(command)
    assert (
        any(
            path.startswith("/etc/ssl")
            for path in profile.splitlines()
            if "subpath" in path
        )
        or "/etc/ssl" in profile
    )
    assert "abc" not in " ".join(command)
    assert "sandbox-exec" in command[0]


def test_macos_socket_modes_and_literal_paths(monkeypatch, tmp_path) -> None:
    socket_path = tmp_path / "api.sock"
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="allowlist", allowed_domains=("a.com",)),
        unix_sockets=LocalUnixSocketPolicy(
            mode="deny", allowed_paths=(str(socket_path),)
        ),
    )
    profile = _profile(
        _command(
            monkeypatch,
            SandboxSpec(workspace=tmp_path, policy=policy, proxy=_endpoint()),
        )
    )
    assert "remote unix-socket" in profile
    assert str(socket_path) in profile
    assert "(allow system-socket (socket-domain AF_UNIX))" in profile
    allow_all = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="allowlist", allowed_domains=("a.com",)),
        unix_sockets=LocalUnixSocketPolicy(mode="allow_all"),
    )
    allow_profile = _profile(
        _command(
            monkeypatch,
            SandboxSpec(workspace=tmp_path, policy=allow_all, proxy=_endpoint()),
        )
    )
    assert "(allow system-socket (socket-domain AF_UNIX))" in allow_profile
    assert "(allow network-outbound (remote unix-socket))" in allow_profile


def test_macos_socket_paths_expand_home(monkeypatch, tmp_path) -> None:
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="allowlist", allowed_domains=("a.com",)),
        unix_sockets=LocalUnixSocketPolicy(
            mode="deny", allowed_paths=("~/astrbot-test.sock",)
        ),
    )
    profile = _profile(
        _command(
            monkeypatch,
            SandboxSpec(workspace=tmp_path, policy=policy, proxy=_endpoint()),
        )
    )
    expanded = str(Path.home() / "astrbot-test.sock")
    assert f'path-literal "{expanded}"' in profile
    assert 'path-literal "~/astrbot-test.sock"' not in profile


def test_socket_allow_rules_are_not_injected_by_control_characters(
    monkeypatch, tmp_path
) -> None:
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="allowlist", allowed_domains=("a.com",)),
        unix_sockets=LocalUnixSocketPolicy(
            mode="deny", allowed_paths=("/tmp/sock\n(deny default)",)
        ),
    )
    profile = _profile(
        _command(
            monkeypatch,
            SandboxSpec(workspace=tmp_path, policy=policy, proxy=_endpoint()),
        )
    )
    assert profile.count("\n(deny default)") == 1


def test_profile_budget_fails_before_launch(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.seatbelt._MAX_PROFILE_BYTES",
        1,
    )
    with pytest.raises(RuntimeError, match="size budget"):
        _command(monkeypatch, SandboxSpec(workspace=tmp_path))


def test_host_scope_denies_ca_writes_after_host_grant(monkeypatch, tmp_path) -> None:
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("test", encoding="utf-8")
    monkeypatch.setenv("ASTRBOT_SANDBOX_CA_FILE", str(ca_file))
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="host",
        network=LocalNetworkPolicy(mode="unrestricted"),
        unix_sockets=LocalUnixSocketPolicy(mode="allow_all"),
    )
    profile = _profile(
        _command(
            monkeypatch,
            SandboxSpec(workspace=tmp_path, policy=policy, proxy=_endpoint()),
        )
    )
    assert f'(deny file-write* (literal "{ca_file}"))' in profile
