from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.config.default import get_local_permission_defaults
from astrbot.core.tools.computer_tools.util import (
    check_local_execution_permission,
    check_local_file_permission,
    get_local_permission_policy,
)
from tests.fixtures.auth import attach_authorized_tool_context


def _make_context(
    *,
    role: str = "member",
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
        role=role,
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
    )
    return ContextWrapper(context=SimpleNamespace(context=config_holder, event=event))


def test_local_permission_defaults_disable_windows_member_access() -> None:
    windows = get_local_permission_defaults("Windows")
    posix = get_local_permission_defaults("Linux")
    assert windows["member"]["filesystem_scope"] == "none"
    assert windows["admin"]["filesystem_scope"] == "host"
    assert posix["member"]["filesystem_scope"] == "workspace"
    assert posix["admin"]["filesystem_scope"] == "workspace"


def test_member_policy_disables_execution_by_default() -> None:
    policy = get_local_permission_policy(_make_context(role="member"))
    assert policy.allow_execution is False
    assert policy.filesystem_scope in {"workspace", "none"}


def test_admin_policy_allows_execution() -> None:
    policy = get_local_permission_policy(_make_context(role="admin"))
    assert policy.allow_execution is True
    assert policy.allow_network is True


def test_file_tools_are_denied_when_scope_is_none() -> None:
    context = _make_context(
        role="member",
        permissions={
            "member": {
                "allow_execution": False,
                "allow_network": False,
                "filesystem_scope": "none",
            }
        },
    )
    error = check_local_file_permission(context)
    assert error is not None
    assert "disabled" in error


@pytest.mark.asyncio
async def test_execution_is_denied_when_policy_disables_it() -> None:
    context = _make_context(role="member")
    _policy, error = await check_local_execution_permission(context, "Shell execution")
    assert error is not None
    assert "disabled" in error


@pytest.mark.asyncio
async def test_non_local_runtime_skips_permission_matrix() -> None:
    context = _make_context(role="member", runtime="sandbox")
    policy, error = await check_local_execution_permission(context, "Shell execution")
    assert policy is None
    assert error is None
