from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.auth.models import WEBCHAT_INSTANCE_TOOL_ACTIONS
from astrbot.core.skills._skill_frontmatter import parse_skill_frontmatter
from astrbot.core.skills._skill_inventory import SkillInfo, build_skills_prompt
from astrbot.core.skills._skill_read import (
    GENERIC_SKILL_READ_ERROR,
    SkillReadError,
    lookup_frozen_skill,
    read_host_skill_file,
    resolve_skill_relative_path,
)
from astrbot.core.skills._skill_snapshot import freeze_skill_snapshot
from astrbot.core.tool_catalog import (
    NEO_LIFECYCLE_TOOLS,
    ToolCatalogInputs,
    assemble_tool_catalog_names,
    sandbox_computer_tool_names,
)
from astrbot.core.tools.skill_tools import ReadSkillTool


def _tool(
    name: str,
    *,
    actions: tuple[str, ...] = ("session.read",),
    handler_module_path: str | None = None,
    active: bool = True,
) -> FunctionTool:
    return FunctionTool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
        required_actions=actions,
        handler_module_path=handler_module_path,
        active=active,
    )


def _skill(
    tmp_path: Path,
    name: str,
    *,
    description: str = "desc",
    tools: list[str] | None = None,
    extra_files: dict[str, str] | None = None,
    allowed_tools: str | None = None,
) -> SkillInfo:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    tools_block = ""
    if tools is not None:
        items = "\n".join(f"  - {item}" for item in tools)
        tools_block = f"tools:\n{items}\n"
    allowed_block = f"allowed-tools: {allowed_tools}\n" if allowed_tools else ""
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n{tools_block}{allowed_block}---\n# {name}\n",
        encoding="utf-8",
    )
    for relative, content in (extra_files or {}).items():
        path = skill_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return SkillInfo(
        name=name,
        description=description,
        path=str(skill_md),
        active=True,
        host_path=str(skill_md),
        declared_tools=tuple(tools or ()),
    )


def _registered(**named: FunctionTool) -> dict[str, FunctionTool]:
    return named


def test_build_skills_prompt_lists_name_and_description_without_cat():
    prompt = build_skills_prompt(
        [
            SkillInfo(
                name="notes",
                description="Search notes",
                path="/abs/skills/notes/SKILL.md",
                active=True,
            )
        ]
    )
    assert "**notes**" in prompt
    assert "Search notes" in prompt
    assert "cat" not in prompt
    assert "type" not in prompt.lower().split("mandatory grounding", 1)[-1][:200]
    assert "read_skill" in prompt
    assert "/abs/skills/notes/SKILL.md" not in prompt


@pytest.mark.parametrize(
    "path",
    ["../etc/passwd", "/etc/passwd", "C:/Windows/SKILL.md", "//server/share/SKILL.md"],
)
def test_read_skill_rejects_escape_paths(path: str):
    with pytest.raises(SkillReadError):
        resolve_skill_relative_path(path)


def test_read_skill_rejects_other_skill_and_unknown_name(tmp_path: Path):
    notes = _skill(tmp_path, "notes")
    other = _skill(tmp_path, "other")
    snapshot = freeze_skill_snapshot([notes], runtime="none")
    with pytest.raises(SkillReadError):
        lookup_frozen_skill(snapshot, "other")
    skill = lookup_frozen_skill(snapshot, "notes")
    with pytest.raises(SkillReadError):
        read_host_skill_file(skill, "SKILL.md/../other/SKILL.md")
    _ = other


def test_read_skill_opens_relative_file_and_freezes_body(tmp_path: Path):
    skill = _skill(tmp_path, "notes", extra_files={"refs/a.md": "ref-body"})
    snapshot = freeze_skill_snapshot([skill], runtime="none")
    frozen = lookup_frozen_skill(snapshot, "notes")
    skill_md = Path(frozen.runtime_copy)
    skill_md.write_text("replaced after freeze", encoding="utf-8")
    body = read_host_skill_file(frozen, "SKILL.md")
    assert "replaced after freeze" not in body
    assert "# notes" in body
    referenced = read_host_skill_file(frozen, "refs/a.md")
    assert "ref-body" in referenced


def test_read_skill_rejects_symlink_escape(tmp_path: Path):
    skill = _skill(tmp_path, "notes")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = Path(skill.host_path).parent / "escape.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    snapshot = freeze_skill_snapshot([skill], runtime="none")
    frozen = lookup_frozen_skill(snapshot, "notes")
    with pytest.raises(SkillReadError):
        read_host_skill_file(frozen, "escape.md")


def test_same_name_precedence_and_sandbox_path_validation(tmp_path: Path):
    local = _skill(tmp_path, "dup", description="local")
    workspace = SkillInfo(
        name="dup",
        description="workspace",
        path=str(tmp_path / "workspace" / "dup" / "SKILL.md"),
        active=True,
        source_type="workspace",
        host_path=str(tmp_path / "workspace" / "dup" / "SKILL.md"),
    )
    (tmp_path / "workspace" / "dup").mkdir(parents=True)
    (tmp_path / "workspace" / "dup" / "SKILL.md").write_text(
        "---\ndescription: workspace\n---\n# workspace\n",
        encoding="utf-8",
    )
    snapshot = freeze_skill_snapshot([workspace, local], runtime="local")
    assert snapshot.get("dup") is not None
    assert snapshot.get("dup").source_type == "workspace"
    sandbox = freeze_skill_snapshot(
        [
            SkillInfo(
                name="sb",
                description="sandbox",
                path="/tmp/evil/sb/SKILL.md",
                active=True,
                source_type="sandbox_only",
                sandbox_exists=True,
                local_exists=False,
            )
        ],
        runtime="sandbox",
        sandbox_root="/workspace",
    )
    frozen = sandbox.get("sb")
    assert frozen is not None
    assert frozen.runtime_copy == "/workspace/skills/sb/SKILL.md"


def test_persona_tools_matrix_and_duplicate_skill_tools(tmp_path: Path):
    skill_a = _skill(tmp_path, "a", tools=["search_memory", "astrbot_execute_shell"])
    skill_b = _skill(tmp_path, "b", tools=["search_memory"])
    snapshot = freeze_skill_snapshot([skill_a, skill_b], runtime="none")
    registered = _registered(
        search_memory=_tool("search_memory"),
        plugin_tool=_tool("plugin_tool", handler_module_path="plugin.demo"),
        astrbot_execute_shell=_tool(
            "astrbot_execute_shell", actions=("tool.local_exec",)
        ),
        read_skill=_tool("read_skill", actions=("skill.read",)),
        future_task=_tool("future_task"),
    )
    none_names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools=registered,
            session_tool_names=frozenset({"plugin_tool"}),
            memory_enabled=True,
        )
    )
    assert none_names.count("search_memory") == 1
    assert "plugin_tool" in none_names
    assert "read_skill" in none_names
    assert "astrbot_execute_shell" not in none_names
    empty_names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=[],
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools=registered,
            memory_enabled=True,
        )
    )
    assert empty_names == ("read_skill",)
    listed = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=["plugin_tool"],
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools=registered,
            session_tool_names=frozenset({"plugin_tool"}),
        )
    )
    assert "plugin_tool" in listed
    assert "read_skill" in listed
    assert "search_memory" not in listed


def test_allowed_tools_only_skill_adds_nothing(tmp_path: Path):
    skill = _skill(tmp_path, "legacy", allowed_tools="Bash(gh:*)")
    parsed = parse_skill_frontmatter(Path(skill.host_path).read_text(encoding="utf-8"))
    assert parsed.tools == ()
    assert "ignored_allowed_tools" in parsed.warnings
    snapshot = freeze_skill_snapshot([skill], runtime="none")
    names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools=_registered(
                search_memory=_tool("search_memory"),
                read_skill=_tool("read_skill", actions=("skill.read",)),
            ),
        )
    )
    assert names == ("read_skill",)


def test_runtime_none_keeps_read_skill_without_computer_tools(tmp_path: Path):
    snapshot = freeze_skill_snapshot([_skill(tmp_path, "notes")], runtime="none")
    names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="im",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools=_registered(
                read_skill=_tool("read_skill", actions=("skill.read",)),
                astrbot_execute_shell=_tool(
                    "astrbot_execute_shell", actions=("tool.local_exec",)
                ),
                astrbot_execute_python=_tool(
                    "astrbot_execute_python", actions=("tool.python_exec",)
                ),
                astrbot_file_write_tool=_tool(
                    "astrbot_file_write_tool", actions=("tool.file_write",)
                ),
                astrbot_file_read_tool=_tool(
                    "astrbot_file_read_tool", actions=("tool.file_read",)
                ),
                astrbot_create_skill_payload=_tool(
                    "astrbot_create_skill_payload",
                    actions=("extension.manage",),
                ),
            ),
        )
    )
    assert "read_skill" in names
    assert "astrbot_execute_shell" not in names
    assert "astrbot_execute_python" not in names
    assert "astrbot_file_write_tool" not in names
    assert "astrbot_file_read_tool" not in names
    assert "astrbot_create_skill_payload" not in names
    for neo in NEO_LIFECYCLE_TOOLS:
        assert neo not in names


def test_social_surface_strips_webchat_instance_actions(tmp_path: Path):
    snapshot = freeze_skill_snapshot(
        [_skill(tmp_path, "notes", tools=["astrbot_execute_shell"])],
        runtime="local",
    )
    registered = _registered(
        read_skill=_tool("read_skill", actions=("skill.read",)),
        astrbot_execute_shell=_tool(
            "astrbot_execute_shell", actions=("tool.local_exec",)
        ),
        search_memory=_tool("search_memory"),
    )
    im_names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="im",
            computer_use_runtime="local",
            plugin_names=None,
            registered_tools=registered,
        )
    )
    assert "astrbot_execute_shell" not in im_names
    api_names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="api_key",
            computer_use_runtime="local",
            plugin_names=None,
            registered_tools=registered,
        )
    )
    assert "astrbot_execute_shell" not in api_names
    webchat_names = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=snapshot,
            persona_tools=None,
            surface="webchat_authenticated",
            computer_use_runtime="local",
            plugin_names=None,
            registered_tools=registered,
            webchat_step_up_actions=frozenset({"tool.local_exec"}),
        )
    )
    assert "astrbot_execute_shell" in webchat_names
    for name in im_names:
        actions = set(registered[name].required_actions)
        assert not actions & WEBCHAT_INSTANCE_TOOL_ACTIONS


def test_skills_like_does_not_change_catalog_set(tmp_path: Path):
    snapshot = freeze_skill_snapshot([_skill(tmp_path, "notes")], runtime="none")
    inputs = ToolCatalogInputs(
        snapshot=snapshot,
        persona_tools=None,
        surface="im",
        computer_use_runtime="none",
        plugin_names=None,
        registered_tools=_registered(
            read_skill=_tool("read_skill", actions=("skill.read",)),
            search_memory=_tool("search_memory"),
        ),
        memory_enabled=True,
    )
    assert assemble_tool_catalog_names(inputs) == assemble_tool_catalog_names(inputs)


def test_neo_lifecycle_tools_are_on_demand_computer_layer():
    none_names = sandbox_computer_tool_names(booter="shipyard_neo")
    assert "astrbot_create_skill_payload" in none_names
    runtime_none = assemble_tool_catalog_names(
        ToolCatalogInputs(
            snapshot=freeze_skill_snapshot([], runtime="none"),
            persona_tools=None,
            surface="webchat_authenticated",
            computer_use_runtime="none",
            plugin_names=None,
            registered_tools=_registered(
                **{
                    name: _tool(name, actions=("extension.manage",))
                    for name in NEO_LIFECYCLE_TOOLS
                }
            ),
            webchat_step_up_actions=frozenset({"tool.local_exec"}),
        )
    )
    for name in NEO_LIFECYCLE_TOOLS:
        assert name not in runtime_none


@pytest.mark.asyncio
async def test_read_skill_tool_returns_generic_error_without_host_path(tmp_path: Path):
    skill = _skill(tmp_path, "notes")
    snapshot = freeze_skill_snapshot([skill], runtime="none")
    tool = ReadSkillTool()
    event = MagicMock()
    event.get_extra.return_value = snapshot
    context = SimpleNamespace(
        context=SimpleNamespace(event=event, context=SimpleNamespace())
    )
    result = await tool.call(context, name="missing")
    assert result == GENERIC_SKILL_READ_ERROR
    host_path = str(tmp_path)
    assert host_path not in result
