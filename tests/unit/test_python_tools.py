import platform
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.auth.models import Role
from astrbot.core.tools.computer_tools.python import LocalPythonTool, handle_result
from tests.fixtures.auth import attach_authorized_tool_context


def test_local_python_tool_description_contains_os():
    """测试 LocalPythonTool 的描述中是否包含当前操作系统信息和兼容性提示"""
    tool = LocalPythonTool()
    current_os = platform.system()
    assert current_os in tool.description
    assert "Python environment" in tool.description
    assert "system-compatible" in tool.description


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime_settings",
    [
        {},
        {"computer_use_runtime": "none"},
        {"computer_use_runtime": "sandbox"},
        {"computer_use_runtime": "invalid"},
        {"computer_use_runtime": None},
    ],
)
@pytest.mark.parametrize("role", ["member", "admin"])
async def test_local_python_tool_rejects_nonlocal_runtime(runtime_settings, role):
    """Reject retained local tools before accessing the host, regardless of role."""
    get_local_booter = MagicMock()
    event = SimpleNamespace(
        unified_msg_origin="onebot:FriendMessage:user123",
        role=role,
        get_platform_name=lambda: "onebot",
    )
    runtime = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {
                **runtime_settings,
                "computer_use_require_admin": False,
            }
        },
        computer_runtime=SimpleNamespace(get_local_booter=get_local_booter),
    )
    attach_authorized_tool_context(event, runtime, "tool.python_exec")
    context = ContextWrapper(
        context=SimpleNamespace(event=event, context=runtime),
        tool_call_timeout=60,
    )

    result = await LocalPythonTool().call(context, code="print('ok')")

    get_local_booter.assert_not_called()
    assert result == "Error executing code: only local runtime is supported."


@pytest.mark.asyncio
async def test_local_python_tool_uses_session_workspace(tmp_path, monkeypatch):
    """Local Python execution should use the same workspace as local shell."""
    tool = LocalPythonTool()
    python_exec = AsyncMock(
        return_value={"data": {"output": {"text": "ok", "images": []}, "error": ""}}
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root",
        lambda umo: tmp_path / umo.replace(":", "_"),
    )

    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="admin",
        get_platform_name=lambda: "onebot",
    )
    runtime = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {
                "computer_use_runtime": "local",
                "computer_use_local_permissions": {
                    "admin": {
                        "allow_execution": True,
                        "filesystem_scope": "host",
                        "network": {
                            "mode": "unrestricted",
                            "allowed_domains": [],
                            "denied_domains": [],
                            "allow_private_network": True,
                            "allow_loopback": True,
                        },
                        "filesystem": {"deny_read": [], "deny_write": []},
                        "unix_sockets": {"mode": "allow_all", "allowed_paths": []},
                    }
                },
            }
        },
        computer_runtime=SimpleNamespace(
            get_local_booter=lambda: SimpleNamespace(
                python=SimpleNamespace(exec=python_exec)
            )
        ),
    )
    attach_authorized_tool_context(
        event,
        runtime,
        "tool.python_exec",
        effective_role=Role.INSTANCE_OPERATOR,
    )
    context = ContextWrapper(
        context=SimpleNamespace(event=event, context=runtime),
        tool_call_timeout=60,
    )

    await tool.call(context, code="print('ok')", timeout_seconds=30)

    workspace = tmp_path / "onebot_GroupMessage_12345"
    assert workspace.is_dir()
    python_exec.assert_awaited_once_with(
        "print('ok')",
        timeout_seconds=30,
        silent=False,
        cwd=str(workspace.resolve(strict=False)),
        spec=None,
    )


@pytest.mark.asyncio
async def test_local_python_tool_accepts_timeout_alias(tmp_path, monkeypatch):
    tool = LocalPythonTool()
    python_exec = AsyncMock(
        return_value={"data": {"output": {"text": "ok", "images": []}, "error": ""}}
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root",
        lambda umo: tmp_path / umo.replace(":", "_"),
    )

    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="admin",
        get_platform_name=lambda: "onebot",
    )
    runtime = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {
                "computer_use_runtime": "local",
                "computer_use_local_permissions": {
                    "admin": {
                        "allow_execution": True,
                        "filesystem_scope": "host",
                        "network": {
                            "mode": "unrestricted",
                            "allowed_domains": [],
                            "denied_domains": [],
                            "allow_private_network": True,
                            "allow_loopback": True,
                        },
                        "filesystem": {"deny_read": [], "deny_write": []},
                        "unix_sockets": {"mode": "allow_all", "allowed_paths": []},
                    }
                },
            }
        },
        computer_runtime=SimpleNamespace(
            get_local_booter=lambda: SimpleNamespace(
                python=SimpleNamespace(exec=python_exec)
            )
        ),
    )
    attach_authorized_tool_context(
        event,
        runtime,
        "tool.python_exec",
        effective_role=Role.INSTANCE_OPERATOR,
    )
    context = ContextWrapper(
        context=SimpleNamespace(event=event, context=runtime),
        tool_call_timeout=60,
    )

    await tool.call(context, code="print('ok')", timeout=12)

    python_exec.assert_awaited_once_with(
        "print('ok')",
        timeout_seconds=12,
        silent=False,
        cwd=str((tmp_path / "onebot_GroupMessage_12345").resolve(strict=False)),
        spec=None,
    )


@pytest.mark.asyncio
async def test_local_python_omits_network_policy_notice(tmp_path, monkeypatch):
    python_exec = AsyncMock(
        return_value={
            "data": {
                "output": {"text": "ok", "images": []},
                "error": "",
            }
        },
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.python.workspace_root",
        lambda umo: tmp_path / umo.replace(":", "_"),
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": "detected"},
    )
    event = SimpleNamespace(
        unified_msg_origin="onebot:GroupMessage:12345",
        role="admin",
        get_platform_name=lambda: "onebot",
    )
    runtime = SimpleNamespace(
        get_config=lambda **_kwargs: {
            "provider_settings": {
                "computer_use_runtime": "local",
                "computer_use_local_permissions": {
                    "admin": {
                        "allow_execution": True,
                        "filesystem_scope": "host",
                        "network": {
                            "mode": "off",
                            "allowed_domains": [],
                            "denied_domains": [],
                            "allow_private_network": False,
                            "allow_loopback": False,
                        },
                        "filesystem": {"deny_read": [], "deny_write": []},
                        "unix_sockets": {"mode": "deny", "allowed_paths": []},
                    }
                },
            }
        },
        computer_runtime=SimpleNamespace(
            get_local_booter=lambda: SimpleNamespace(
                python=SimpleNamespace(exec=python_exec)
            )
        ),
    )
    attach_authorized_tool_context(
        event,
        runtime,
        "tool.python_exec",
        effective_role=Role.INSTANCE_OPERATOR,
    )
    context = ContextWrapper(
        context=SimpleNamespace(event=event, context=runtime),
        tool_call_timeout=60,
    )

    result = await LocalPythonTool().call(context, code="print('ok')")
    output = [part.text for part in result.content]
    assert output == ["ok"]

    python_exec.side_effect = RuntimeError("execution failed")
    result = await LocalPythonTool().call(context, code="print('ok')")
    assert result == "Error executing code: execution failed"


@pytest.mark.asyncio
async def test_handle_result_reports_sandbox_denials():
    event = SimpleNamespace(get_platform_name=lambda: "cli")
    result = await handle_result(
        {
            "data": {
                "output": {"text": "ok", "images": []},
                "error": "",
                "violations": [
                    {
                        "kind": "network",
                        "reason": "denied by policy",
                        "target": "example.com",
                    }
                ],
            }
        },
        event,
    )
    text = " ".join(part.text for part in result.content)
    assert "sandbox denials" in text
    assert "network: denied by policy (example.com)" in text
