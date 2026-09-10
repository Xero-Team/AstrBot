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
