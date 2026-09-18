"""Tests for the read-only work loop and its loop-scoped tools."""

from types import SimpleNamespace

import pytest
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.btw.runtime_policy import work_loop_is_read_only
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_main_agent import (
    WORK_LOOP_DELEGATION_PROMPT,
    WORK_LOOP_READ_ONLY_PROMPT,
    _apply_btw_work_loop_prompt,
)
from astrbot.core.auth.models import WEBCHAT_INSTANCE_TOOL_ACTIONS
from astrbot.core.skills._skill_snapshot import SkillSnapshot
from astrbot.core.tool_catalog import (
    ToolCatalogInputs,
    assemble_tool_catalog_names,
    tool_blocked_in_loop,
)

LOOP_TOOLS = {
    "astrbot_execute_shell": ("tool.local_exec",),
    "astrbot_execute_python": ("tool.python_exec",),
    "astrbot_file_write_tool": ("tool.file_write",),
    "astrbot_file_read_tool": ("tool.file_read",),
    "astrbot_grep_tool": ("tool.file_read",),
    "web_search_tavily": ("tool.web_search",),
    "submit_work_task": ("agent.manage",),
    "delegate_coding_task": ("tool.local_exec", "tool.file_write"),
    "mcp_read_tool": ("tool.mcp_read",),
    "mcp_write_tool": ("tool.mcp_write",),
}


@dataclass
class FakeTool(FunctionTool):
    name: str = "tool"
    description: str = "A test tool."
    parameters: dict = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    required_actions: tuple[str, ...] = ()


def _registered_tools() -> dict[str, FunctionTool]:
    return {
        name: FakeTool(name=name, required_actions=actions)
        for name, actions in LOOP_TOOLS.items()
    }


def _inputs(*, loop_mode: str, read_only: bool = False) -> ToolCatalogInputs:
    tools = _registered_tools()
    return ToolCatalogInputs(
        snapshot=SkillSnapshot(skills=(), runtime="none"),
        persona_tools=None,
        surface="im",
        computer_use_runtime="local",
        plugin_names=None,
        registered_tools=tools,
        session_tool_names=frozenset(tools),
        # An admitted operator: the request already carries the elevation these
        # actions need, so the loop's own policy is what the test measures.
        elevated_instance_tool_actions=WEBCHAT_INSTANCE_TOOL_ACTIONS,
        btw_config={"enabled": True},
        loop_mode=loop_mode,
        work_loop_read_only=read_only,
    )


def _names(*, loop_mode: str, read_only: bool = False) -> set[str]:
    return set(
        assemble_tool_catalog_names(_inputs(loop_mode=loop_mode, read_only=read_only))
    )


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ({"btw": {"enabled": True, "work_loop": {"enabled": True}}}, True),
        (
            {
                "btw": {
                    "enabled": True,
                    "work_loop": {"enabled": True, "read_only": False},
                }
            },
            False,
        ),
        ({"btw": {"enabled": False, "work_loop": {"enabled": True}}}, False),
    ],
)
def test_read_only_follows_the_profile(profile, expected):
    assert work_loop_is_read_only(profile, "work") is expected


def test_read_only_applies_to_the_work_loop_only():
    profile = {"btw": {"enabled": True, "work_loop": {"enabled": True}}}
    assert work_loop_is_read_only(profile, "conversation") is False
    assert work_loop_is_read_only(profile, None) is False


def test_read_only_defaults_on_without_the_field():
    profile = {"btw": {"enabled": True, "work_loop": {"enabled": True}}}
    assert work_loop_is_read_only(profile, "work") is True


def test_work_loop_keeps_reads_and_drops_every_write():
    names = _names(loop_mode="work", read_only=True)
    assert "astrbot_file_read_tool" in names
    assert "astrbot_grep_tool" in names
    assert "web_search_tavily" in names
    for dropped in (
        "astrbot_execute_shell",
        "astrbot_execute_python",
        "astrbot_file_write_tool",
        "mcp_write_tool",
        "submit_work_task",
    ):
        assert dropped not in names, dropped


def test_work_loop_keeps_mcp_reads():
    assert "mcp_read_tool" in _names(loop_mode="work", read_only=True)


def test_work_loop_without_read_only_keeps_writes():
    names = _names(loop_mode="work", read_only=False)
    assert "astrbot_execute_shell" in names
    assert "astrbot_file_write_tool" in names


def test_conversation_loop_is_unaffected_by_the_read_only_rule():
    names = _names(loop_mode="conversation", read_only=False)
    assert "astrbot_execute_shell" in names
    assert "delegate_coding_task" not in names


def test_conversation_loop_does_not_delegate_or_run_work():
    names = _names(loop_mode="conversation", read_only=True)
    assert "submit_work_task" in names
    assert "delegate_coding_task" not in names
    assert names >= {"astrbot_execute_shell", "astrbot_file_write_tool"}


@pytest.mark.parametrize(
    ("name", "actions", "loop_mode", "read_only", "blocked"),
    [
        ("astrbot_execute_shell", ("tool.local_exec",), "work", True, True),
        ("astrbot_file_read_tool", ("tool.file_read",), "work", True, False),
        (
            "delegate_coding_task",
            ("tool.local_exec", "tool.file_write"),
            "work",
            True,
            False,
        ),
        ("submit_work_task", ("agent.manage",), "work", True, True),
        ("submit_work_task", ("agent.manage",), "conversation", False, False),
        (
            "delegate_coding_task",
            ("tool.local_exec", "tool.file_write"),
            "conversation",
            False,
            True,
        ),
        # A tool that declares no actions is not read-only by default: a plugin
        # tool that never stated what it needs cannot be assumed to need
        # nothing, and guessing the other way is what the boundary exists for.
        ("unknown_tool", (), "work", True, True),
        ("unknown_tool", (), "work", False, False),
        ("mcp_write_tool", ("tool.mcp_write",), "conversation", True, False),
    ],
)
def test_loop_policy_decides_each_tool(name, actions, loop_mode, read_only, blocked):
    assert (
        tool_blocked_in_loop(
            name,
            actions,
            loop_mode=loop_mode,
            work_loop_read_only=read_only,
        )
        is blocked
    )


def _work_prompt(profile, *, loop="work", runtime="local", allow_computer_tools=True):
    """Return the system prompt the work loop's model would receive."""
    req = SimpleNamespace(system_prompt="base")
    event = SimpleNamespace(
        unified_msg_origin="umo-1",
        get_extra=lambda key, default=None: loop if key == "btw_loop" else default,
    )
    plugin_context = SimpleNamespace(get_config=lambda umo=None: profile)
    config = SimpleNamespace(
        computer_use_runtime=runtime, allow_computer_tools=allow_computer_tools
    )
    _apply_btw_work_loop_prompt(req, event, plugin_context, config)
    return req.system_prompt


def _profile_with_agent(read_only=True, runtime="local"):
    return {
        "btw": {
            "enabled": True,
            "work_loop": {
                "enabled": True,
                "read_only": read_only,
                "computer_use_runtime": runtime,
                "coding_agents": [
                    {"id": "claude_code", "type": "claude_code", "enabled": True}
                ],
            },
        }
    }


def test_the_conversation_loop_gets_no_work_loop_prompt():
    assert _work_prompt(_profile_with_agent(), loop="conversation") == "base"


def test_a_read_only_work_loop_is_told_what_it_lost():
    prompt = _work_prompt(_profile_with_agent())
    assert WORK_LOOP_READ_ONLY_PROMPT in prompt
    assert WORK_LOOP_DELEGATION_PROMPT in prompt


def test_delegation_is_described_only_when_it_is_reachable():
    profile = _profile_with_agent()
    assert WORK_LOOP_DELEGATION_PROMPT in _work_prompt(profile)
    assert WORK_LOOP_DELEGATION_PROMPT not in _work_prompt(profile, runtime="none")
    assert WORK_LOOP_DELEGATION_PROMPT not in _work_prompt(
        profile, allow_computer_tools=False
    )
    # A work loop whose own runtime is not local never delegates, whatever the
    # request resolved to: the run would be started on this host anyway.
    assert WORK_LOOP_DELEGATION_PROMPT not in _work_prompt(
        _profile_with_agent(runtime="sandbox")
    )


def test_a_work_loop_without_an_agent_is_not_told_to_delegate():
    profile = _profile_with_agent()
    profile["btw"]["work_loop"]["coding_agents"] = []
    prompt = _work_prompt(profile)
    assert WORK_LOOP_READ_ONLY_PROMPT in prompt
    assert WORK_LOOP_DELEGATION_PROMPT not in prompt


def test_a_writable_work_loop_is_told_only_about_delegation():
    prompt = _work_prompt(_profile_with_agent(read_only=False))
    assert WORK_LOOP_READ_ONLY_PROMPT not in prompt
    assert WORK_LOOP_DELEGATION_PROMPT in prompt
