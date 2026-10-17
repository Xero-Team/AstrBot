from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.work import WorkCommands
from astrbot.core.agent.btw import runtime_registry
from astrbot.core.agent.btw.types import WorkSessionStatus
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.pipeline.process_stage import stage as process_stage
from tests.unit.builtin_command_fakes import FakeI18n
from tests.unit.test_builtin_command_extensions import DummyEvent


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(runtime_registry, "_managers", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en-US", "zh-CN"])
@pytest.mark.parametrize("status", list(WorkSessionStatus))
async def test_work_status_localizes_every_terminal_and_active_state(locale, status):
    manager = WorkSessionManager()
    event = DummyEvent(message_str="work status")
    event.resource = SimpleNamespace(config_id="profile-a")
    event.set_extra("locale", locale)
    session = await manager.create(event.unified_msg_origin, "inspect the workspace")
    await manager.update_status(session.id, status)
    runtime_registry.register("profile-a", manager)
    context = SimpleNamespace(i18n=FakeI18n())

    await WorkCommands(context).handle(event, "STATUS")

    expected = await context.i18n.t(
        event, f"work.status.{status}", task="inspect the workspace"
    )
    assert event.result.get_plain_text() == expected
    assert "inspect the workspace" in expected
    assert "work.status." not in expected
    assert event.is_stopped()
    assert event.get_extra("btw_force_work") is None


@pytest.mark.asyncio
async def test_latest_status_stays_with_its_profile_origin_and_latest_task():
    first = WorkSessionManager(max_age_seconds=60)
    second = WorkSessionManager()
    runtime_registry.register("profile-a", first)
    runtime_registry.register("profile-b", second)
    older = await first.create("same-origin", "first task")
    await first.update_status(older.id, WorkSessionStatus.RUNNING)
    latest = await first.create("same-origin", "newest task")
    await second.create("same-origin", "other profile")

    assert await runtime_registry.latest_status("profile-a", "same-origin") == (
        "newest task",
        WorkSessionStatus.PENDING,
    )
    assert await runtime_registry.latest_status("profile-b", "same-origin") == (
        "other profile",
        WorkSessionStatus.PENDING,
    )
    assert await runtime_registry.latest_status("profile-a", "other-origin") is None
    assert (
        await runtime_registry.latest_status("unknown-profile", "same-origin") is None
    )
    await first.update_status(latest.id, WorkSessionStatus.COMPLETED)
    latest.updated_at = datetime.now(UTC) - timedelta(seconds=61)
    assert await runtime_registry.latest_status("profile-a", "same-origin") is None
    assert await first.get_by_id(older.id) is older


@pytest.mark.asyncio
async def test_status_command_uses_resource_config_without_profile_fallback():
    manager = WorkSessionManager()
    event = DummyEvent(message_str="work")
    event.resource = SimpleNamespace(config_id="profile-b")
    await manager.create(event.unified_msg_origin, "profile-a task")
    runtime_registry.register("profile-a", manager)

    await WorkCommands(SimpleNamespace(i18n=FakeI18n())).handle(event)

    assert event.result.get_plain_text() == "No BTW work task has run in this session."


@pytest.mark.asyncio
async def test_process_registration_replacement_and_close_are_identity_scoped(
    monkeypatch,
):
    monkeypatch.setattr(process_stage.AgentRequestSubStage, "initialize", AsyncMock())
    monkeypatch.setattr(process_stage.StarRequestSubStage, "initialize", AsyncMock())
    context = SimpleNamespace(
        astrbot_config_id="profile-a",
        astrbot_config={"btw": {"enabled": True, "work_loop": {"enabled": True}}},
    )
    old = process_stage.ProcessStage()
    current = process_stage.ProcessStage()
    await old.initialize(context)
    await old.conversation_loop.work_sessions.create("origin", "old task")
    assert (await runtime_registry.latest_status("profile-a", "origin"))[
        0
    ] == "old task"

    await current.initialize(context)
    await current.conversation_loop.work_sessions.create("origin", "new task")
    await old.close()
    assert (await runtime_registry.latest_status("profile-a", "origin"))[
        0
    ] == "new task"
    await current.close()
    await current.close()
    assert await runtime_registry.latest_status("profile-a", "origin") is None


@pytest.mark.asyncio
async def test_failed_stage_initialization_does_not_publish_a_manager(monkeypatch):
    monkeypatch.setattr(process_stage.AgentRequestSubStage, "initialize", AsyncMock())
    monkeypatch.setattr(
        process_stage.StarRequestSubStage,
        "initialize",
        AsyncMock(side_effect=RuntimeError("initialization failed")),
    )
    stage = process_stage.ProcessStage()
    with pytest.raises(RuntimeError, match="initialization failed"):
        await stage.initialize(
            SimpleNamespace(
                astrbot_config_id="profile-a", astrbot_config={"btw": {"enabled": True}}
            )
        )
    assert runtime_registry._managers == {}
    await stage.close()


@pytest.mark.asyncio
async def test_failing_close_still_removes_its_registration(monkeypatch):
    monkeypatch.setattr(process_stage.AgentRequestSubStage, "initialize", AsyncMock())
    monkeypatch.setattr(process_stage.StarRequestSubStage, "initialize", AsyncMock())
    stage = process_stage.ProcessStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config_id="profile-a", astrbot_config={"btw": {"enabled": True}}
        )
    )
    monkeypatch.setattr(
        stage.conversation_loop,
        "close",
        AsyncMock(side_effect=RuntimeError("close failed")),
    )
    with pytest.raises(RuntimeError, match="close failed"):
        await stage.close()
    assert runtime_registry._managers == {}


@pytest.mark.asyncio
async def test_status_snapshot_and_command_include_live_delegation_progress():
    from astrbot.core.agent.btw.types import WorkDelegation

    manager = WorkSessionManager()
    event = DummyEvent(message_str="work status")
    event.resource = SimpleNamespace(config_id="profile-a")
    session = await manager.create(event.unified_msg_origin, "inspect the workspace")
    await manager.update_status(session.id, WorkSessionStatus.RUNNING)
    delegation = WorkDelegation(
        run_id="run-1",
        agent_id="codex",
        agent_name="Codex",
        agent_type="codex",
        workspace="run-1",
    )
    await manager.start_delegation(session.id, delegation)
    await manager.record_delegation_event(
        session.id,
        "run-1",
        event_type="tool_call",
        summary="shell: pytest -q",
        tool="shell",
        status="running",
    )
    runtime_registry.register("profile-a", manager)
    context = SimpleNamespace(i18n=FakeI18n())

    snapshot = await runtime_registry.latest_status_snapshot(
        "profile-a", event.unified_msg_origin
    )
    assert snapshot is not None
    assert snapshot.delegation is delegation

    await WorkCommands(context).handle(event, "status")
    text = event.result.get_plain_text()
    assert "Coding agent: Codex" in text
    assert "shell: pytest -q" in text
    assert "Tool calls: 1; events: 1" in text


@pytest.mark.asyncio
async def test_delegation_progress_is_terminal_and_artifact_aware():
    from astrbot.core.agent.btw.types import WorkDelegation

    manager = WorkSessionManager()
    session = await manager.create("origin", "task")
    delegation = WorkDelegation(
        run_id="run-1",
        agent_id="opencode",
        agent_name="OpenCode",
        agent_type="opencode",
        workspace="run-1",
    )
    assert await manager.start_delegation(session.id, delegation) is True
    assert (
        await manager.record_delegation_event(
            session.id,
            "run-1",
            event_type="tool_call",
            summary="write: report.md",
            tool="write",
            call_id="call-1",
            status="running",
            usage={"input_tokens": 4},
        )
        is True
    )
    assert (
        await manager.record_delegation_event(
            session.id,
            "run-1",
            event_type="tool_result",
            summary="written",
            tool="write",
            call_id="call-1",
            status="completed",
        )
        is True
    )
    last_event_at = delegation.updated_at
    assert (
        await manager.finish_delegation(
            session.id,
            "run-1",
            status="completed",
            exit_code=0,
            artifacts=["report.md"],
            latest_action="OpenCode finished",
            usage={"output_tokens": 2},
        )
        is True
    )
    assert delegation.status == "completed"
    assert delegation.tool_call_count == 1
    assert delegation.usage == {"input_tokens": 4, "output_tokens": 2}
    assert delegation.artifacts == ["report.md"]
    assert delegation.recent_events[0]["summary"] == "write: report.md"
    assert delegation.recent_events[1]["timestamp"] == last_event_at.isoformat()
    assert (
        await manager.record_delegation_event(
            "missing", "run-1", event_type="message", summary="ignored"
        )
        is False
    )
