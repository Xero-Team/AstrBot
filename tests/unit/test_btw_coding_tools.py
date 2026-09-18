"""Tests for the work loop's delegation tool."""

import sys
from types import SimpleNamespace

import pytest

from astrbot.core.agent.btw import coding_runner, runtime_registry
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.tools.coding_tools import (
    NO_AGENT_REPLY,
    DelegateCodingTaskTool,
)

UMO = "webchat:FriendMessage:webchat!user!session"
RUNNER_CODE = (
    "import pathlib; pathlib.Path('report.md').write_text('ok', encoding='utf-8')"
)


class FakeEvent:
    def __init__(self, session_id: str = "session-1") -> None:
        self.unified_msg_origin = UMO
        self.message_str = "task"
        self.extras = {"btw_work_session_id": session_id}
        self._stopped = False

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def is_stopped(self) -> bool:
        return self._stopped


def _profile(agents: list, **work_overrides) -> dict:
    work = {"enabled": True, "coding_agents": agents, "computer_use_runtime": "local"}
    work.update(work_overrides)
    return {"btw": {"enabled": True, "work_loop": work}}


def _fake_agent(**overrides) -> dict:
    entry = {
        "id": "fake",
        "type": "custom",
        "enabled": True,
        "command": sys.executable,
        "extra_args": ["-c", RUNNER_CODE],
    }
    entry.update(overrides)
    return entry


def _context(profile: dict, event: FakeEvent):
    runtime = SimpleNamespace(get_config=lambda umo=None: profile)
    return SimpleNamespace(context=SimpleNamespace(event=event, context=runtime))


@pytest.mark.asyncio
async def test_delegation_without_an_agent_answers_with_a_reason():
    tool = DelegateCodingTaskTool()
    reply = await tool.call(_context({"btw": {"enabled": True}}, FakeEvent()), task="x")
    assert reply == NO_AGENT_REPLY


@pytest.mark.asyncio
async def test_delegation_without_a_task_answers_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    tool = DelegateCodingTaskTool()
    reply = await tool.call(
        _context(_profile([_fake_agent()]), FakeEvent()), task="   "
    )
    assert reply.startswith("error: the task was empty")


@pytest.mark.asyncio
async def test_delegation_reports_the_folder_the_artifacts_and_the_run(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    manager = WorkSessionManager()
    session = await manager.create(UMO, "task")
    runtime_registry._managers["cfg"] = manager
    try:
        event = FakeEvent(session.id)
        event.resource = SimpleNamespace(config_id="cfg")
        tool = DelegateCodingTaskTool()
        reply = await tool.call(
            _context(_profile([_fake_agent()]), event), task="write report.md"
        )
    finally:
        runtime_registry._managers.pop("cfg", None)

    assert "status: completed" in reply
    assert "agent: fake (fake)" in reply
    assert "exit_code: 0" in reply
    workspace = (
        coding_runner.workspace_root({"btw": {}})
        / reply.splitlines()[2].split(": ", 1)[1]
    )
    # Named through its folder, so a run that also wrote into a project dir --
    # which is not inside the workspace root -- cannot read as the same place.
    assert f"- {workspace.name}/report.md" in reply
    assert (workspace / coding_runner.OUTPUT_LOG_NAME).is_file()
    assert session.artifacts == [f"{workspace.name}/report.md"]


@pytest.mark.asyncio
async def test_delegation_records_nothing_without_a_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    runtime_registry._managers["cfg"] = WorkSessionManager()
    try:
        event = FakeEvent("missing-session")
        event.resource = SimpleNamespace(config_id="cfg")
        tool = DelegateCodingTaskTool()
        reply = await tool.call(
            _context(_profile([_fake_agent()]), event), task="write report.md"
        )
    finally:
        runtime_registry._managers.pop("cfg", None)
    assert "status: completed" in reply


@pytest.mark.asyncio
async def test_a_runner_that_raises_becomes_a_reported_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))

    async def _explode(*args, **kwargs):
        raise RuntimeError("provider token leaked")

    monkeypatch.setattr(coding_runner, "run_coding_task", _explode)
    tool = DelegateCodingTaskTool()
    reply = await tool.call(
        _context(_profile([_fake_agent()]), FakeEvent()), task="write report.md"
    )
    assert reply.startswith("error: the coding agent could not be run")


@pytest.mark.asyncio
async def test_a_named_agent_is_used_when_it_is_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    profile = _profile(
        [
            _fake_agent(id="first", command="does-not-exist"),
            _fake_agent(id="second"),
        ]
    )
    tool = DelegateCodingTaskTool()
    reply = await tool.call(_context(profile, FakeEvent()), task="t", agent_id="second")
    assert "agent: second (second)" in reply
    assert "status: completed" in reply


@pytest.mark.asyncio
async def test_an_unknown_agent_id_is_not_substituted(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    tool = DelegateCodingTaskTool()
    reply = await tool.call(
        _context(_profile([_fake_agent()]), FakeEvent()), task="t", agent_id="nope"
    )
    assert reply == NO_AGENT_REPLY


@pytest.mark.asyncio
async def test_an_empty_artifact_list_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    agent = _fake_agent(extra_args=["-c", "pass"])
    tool = DelegateCodingTaskTool()
    reply = await tool.call(_context(_profile([agent]), FakeEvent()), task="t")
    assert "artifacts: none reported" in reply
    assert "exit_code: 0" in reply
    folder = reply.splitlines()[2].split(": ", 1)[1]
    root = coding_runner.workspace_root({"btw": {}})
    assert (root / folder).is_dir()
