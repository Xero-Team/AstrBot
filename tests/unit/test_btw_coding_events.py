"""Contract tests for normalized coding-agent streams and run artifacts."""

import json
import sys
from types import SimpleNamespace

import pytest

from astrbot.core.agent.btw import coding_runner
from astrbot.core.agent.btw.coding_agents import CodingInvocation
from astrbot.core.agent.btw.coding_events import (
    EVENTS_LOG_NAME,
    RUN_SUMMARY_NAME,
    CodingAgentEvent,
    CodingRunObserver,
    adapter_for,
)
from tests.unit.coding_agent_support import CASES, FAKE_CLI, normalized_agent


@pytest.mark.parametrize("case", CASES, ids=[case.agent_type for case in CASES])
def test_each_agent_stream_normalizes_to_the_same_event_model(case):
    adapter = adapter_for(case.agent_type)
    assert adapter is not None
    events = []
    for line in case.fixture.read_text(encoding="utf-8").splitlines():
        events.extend(adapter.feed(line))

    types = {event.type for event in events}
    assert {"lifecycle", "message", "usage"} <= types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "file_change" in types
    assert adapter.final_text == case.stream_final_text
    assert adapter.usage


def test_claude_tool_results_keep_the_call_id_separate_from_the_tool():
    adapter = adapter_for("claude_code")
    assert adapter is not None
    events = []
    for line in CASES[0].fixture.read_text(encoding="utf-8").splitlines():
        events.extend(adapter.feed(line))

    call = next(event for event in events if event.type == "tool_call")
    result = next(event for event in events if event.type == "tool_result")
    assert call.tool == "Write"
    assert call.call_id == "tool-1"
    assert result.tool == ""
    assert result.call_id == "tool-1"


@pytest.mark.asyncio
async def test_completed_only_tool_events_count_as_one_call(tmp_path):
    adapter = adapter_for("codex")
    assert adapter is not None
    observer = CodingRunObserver(
        agent={"id": "codex", "name": "Codex", "type": "codex", "command": "codex"},
        workspace=tmp_path,
        run_id="run-1",
    )
    events = adapter.feed(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "ws-1",
                    "type": "web_search",
                    "status": "completed",
                    "result": {"title": "result"},
                },
            }
        )
    )
    for event in events:
        await observer.record(event)
    observer.finish(
        status=coding_runner.STATUS_COMPLETED,
        exit_code=0,
        artifacts=[],
    )
    observer.close()

    assert observer.tool_calls == 1


@pytest.mark.asyncio
async def test_run_summary_bounds_the_latest_action(tmp_path):
    observer = CodingRunObserver(
        agent={"id": "codex", "name": "Codex", "type": "codex", "command": "codex"},
        workspace=tmp_path,
        run_id="run-1",
    )
    summary = observer.finish(
        status=coding_runner.STATUS_COMPLETED,
        exit_code=0,
        artifacts=[],
        latest_action="x" * 10_000,
    )
    observer.close()

    assert len(summary["latest_action"]) < 300
    assert "characters truncated" in summary["latest_action"]


@pytest.mark.asyncio
async def test_the_observer_writes_redacted_events_and_a_run_summary(tmp_path):
    trace_calls = []
    trace = SimpleNamespace(
        record=lambda action, **fields: trace_calls.append((action, fields))
    )
    observer = CodingRunObserver(
        agent={"id": "codex", "name": "Codex", "type": "codex", "command": "codex"},
        workspace=tmp_path,
        run_id="run-1",
        trace=trace,
    )
    await observer.record(
        CodingAgentEvent(
            type="tool_call",
            summary="fetch https://private.example/api?api_key=sk-abcdefghijklmnop",
            detail='{"api_key":"sk-abcdefghijklmnop","file_path":"/Users/me/private.txt"}',
            tool="fetch",
            status="running",
        )
    )
    summary = observer.finish(
        status=coding_runner.STATUS_COMPLETED,
        exit_code=0,
        artifacts=["report.md"],
    )
    observer.close()

    events_text = (tmp_path / EVENTS_LOG_NAME).read_text(encoding="utf-8")
    summary_text = (tmp_path / RUN_SUMMARY_NAME).read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in events_text
    assert "/Users/me/private.txt" not in events_text
    assert "private.example" not in events_text
    assert "[REDACTED]" in events_text
    assert summary["status"] == "completed"
    assert summary["event_count"] == 1
    assert json.loads(summary_text)["artifacts"] == ["report.md"]
    assert [action for action, _ in trace_calls] == [
        "coding_agent_start",
        "coding_agent_event",
        "coding_agent_end",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[case.agent_type for case in CASES])
async def test_the_runner_parses_live_events_and_collects_the_result(
    tmp_path, monkeypatch, case
):
    workspace = tmp_path / f"workspace-{case.agent_type}"
    workspace.mkdir()
    received = []

    def fake_invocation(agent, *, workspace):
        del agent
        return CodingInvocation(
            argv=(sys.executable, str(FAKE_CLI), str(case.fixture)),
            cwd=workspace,
        )

    monkeypatch.setattr(coding_runner, "build_invocation", fake_invocation)

    async def on_event(event):
        received.append(event)

    result = await coding_runner.run_coding_task(
        normalized_agent(case),
        workspace=workspace,
        task="write the report",
        on_event=on_event,
    )

    assert result.status == coding_runner.STATUS_COMPLETED
    assert result.output == case.result_final_text
    assert result.event_count == len(received)
    assert result.tool_call_count >= 1
    assert "report.md" in result.artifacts
    assert (workspace / "report.md").read_text(encoding="utf-8") == "write the report"
    assert (workspace / EVENTS_LOG_NAME).is_file()
    summary = json.loads((workspace / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["run_id"] == workspace.name
    assert summary["status"] == "completed"
    assert summary["event_count"] == len(received)
    assert summary["workspace"] == workspace.name
    assert str(tmp_path) not in json.dumps(summary)


@pytest.mark.asyncio
async def test_a_failed_run_still_writes_its_summary(tmp_path):
    agent = normalized_agent(
        CASES[0],
        command=sys.executable,
        extra_args=["-c", "raise SystemExit(3)"],
        type="custom",
    )
    result = await coding_runner.run_coding_task(
        agent,
        workspace=tmp_path,
        task="fail",
    )

    assert result.status == coding_runner.STATUS_FAILED
    summary = json.loads((tmp_path / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["exit_code"] == 3


@pytest.mark.asyncio
async def test_a_cancelled_run_still_writes_its_summary(tmp_path):
    import asyncio

    agent = normalized_agent(
        CASES[0],
        command=sys.executable,
        extra_args=["-c", "import time; time.sleep(30)"],
        type="custom",
    )
    task = asyncio.create_task(
        coding_runner.run_coding_task(agent, workspace=tmp_path, task="cancel")
    )
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    summary = json.loads((tmp_path / RUN_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["status"] == "cancelled"


@pytest.mark.asyncio
async def test_a_failing_progress_callback_does_not_break_the_observer(tmp_path):
    async def fail(_event):
        raise RuntimeError("dashboard offline")

    def broken_trace(_action, **_fields):
        raise RuntimeError("trace sink offline")

    observer = CodingRunObserver(
        agent={"id": "codex", "name": "Codex", "type": "codex", "command": "codex"},
        workspace=tmp_path,
        run_id="run-1",
        on_event=fail,
        trace=SimpleNamespace(record=broken_trace),
    )
    await observer.record(
        CodingAgentEvent(type="message", summary="still recorded", detail="text")
    )
    observer.finish(
        status=coding_runner.STATUS_COMPLETED,
        exit_code=0,
        artifacts=[],
    )
    observer.close()

    assert (tmp_path / EVENTS_LOG_NAME).is_file()
    assert (tmp_path / RUN_SUMMARY_NAME).is_file()
