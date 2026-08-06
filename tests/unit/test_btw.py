import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.btw import (
    TaskClassifier,
    TaskType,
    WorkLoop,
    WorkSessionManager,
    WorkSessionStatus,
)


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
async def test_task_classifier_selects_work_for_keywords_and_conversation_otherwise():
    classifier = TaskClassifier(
        {"btw": {"enabled": True, "work_loop": {"enabled": True}}}
    )

    assert await classifier.classify(SimpleNamespace(message_str="你好")) is TaskType.CONVERSATION
    assert await classifier.classify(SimpleNamespace(message_str="帮我修改代码")) is TaskType.WORK
    assert (
        await classifier.classify(SimpleNamespace(message_str="让 Claude Code 处理这个仓库"))
        is TaskType.WORK
    )
    assert (
        await classifier.classify(SimpleNamespace(message_str="continue with Codex"))
        is TaskType.WORK
    )


@pytest.mark.asyncio
async def test_task_classifier_respects_disabled_work_loop():
    classifier = TaskClassifier(
        {"btw": {"enabled": True, "work_loop": {"enabled": False}}}
    )

    assert await classifier.classify(SimpleNamespace(message_str="帮我修改代码")) is TaskType.CONVERSATION


@pytest.mark.asyncio
async def test_task_classifier_accepts_manual_work_command_when_auto_classification_is_disabled():
    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": False},
                "work_loop": {"enabled": True},
            }
        }
    )

    assert await classifier.classify(SimpleNamespace(message_str="/work 重构项目")) is TaskType.WORK


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
    await task

    assert session.status is WorkSessionStatus.COMPLETED
    result_dispatcher.assert_awaited_once_with(event)
    event_finalizer.assert_awaited_once_with(event)
