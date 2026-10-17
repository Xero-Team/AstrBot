"""Closed-loop tests: work loop -> delegation tool -> CLI stream -> result."""

import json
import sys
from types import SimpleNamespace

import pytest

from astrbot.core.agent.btw import coding_runner, runtime_registry
from astrbot.core.agent.btw.coding_agents import CodingInvocation
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.tools.coding_tools import DelegateCodingTaskTool
from tests.unit.coding_agent_support import (
    CASES,
    FAKE_CLI,
    agent_entry,
)


class LoopEvent:
    def __init__(self, origin: str = "webchat:FriendMessage:user") -> None:
        self.unified_msg_origin = origin
        self.message_str = "write the report"
        self.resource = SimpleNamespace(config_id="cfg")
        self.extras = {}
        self.result = None
        self._stopped = False
        self.trace_calls = []
        self.trace = SimpleNamespace(
            record=lambda action, **fields: self.trace_calls.append((action, fields))
        )

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def is_stopped(self) -> bool:
        return self._stopped

    def set_result(self, result) -> None:
        self.result = result


def _profile(case):
    return {
        "btw": {
            "enabled": True,
            "work_loop": {
                "enabled": True,
                "computer_use_runtime": "local",
                "coding_agents": [agent_entry(case)],
            },
        }
    }


class DelegatingExecutor:
    def __init__(self, profile: dict) -> None:
        self.profile = profile
        self.reply = ""
        self.tool = DelegateCodingTaskTool()

    async def process(self, event):
        context = SimpleNamespace(
            context=SimpleNamespace(
                event=event,
                context=SimpleNamespace(get_config=lambda umo=None: self.profile),
            )
        )
        self.reply = await self.tool.call(context, task=event.message_str)
        event.set_result(self.reply)
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[case.agent_type for case in CASES])
async def test_work_loop_closes_the_delegation_loop(tmp_path, monkeypatch, case):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    sessions = WorkSessionManager()
    runtime_registry.register("cfg", sessions)

    def fake_invocation(agent, *, workspace):
        del agent
        return CodingInvocation(
            argv=(sys.executable, str(FAKE_CLI), str(case.fixture)),
            cwd=workspace,
        )

    monkeypatch.setattr(coding_runner, "build_invocation", fake_invocation)
    executor = DelegatingExecutor(_profile(case))
    work_loop = WorkLoop(executor, sessions)
    event = LoopEvent()

    try:
        _ = [progress async for progress in work_loop.process(event)]
    finally:
        runtime_registry.unregister("cfg", sessions)

    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status.value == "completed"
    assert len(session.delegations) == 1
    delegation = session.delegations[0]
    assert delegation.status == "completed"
    assert delegation.agent_type == case.agent_type
    assert delegation.event_count > 0
    assert delegation.tool_call_count >= 1
    assert delegation.recent_events
    assert session.artifacts == [f"{delegation.workspace}/report.md"]
    assert "status: completed" in executor.reply
    assert case.result_final_text in executor.reply

    workspace = coding_runner.workspace_root(_profile(case)) / delegation.workspace
    summary = json.loads((workspace / "run.json").read_text(encoding="utf-8"))
    assert summary["status"] == "completed"
    assert summary["agent"]["type"] == case.agent_type
    assert [action for action, _ in event.trace_calls][0] == "coding_agent_start"
    assert [action for action, _ in event.trace_calls][-1] == "coding_agent_end"
