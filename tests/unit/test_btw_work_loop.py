import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.btw.types import WorkSessionStatus, is_work_loop_enabled
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.astr_agent_run_util import run_agent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.process_stage.method import agent_request
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import third_party
from tests.unit.agent_sub_stage_support import (
    FakeThirdPartyRunner,
    ThirdPartyResponseExecutor,
)
from tests.unit.test_astr_agent_run_util import FakeEvent as RunnerEvent
from tests.unit.test_astr_agent_run_util import FakeRunner


class FakeEvent:
    def __init__(self, message: str) -> None:
        self.unified_msg_origin = "umo-1"
        self.message_str = message
        self.extras = {}
        self.result = None
        self._stopped = False

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def set_result(self, value) -> None:
        self.result = value

    def is_stopped(self) -> bool:
        return self._stopped

    def stop_event(self) -> None:
        self._stopped = True


class FailingExecutor:
    async def process(self, event):
        del event
        raise RuntimeError("provider token leaked")
        yield


class SecretFailingExecutor:
    async def process(self, event):
        del event
        raise RuntimeError("provider failed: api_key=btw-work-loop-secret")
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


class WorkEvent(RunnerEvent):
    """The event surface a real agent run needs inside a work loop."""

    def __init__(self) -> None:
        super().__init__()
        self.unified_msg_origin = "umo-1"
        self.message_str = "执行命令"


class RunAgentExecutor:
    """The real ``run_agent`` used as the work loop's executor.

    Only the model runner behind it is a test double, so the terminal status
    is decided by the same control flow production uses.
    """

    def __init__(self, runner) -> None:
        self.runner = runner

    async def process(self, event):
        del event
        async for _ in run_agent(self.runner):
            yield


class AdmissionSkipExecutor:
    """The real Agent request stage for a run the session turns away."""

    def __init__(self, stage) -> None:
        self.stage = stage

    async def process(self, event):
        async for progress in self.stage.process(event):
            yield progress


class SilentExecutor:
    """An executor that ends without running anything or reporting a result."""

    async def process(self, event):
        del event
        if False:  # noqa: SIM223 -- unreachable yield keeps this a generator
            yield


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


@pytest.mark.asyncio
async def test_detached_work_redacts_executor_failure_from_logs(caplog):
    sessions = WorkSessionManager()
    work_loop = WorkLoop(SecretFailingExecutor(), sessions)
    background_tasks: set[asyncio.Task] = set()
    event_finalizer = AsyncMock()
    work_loop.configure_detached_execution(
        background_tasks=background_tasks,
        result_dispatcher=AsyncMock(),
        event_finalizer=event_finalizer,
    )
    event = FakeEvent("execute work")

    with caplog.at_level("ERROR", logger="astrbot"):
        _ = [item async for item in work_loop.submit(event)]
        [task] = background_tasks
        await asyncio.wait_for(task, timeout=5)

    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED
    assert session.error == "Work task failed."
    assert "btw-work-loop-secret" not in caplog.text
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
        _cancelled_result = await task
    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session.status is WorkSessionStatus.CANCELLED


@pytest.mark.asyncio
async def test_retention_does_not_expire_active_work():
    sessions = WorkSessionManager(max_age_seconds=1)
    session = await sessions.create("origin", "still running")
    session.updated_at = datetime.now(UTC) - timedelta(seconds=120)
    assert await sessions.get_by_id(session.id) is session


@pytest.mark.asyncio
async def test_schedule_runs_work_detached_without_an_acknowledgement():
    """The tool path schedules the task and leaves the reply to its caller."""
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
    event = FakeEvent("the complete task")

    session = await work_loop.schedule(event)

    assert session.request == "the complete task"
    assert event.result is None
    assert event.get_extra("btw_loop") == "work"
    assert event.get_extra("btw_agent_lock_key") == "umo-1:work"
    assert event.get_extra("btw_detached_work") is True
    assert len(background_tasks) == 1
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    assert session.status is WorkSessionStatus.RUNNING

    executor.release.set()
    [task] = background_tasks
    await asyncio.wait_for(task, timeout=1)

    assert session.status is WorkSessionStatus.COMPLETED
    result_dispatcher.assert_awaited_once_with(event)
    event_finalizer.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_schedule_requires_detached_execution_services():
    work_loop = WorkLoop(BlockingExecutor(), WorkSessionManager())

    with pytest.raises(RuntimeError):
        await work_loop.schedule(FakeEvent("the complete task"))


@pytest.mark.asyncio
async def test_schedule_refuses_after_the_loop_closed():
    work_loop = WorkLoop(BlockingExecutor(), WorkSessionManager())
    work_loop.configure_detached_execution(
        background_tasks=set(),
        result_dispatcher=AsyncMock(),
        event_finalizer=AsyncMock(),
    )
    await work_loop.close()

    with pytest.raises(RuntimeError):
        await work_loop.schedule(FakeEvent("the complete task"))


@pytest.mark.asyncio
async def test_work_loop_records_user_abort_as_cancelled():
    """Aborting a real run_agent through the executor must not read as success."""
    event = WorkEvent()
    runner = FakeRunner([SimpleNamespace(type="aborted", data={})], event=event)
    sessions = WorkSessionManager()
    work_loop = WorkLoop(RunAgentExecutor(runner), sessions)

    _ = [item async for item in work_loop.process(event)]

    # The real run_agent clears the stop flag when it reports the abort, so the
    # loop cannot rely on that flag to tell a cancellation from a completion.
    assert event.get_extra("agent_user_aborted") is True
    assert event.get_extra("agent_stop_requested") is False
    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.CANCELLED


@pytest.mark.asyncio
async def test_work_loop_records_agent_error_response_as_failed():
    """A local ``err`` response ends the generator normally but is a failure."""
    event = WorkEvent()
    runner = FakeRunner(
        [SimpleNamespace(type="err", data={"chain": MessageChain().message("boom")})],
        event=event,
    )
    sessions = WorkSessionManager()
    work_loop = WorkLoop(RunAgentExecutor(runner), sessions)

    _ = [item async for item in work_loop.process(event)]

    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED


@pytest.mark.asyncio
async def test_work_loop_records_runner_exception_as_failed():
    """run_agent converts a raising runner into a result, not into a re-raise."""
    event = WorkEvent()
    runner = FakeRunner(RuntimeError("provider exploded"), event=event, streaming=True)
    sessions = WorkSessionManager()
    work_loop = WorkLoop(RunAgentExecutor(runner), sessions)

    _ = [item async for item in work_loop.process(event)]

    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED


@pytest.mark.asyncio
async def test_work_loop_records_third_party_runner_error_as_failed():
    """A third-party runner failure is reported through its own marker."""
    event = WorkEvent()
    runner = FakeThirdPartyRunner(
        step_exception=RuntimeError("service unavailable"),
        final_resp=None,
    )
    sessions = WorkSessionManager()
    work_loop = WorkLoop(ThirdPartyResponseExecutor(runner), sessions)

    _ = [item async for item in work_loop.process(event)]

    assert event.get_extra(third_party.THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY) is True
    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED


@pytest.mark.asyncio
async def test_work_loop_records_a_run_the_session_refused_as_failed():
    """Session admission can decline a work run before any Agent is built."""
    event = WorkEvent()
    stage = agent_request.AgentRequestSubStage.__new__(
        agent_request.AgentRequestSubStage
    )
    stage.ctx = SimpleNamespace(astrbot_config={"provider_settings": {"enable": True}})
    stage.session_services = SimpleNamespace(
        should_process_llm_request=AsyncMock(return_value=False)
    )
    sessions = WorkSessionManager()
    work_loop = WorkLoop(AdmissionSkipExecutor(stage), sessions)

    _ = [item async for item in work_loop.process(event)]

    assert event.get_extra("btw_loop") == "work"
    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED


@pytest.mark.asyncio
async def test_work_loop_does_not_report_a_silent_run_as_completed():
    """An executor that ran nothing is not evidence the task succeeded."""
    event = FakeEvent("执行命令")
    sessions = WorkSessionManager()
    work_loop = WorkLoop(SilentExecutor(), sessions)

    _ = [item async for item in work_loop.process(event)]

    session = await sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED
