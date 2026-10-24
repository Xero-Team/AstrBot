import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.computer_tools import util as computer_util
from astrbot.core.tools.computer_tools.shipyard_neo.browser import (
    BrowserBatchExecTool,
    BrowserExecTool,
    RunBrowserSkillTool,
)
from astrbot.core.tools.computer_tools.shipyard_neo.neo_skills import (
    GetExecutionHistoryTool,
)
from tests.fixtures.auth import attach_authorized_tool_context


class _FakeBrowser:
    async def exec(self, **kwargs):
        return {
            "ok": True,
            "cmd": kwargs["cmd"],
        }


class _RecordingBrowser:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def exec(self, **kwargs):
        self.calls.append(("exec", kwargs))
        return {"ok": True}

    async def exec_batch(self, **kwargs):
        self.calls.append(("exec_batch", kwargs))
        return {"ok": True}

    async def run_skill(self, **kwargs):
        self.calls.append(("run_skill", kwargs))
        return {"ok": True}


class _FakeSandbox:
    async def get_execution_history(self, **kwargs):
        return {
            "items": [],
            "limit": kwargs["limit"],
        }


def _make_run_context(
    role: str = "member",
    computer_runtime: object | None = None,
    *,
    tool_call_timeout: int = 120,
) -> ContextWrapper:
    config_holder = SimpleNamespace(
        get_config=lambda umo: {  # noqa: ARG005
            "provider_settings": {}
        },
        computer_runtime=computer_runtime,
    )
    event = SimpleNamespace(
        role=role,
        unified_msg_origin="qq_official:friend:user-1",
        get_sender_id=lambda: "user-1",
    )
    attach_authorized_tool_context(
        event,
        config_holder,
        "tool.browser_control",
        "extension.manage",
    )
    astr_ctx = SimpleNamespace(context=config_holder, event=event)
    return ContextWrapper(context=astr_ctx, tool_call_timeout=tool_call_timeout)


@pytest.mark.asyncio
async def test_browser_tool_direct_component_call_is_not_gated_by_legacy_config(
    monkeypatch,
):
    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(browser=_FakeBrowser())

    result = await BrowserExecTool().call(
        _make_run_context(
            computer_runtime=SimpleNamespace(get_booter=_fake_get_booter),
        ),
        cmd="open https://example.com",
    )

    assert json.loads(result)["ok"] is True


@pytest.mark.asyncio
async def test_browser_tools_forward_declared_timeout():
    browser = _RecordingBrowser()

    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(browser=browser)

    context = _make_run_context(
        computer_runtime=SimpleNamespace(get_booter=_fake_get_booter),
    )

    await BrowserExecTool().call(context, cmd="open https://example.com", timeout=7)
    await BrowserBatchExecTool().call(
        context,
        commands=["open https://example.com"],
        timeout=8,
    )
    await RunBrowserSkillTool().call(context, skill_key="demo", timeout=9)

    assert [name for name, _ in browser.calls] == ["exec", "exec_batch", "run_skill"]
    assert [kwargs["timeout_seconds"] for _, kwargs in browser.calls] == [7, 8, 9]


@pytest.mark.asyncio
async def test_browser_tools_cap_declared_timeout_at_tool_call_deadline():
    browser = _RecordingBrowser()

    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(browser=browser)

    context = _make_run_context(
        computer_runtime=SimpleNamespace(get_booter=_fake_get_booter),
        tool_call_timeout=10,
    )

    await BrowserExecTool().call(context, cmd="open https://example.com", timeout=30)
    await BrowserBatchExecTool().call(
        context,
        commands=["open https://example.com"],
        timeout=60,
    )
    await RunBrowserSkillTool().call(context, skill_key="demo", timeout=60)

    assert [kwargs["timeout_seconds"] for _, kwargs in browser.calls] == [10, 10, 10]


@pytest.mark.asyncio
async def test_neo_skill_tool_direct_component_call_is_not_gated_by_legacy_config(
    monkeypatch,
):
    async def _fake_get_booter(_ctx, _session_id):
        return SimpleNamespace(
            bay_client=object(),
            sandbox=_FakeSandbox(),
        )

    result = await GetExecutionHistoryTool().call(
        _make_run_context(
            computer_runtime=SimpleNamespace(get_booter=_fake_get_booter),
        ),
        limit=5,
    )

    payload = json.loads(result)
    assert payload["items"] == []
    assert payload["limit"] == 5


@pytest.mark.asyncio
async def test_browser_tool_without_runtime_context_is_not_gated_by_legacy_config():
    result = await BrowserExecTool().call(
        _make_run_context(),
        cmd="open https://example.com",
    )

    assert "Error executing browser command" in result


@pytest.mark.asyncio
async def test_local_permission_error_names_capabilities_tab(monkeypatch):
    policy = SimpleNamespace(
        allow_execution=False,
        execution_disabled_reason=None,
        filesystem_scope="workspace",
    )
    monkeypatch.setattr(computer_util, "is_local_runtime", lambda _context: True)
    monkeypatch.setattr(
        computer_util, "_local_permission_role", lambda _context: "member"
    )
    monkeypatch.setattr(
        computer_util,
        "get_local_permission_policy",
        lambda _context, **_kwargs: policy,
    )

    async def allow_operation(_context, _operation_name):
        return None

    monkeypatch.setattr(computer_util, "check_admin_permission", allow_operation)

    resolved, error = await computer_util.check_local_execution_permission(
        object(),
        "Shell execution",
    )

    assert resolved is policy
    assert error is not None
    assert "WebUI -> Config -> AI -> Capabilities" in error
    assert "Local Permission Policies" in error
