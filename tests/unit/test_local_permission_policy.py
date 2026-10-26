from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.auth.models import Role
from astrbot.core.computer.local_policy import (
    LocalFilesystemPolicy,
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.config.default import get_local_permission_defaults
from astrbot.core.tools.computer_tools.util import (
    check_admin_permission,
    check_local_execution_permission,
    check_local_file_permission,
    get_local_permission_policy,
    resolve_local_permission_role,
)
from tests.fixtures.auth import attach_authorized_tool_context


def _make_context(
    *,
    effective_role: Role | None = None,
    permissions: dict | None = None,
    runtime: str = "local",
) -> ContextWrapper:
    config_holder = SimpleNamespace(
        get_config=lambda umo: {  # noqa: ARG005
            "provider_settings": {
                "computer_use_runtime": runtime,
                **(
                    {"computer_use_local_permissions": permissions}
                    if permissions is not None
                    else {}
                ),
            }
        }
    )
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:user-1",
        get_sender_id=lambda: "user-1",
    )
    attach_authorized_tool_context(
        event,
        config_holder,
        "tool.local_exec",
        "tool.python_exec",
        "tool.file_read",
        "tool.file_write",
        effective_role=effective_role,
    )
    return ContextWrapper(context=SimpleNamespace(context=config_holder, event=event))


def _role_policy(
    *,
    allow_execution: bool,
    scope: str,
    mode: str = "off",
    private: bool = False,
    loopback: bool = False,
    deny_read: tuple[str, ...] = (),
    deny_write: tuple[str, ...] = (),
    socket_mode: str = "deny",
) -> dict:
    return {
        "allow_execution": allow_execution,
        "filesystem_scope": scope,
        "network": {
            "mode": mode,
            "allowed_domains": [],
            "denied_domains": [],
            "allow_private_network": private,
            "allow_loopback": loopback,
        },
        "filesystem": {
            "deny_read": list(deny_read),
            "deny_write": list(deny_write),
        },
        "unix_sockets": {"mode": socket_mode, "allowed_paths": []},
    }


def test_local_permission_defaults_are_platform_independent() -> None:
    defaults = get_local_permission_defaults()
    assert defaults["member"]["filesystem_scope"] == "workspace"
    assert defaults["member"]["network"]["mode"] == "off"
    assert defaults["admin"]["filesystem_scope"] == "host"
    assert defaults["admin"]["network"]["mode"] == "unrestricted"
    assert defaults["admin"]["network"]["allow_private_network"] is True
    assert defaults["admin"]["unix_sockets"]["mode"] == "allow_all"


@pytest.mark.asyncio
async def test_member_policy_disables_execution_by_default() -> None:
    context = _make_context(effective_role=Role.MEMBER)
    await resolve_local_permission_role(context)
    policy = get_local_permission_policy(context)
    assert policy.allow_execution is False
    assert policy.filesystem_scope in {"workspace", "none"}


@pytest.mark.asyncio
async def test_admin_policy_allows_execution() -> None:
    context = _make_context(effective_role=Role.INSTANCE_OPERATOR)
    await resolve_local_permission_role(context)
    policy = get_local_permission_policy(context)
    assert policy.allow_execution is True
    assert policy.allow_network is True


@pytest.mark.asyncio
async def test_file_tools_are_denied_when_scope_is_none() -> None:
    context = _make_context(
        effective_role=Role.MEMBER,
        permissions={
            "member": _role_policy(
                allow_execution=False,
                scope="none",
            )
        },
    )
    error = await check_local_file_permission(context)
    assert error is not None
    assert "disabled" in error


@pytest.mark.asyncio
async def test_file_tools_resolve_admin_without_execution_marker() -> None:
    context = _make_context(
        effective_role=Role.INSTANCE_OPERATOR,
        permissions={
            "member": _role_policy(allow_execution=False, scope="none"),
            "admin": _role_policy(
                allow_execution=True,
                scope="host",
                mode="unrestricted",
                private=True,
                loopback=True,
                socket_mode="allow_all",
            ),
        },
    )
    assert getattr(context.context.event, "_computer_permission_role", None) is None
    error = await check_local_file_permission(context)
    assert error is None
    assert get_local_permission_policy(context).filesystem_scope == "host"


@pytest.mark.asyncio
async def test_execution_is_denied_when_policy_disables_it() -> None:
    context = _make_context(effective_role=Role.MEMBER)
    _policy, error = await check_local_execution_permission(context, "Shell execution")
    assert error is not None
    assert "disabled" in error


@pytest.mark.asyncio
async def test_execution_denial_points_to_authorization_role_binding() -> None:
    context = _make_context(effective_role=Role.MEMBER)
    _policy, error = await check_local_execution_permission(context, "Shell execution")
    assert error is not None
    assert "More Features -> Authorization" in error
    assert "`instance_operator`" in error
    assert "`im:test-platform:test-bot:test-user`" in error
    assert "`allow_execution`" in error or "Allow code execution" in error
    assert "`Execute code`" not in error
    assert "Access Control" not in error


@pytest.mark.asyncio
async def test_non_local_runtime_skips_permission_matrix() -> None:
    context = _make_context(effective_role=Role.MEMBER, runtime="sandbox")
    policy, error = await check_local_execution_permission(context, "Shell execution")
    assert policy is None
    assert error is None


@pytest.mark.asyncio
async def test_unknown_permission_operation_fails_loudly() -> None:
    context = _make_context(effective_role=Role.INSTANCE_OPERATOR)
    with pytest.raises(ValueError, match="Unsupported local permission operation"):
        await check_admin_permission(context, "Not a registered operation")


@pytest.mark.asyncio
async def test_native_admin_policy_does_not_require_isolation(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": "unsupported"},
    )
    context = _make_context(
        effective_role=Role.INSTANCE_OPERATOR,
        permissions={
            "admin": _role_policy(
                allow_execution=True,
                scope="host",
                mode="unrestricted",
                private=True,
                loopback=True,
                socket_mode="allow_all",
            )
        },
    )
    await resolve_local_permission_role(context)
    policy = get_local_permission_policy(context)
    assert policy.allow_execution is True
    assert policy.requires_sandbox is False
    _policy, error = await check_local_execution_permission(context, "Shell execution")
    assert error is None


@pytest.mark.asyncio
async def test_host_unrestricted_with_a_deny_rule_requires_isolation(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": "missing", "backend": "bubblewrap"},
    )
    context = _make_context(
        effective_role=Role.INSTANCE_OPERATOR,
        permissions={
            "admin": _role_policy(
                allow_execution=True,
                scope="host",
                mode="unrestricted",
                private=True,
                loopback=True,
                deny_read=(str(tmp_path / "secret"),),
                socket_mode="allow_all",
            )
        },
    )
    await resolve_local_permission_role(context)
    policy = get_local_permission_policy(context)
    assert policy.allow_execution is False
    assert policy.execution_disabled_reason
    _policy, error = await check_local_execution_permission(context, "Shell execution")
    assert error is not None
    assert "isolation unavailable" in error.lower()
    assert "Entire environment" in error


@pytest.mark.asyncio
async def test_malformed_saved_policy_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": "detected"},
    )
    context = _make_context(
        effective_role=Role.INSTANCE_OPERATOR,
        permissions={"admin": {"allow_network": True, "filesystem_scope": "host"}},
    )
    await resolve_local_permission_role(context)
    policy = get_local_permission_policy(context)
    assert policy.allow_execution is False
    assert policy.execution_disabled_reason
    assert "invalid" in policy.execution_disabled_reason.lower()
    assert await check_local_file_permission(context) is not None


@pytest.mark.asyncio
async def test_sandbox_policy_notice_is_mode_specific(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": "detected"},
    )
    context = _make_context(
        effective_role=Role.INSTANCE_OPERATOR,
        permissions={
            "admin": _role_policy(
                allow_execution=True,
                scope="workspace",
                mode="allowlist",
            )
        },
    )
    await resolve_local_permission_role(context)
    policy = get_local_permission_policy(context)
    assert "allowlist" in policy.network_notice
    assert policy.network == LocalNetworkPolicy(mode="allowlist")
    assert policy.filesystem == LocalFilesystemPolicy()
    assert policy.unix_sockets == LocalUnixSocketPolicy(mode="deny")
    assert isinstance(policy.sandbox, LocalSandboxPolicy)
