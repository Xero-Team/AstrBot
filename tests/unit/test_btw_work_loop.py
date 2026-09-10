import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.btw.types import WorkSessionStatus, is_work_loop_enabled
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager


class FakeEvent:
    def __init__(self, message: str) -> None:
        self.unified_msg_origin = "umo-1"
        self.message_str = message
        self.extras = {}
        self.result = None

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def set_result(self, value) -> None:
        self.result = value


class FailingExecutor:
    async def process(self, event):
        del event
        raise RuntimeError("provider token leaked")
        yield


class BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process(self, event):
        del event
        self.started.set()
        await self.release.wait()
        yield "done"


@pytest.mark.asyncio
async def test_work_loop_marks_failures_without_exposing_executor_error():
    sessions = WorkSessionManager()
    work_loop = WorkLoop(FailingExecutor(), sessions)
    event = FakeEvent("执行命令")

    with pytest.raises(RuntimeError, match="provider token leaked"):
        _ = [item async for item in work_loop.process(event)]

    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED
    assert "provider token leaked" not in (session.error or "")


@pytest.mark.asyncio
async def test_work_session_manager_expires_terminal_sessions():
    sessions = WorkSessionManager(max_age_seconds=60)
    session = await sessions.create("umo-1", "执行命令")
    await sessions.update_status(session.id, WorkSessionStatus.COMPLETED)
    session.updated_at = datetime.now(UTC) - timedelta(seconds=61)

    assert await sessions.get_by_id(session.id) is None
    assert await sessions.get_for_origin(session.origin) is None


@pytest.mark.asyncio
async def test_work_loop_acknowledges_then_runs_in_background():
    executor = BlockingExecutor()
    sessions = WorkSessionManager()
    work_loop = WorkLoop(executor, sessions)
    background_tasks: set[asyncio.Task] = set()
    result_dispatcher = AsyncMock()
    event_finalizer = AsyncMock()
    work_loop.configure_detached_execution(
        background_tasks=background_tasks,
        result_dispatcher=result_dispatcher,
        event_finalizer=event_finalizer,
    )
    event = FakeEvent("执行命令")

    output = [item async for item in work_loop.submit(event)]

    assert output == [None]
    assert event.result.get_plain_text() == "🔧 工作任务已开始处理。"
    assert len(background_tasks) == 1
    [task] = background_tasks
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.RUNNING

    executor.release.set()
    await asyncio.wait_for(task, timeout=5)

    assert session.status is WorkSessionStatus.COMPLETED
    result_dispatcher.assert_awaited_once_with(event)
    event_finalizer.assert_awaited_once_with(event)


@pytest.mark.parametrize(
    "config, enabled",
    [
        ({"btw": {"enabled": True, "work_loop": {"enabled": True}}}, True),
        ({"btw": {"enabled": False, "work_loop": {"enabled": True}}}, False),
        ({"btw": {"enabled": True, "work_loop": None}}, False),
        ({"btw": None}, False),
        (None, False),
    ],
)
def test_work_admission_requires_both_valid_switches(config, enabled):
    assert is_work_loop_enabled(config) is enabled


@pytest.mark.asyncio
async def test_cancelled_work_retains_cancelled_state_and_propagates():
    executor = BlockingExecutor()
    sessions = WorkSessionManager()
    loop = WorkLoop(executor, sessions)
    event = FakeEvent("cancel this work")

    async def run():
        return [item async for item in loop.process(event)]

    task = asyncio.create_task(run())
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session.status is WorkSessionStatus.CANCELLED


@pytest.mark.asyncio
async def test_retention_does_not_expire_active_work():
    sessions = WorkSessionManager(max_age_seconds=1)
    session = await sessions.create("origin", "still running")
    session.updated_at = datetime.now(UTC) - timedelta(seconds=120)
    assert await sessions.get_by_id(session.id) is session
