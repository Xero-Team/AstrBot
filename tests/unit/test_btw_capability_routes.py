"""BTW assignments apply across catalog assembly and nested handoffs."""

import json
from types import SimpleNamespace

import pytest

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.astr_main_agent import (
    MainAgentBuildConfig,
    _assemble_request_tool_catalog,
)
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.skills._skill_snapshot import SkillSnapshot
from astrbot.core.tool_catalog import ToolCatalogInputs, assemble_tool_catalog
from astrbot.core.tools.function_tool_manager import FunctionToolManager


@pytest.fixture
def plugin_context():
    plugin = SimpleNamespace(root_dir_name="example", name="example", reserved=False)
    plugins = SimpleNamespace(
        get_by_module=lambda path: plugin if path == "plugins.example.main" else None
    )
    plugin_tool = FunctionTool(
        name="plugin_tool",
        description="Plugin operation",
        parameters={"type": "object", "properties": {}},
        handler_module_path="plugins.example.main",
        required_actions=("session.read",),
    )
    builtin_tool = FunctionTool(
        name="builtin_tool",
        description="Built-in operation",
        parameters={"type": "object", "properties": {}},
    )
    manager = FunctionToolManager()
    manager.func_list = [plugin_tool, builtin_tool]
    return SimpleNamespace(
        catalogs=SimpleNamespace(plugins=plugins),
        get_llm_tool_manager=lambda: manager,
        subagent_orchestrator=None,
    )


@pytest.mark.parametrize(
    ("enabled", "loop", "routes", "allowed"),
    [
        (True, None, [], False),
        (True, "conversation", [], False),
        (True, "work", [], True),
        (False, "conversation", [], True),
        (True, "conversation", [{"plugin_id": "example", "loop": "both"}], True),
        (True, "work", [{"plugin_id": "example", "loop": "conversation"}], False),
        (True, "conversation", [{"plugin_id": "example", "loop": "invalid"}], False),
        (True, "conversation", {"example": "both"}, False),
        (True, "conversation", [None, {"plugin_id": "example", "loop": []}], False),
    ],
)
@pytest.mark.parametrize("handoff_selection", [None, ["plugin_tool", "builtin_tool"]])
def test_plugin_assignments_match_main_and_handoff(
    plugin_context, enabled, loop, routes, allowed, handoff_selection
):
    cfg = {"btw": {"enabled": enabled, "plugin_routes": routes}}
    plugin_context.get_config = lambda **_kwargs: cfg
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:test",
        get_extra=lambda key, default=None: loop if key == "btw_loop" else default,
        plugins_name=None,
        platform_meta=SimpleNamespace(support_proactive_message=False),
        get_message_type=lambda: None,
    )
    req = ProviderRequest(prompt="hello")
    _assemble_request_tool_catalog(
        event,
        req,
        plugin_context,
        MainAgentBuildConfig(tool_call_timeout=60, add_cron_tools=False),
    )
    run_context = ContextWrapper(
        context=SimpleNamespace(event=event, context=plugin_context)
    )
    handoff = FunctionToolExecutor._build_handoff_toolset(
        run_context, tools=handoff_selection
    )
    expected = {"builtin_tool", "plugin_tool"} if allowed else {"builtin_tool"}
    assert req.func_tool is not None
    assert set(req.func_tool.names()) == expected
    assert handoff is not None
    assert set(handoff.names()) == expected


def test_plugin_assignment_does_not_restore_persona_filtered_tool(plugin_context):
    tools = plugin_context.get_llm_tool_manager().func_list
    catalog = assemble_tool_catalog(
        ToolCatalogInputs(
            snapshot=SkillSnapshot(skills=(), runtime="none"),
            persona_tools=[],
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools={tool.name: tool for tool in tools},
            session_tool_names=frozenset(tool.name for tool in tools),
            plugins=plugin_context.catalogs.plugins,
            btw_config={
                "enabled": True,
                "plugin_routes": [{"plugin_id": "example", "loop": "both"}],
            },
        )
    )
    assert catalog.empty()


def test_plugin_routes_survive_profile_save(tmp_path):
    path = tmp_path / "profile.json"
    routes = [{"plugin_id": "example", "loop": "both"}]
    path.write_text(json.dumps({"btw": {"plugin_routes": routes}}), encoding="utf-8")
    config = AstrBotConfig(
        config_path=str(path), default_config={"btw": {"plugin_routes": []}}
    )
    config.save_config()
    assert (
        json.loads(path.read_text(encoding="utf-8-sig"))["btw"]["plugin_routes"]
        == routes
    )
