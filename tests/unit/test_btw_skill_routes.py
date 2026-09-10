"""Skill loop assignments constrain the frozen request capabilities."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import astrbot.core.astr_main_agent as main_agent
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.skills._skill_inventory import SkillInfo
from astrbot.core.skills._skill_read import (
    SkillReadError,
    lookup_frozen_skill,
    read_host_skill_file,
)
from astrbot.core.skills._skill_snapshot import SKILL_SNAPSHOT_EXTRA_KEY
from astrbot.core.tool_catalog import ToolCatalogInputs, assemble_tool_catalog
from astrbot.core.tools.computer_tools import ExecuteShellTool
from astrbot.core.tools.skill_tools import ReadSkillTool


def _skill(root: Path, name: str, *, workspace: bool = False) -> SkillInfo:
    directory = root / ("workspace" if workspace else "ordinary") / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {name} manual\n"
        f"tools:\n  - {name}_query\n  - astrbot_execute_shell\n---\n# {name}\n",
        encoding="utf-8",
    )
    return SkillInfo(
        name=name,
        description=f"{name} manual",
        path=str(path),
        host_path=str(path),
        active=True,
        source_type="workspace" if workspace else "local_only",
        declared_tools=(f"{name}_query", "astrbot_execute_shell"),
    )


@pytest.fixture
def skill_context(tmp_path, monkeypatch):
    ordinary = [_skill(tmp_path, name) for name in ("shared", "restricted")]
    workspace = [_skill(tmp_path, "workspace-guide", workspace=True)]
    manager = SimpleNamespace(
        list_skills=MagicMock(return_value=ordinary),
        list_workspace_skills=MagicMock(return_value=workspace),
    )
    profile = {"btw": {"enabled": True, "skill_routes": []}}
    context = SimpleNamespace(
        skill_manager=manager,
        catalogs=SimpleNamespace(plugins=SimpleNamespace(all=lambda: [])),
        get_config=lambda **_kwargs: profile,
    )
    extras = {}
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:test",
        get_extra=lambda key, default=None: extras.get(key, default),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )
    monkeypatch.setattr(
        main_agent, "get_astrbot_workspaces_path", lambda: str(tmp_path)
    )
    return context, event, profile, extras


@pytest.mark.parametrize(
    ("enabled", "loop", "routes", "names"),
    [
        (True, None, [], {"shared", "restricted"}),
        (True, "work", [], {"shared", "restricted"}),
        (
            True,
            "conversation",
            [{"skill_name": "restricted", "loop": "work"}],
            {"shared"},
        ),
        (
            True,
            "work",
            [{"skill_name": "restricted", "loop": "conversation"}],
            {"shared"},
        ),
        (
            False,
            "conversation",
            [{"skill_name": "restricted", "loop": "work"}],
            {"shared", "restricted"},
        ),
        (
            True,
            "conversation",
            [{"skill_name": "restricted", "loop": "invalid"}],
            {"shared", "restricted"},
        ),
        (True, "conversation", {"restricted": "work"}, {"shared", "restricted"}),
    ],
)
def test_skill_prompt_reader_and_tool_catalog_share_filtered_snapshot(
    skill_context, enabled, loop, routes, names
):
    context, event, profile, extras = skill_context
    profile["btw"] = {"enabled": enabled, "skill_routes": routes}
    extras["btw_loop"] = loop
    req = ProviderRequest(prompt="help")
    snapshot = main_agent._append_skills_prompt(
        req, {"computer_use_runtime": "none"}, None, event, context
    )
    assert snapshot is extras[SKILL_SNAPSHOT_EXTRA_KEY]
    assert {skill.name for skill in snapshot.skills} == names
    for name in ("shared", "restricted"):
        assert (f"**{name}**" in req.system_prompt) == (name in names)
        if name in names:
            assert f"# {name}" in read_host_skill_file(
                lookup_frozen_skill(snapshot, name), "SKILL.md"
            )
        else:
            with pytest.raises(SkillReadError):
                lookup_frozen_skill(snapshot, name)
    tools = [ReadSkillTool(), ExecuteShellTool()] + [
        FunctionTool(
            name=f"{name}_query",
            description=name,
            parameters={"type": "object", "properties": {}},
            required_actions=("session.read",),
        )
        for name in ("shared", "restricted")
    ]
    catalog = assemble_tool_catalog(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools={tool.name: tool for tool in tools},
            btw_config=profile["btw"],
            loop_mode=loop,
        )
    )
    assert set(catalog.names()) == {"read_skill"} | {f"{name}_query" for name in names}
    context.skill_manager.list_workspace_skills.assert_not_called()


@pytest.mark.parametrize(
    ("enabled", "loop", "runtime", "persona", "workspace_visible"),
    [
        (True, "conversation", "local", None, False),
        (True, None, "local", None, False),
        (True, "work", "local", None, True),
        (True, "work", "sandbox", None, False),
        (True, "work", "none", None, False),
        (False, "conversation", "local", None, True),
        (True, "work", "local", {"skills": []}, False),
    ],
)
def test_workspace_skill_requires_local_work_and_respects_persona(
    skill_context, enabled, loop, runtime, persona, workspace_visible
):
    context, event, profile, extras = skill_context
    profile["btw"]["enabled"] = enabled
    extras["btw_loop"] = loop
    snapshot = main_agent._append_skills_prompt(
        ProviderRequest(prompt="help"),
        {"computer_use_runtime": runtime},
        persona,
        event,
        context,
    )
    assert (snapshot.get("workspace-guide") is not None) == workspace_visible
    if persona == {"skills": []}:
        assert snapshot.skills == ()


def test_skill_routes_survive_profile_save(tmp_path):
    path = tmp_path / "profile.json"
    routes = [{"skill_name": "restricted", "loop": "work"}]
    path.write_text(json.dumps({"btw": {"skill_routes": routes}}), encoding="utf-8")
    config = AstrBotConfig(
        config_path=str(path), default_config={"btw": {"skill_routes": []}}
    )
    config.save_config()
    assert (
        json.loads(path.read_text(encoding="utf-8-sig"))["btw"]["skill_routes"]
        == routes
    )
