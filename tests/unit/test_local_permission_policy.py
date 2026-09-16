from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.auth.models import Role
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


def test_local_permission_defaults_disable_windows_member_access() -> None:
    windows = get_local_permission_defaults("Windows")
    posix = get_local_permission_defaults("Linux")
    assert windows["member"]["filesystem_scope"] == "none"
    assert windows["admin"]["filesystem_scope"] == "host"
    assert posix["member"]["filesystem_scope"] == "workspace"
    assert posix["admin"]["filesystem_scope"] == "workspace"


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
            "member": {
                "allow_execution": False,
                "allow_network": False,
                "filesystem_scope": "none",
            }
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
            "member": {
                "allow_execution": False,
                "allow_network": False,
                "filesystem_scope": "none",
            },
            "admin": {
                "allow_execution": True,
                "allow_network": True,
                "filesystem_scope": "host",
            },
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
