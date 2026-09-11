import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.btw import runtime_registry
from astrbot.core.agent.btw.types import WorkSessionStatus
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.utils.active_event_registry import ActiveEventRegistry
from astrbot.core.webchat.emitter import emit_webchat_response
from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator

PROFILE_ID = "profile-1"


class WorkEvent:
    requires_empty_completion = True

    def __init__(self, run, queues, attachments):
        self.message_id = run.request_id
        self.unified_msg_origin = "webchat:FriendMessage:shared"
        self.message_str = "run work"
        self.queues = queues
        self.attachments = attachments
        self.resource = SimpleNamespace(config_id=PROFILE_ID)
        self.extras = {}
        self.result = None
        self.cleaned = 0
        self.trace = []
        self._stopped = False

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value):
        self.extras[key] = value

    def set_result(self, result):
        self.result = result

    def is_stopped(self):
        return self._stopped

    def stop_event(self):
        self._stopped = True

    def get_platform_id(self):
        return "webchat"

    def get_message_outline(self):
        return self.message_str

    def cleanup_temporary_local_files(self):
        self.cleaned += 1

    async def send(self, message):
        return await emit_webchat_response(
            self.queues, self.message_id, message, attachments_dir=self.attachments
        )


class BlockingExecutor:
    def __init__(self):
        self.started = {}
        self.release = {}

    async def process(self, event):
        self.started[event.message_id].set()
        await self.release[event.message_id].wait()
        await event.send(MessageChain(type="agent_stats").message('{"calls": 1}'))
        event.set_result(MessageEventResult().message("finished " + event.message_id))
        yield


class SubmitStage(Stage):
    def __init__(self, work):
        self.work = work

    async def initialize(self, ctx):
        pass

    def configure_detached_work(self, **kwargs):
        self.work.configure_detached_execution(**kwargs)

    async def process(self, event):
        async for progress in self.work.submit(event):
            yield progress

    async def close(self):
        await self.work.close()


class DecorateStage(ResultDecorateStage):
    async def initialize(self, ctx):
        pass

    async def process(self, event):
        if event.result is None:
            return
        event.trace.append("decorate-before")
        yield
        event.trace.append("decorate-after")


class SendStage(Stage):
    async def initialize(self, ctx):
        pass

    async def process(self, event):
        if event.result is None:
            return
        event.trace.append("send")
        await event.send(event.result)
        event.result = None


class StopAfterAcknowledgementStage(Stage):
    """Stops the event once the acknowledgement has reached the platform."""

    async def initialize(self, ctx):
        pass

    async def process(self, event):
        if event.result is not None:
            return
        event.trace.append("stop")
        event.stop_event()


async def setup_work(tmp_path, *, stop_after_acknowledgement: bool = False):
    queues = WebChatQueueManager()
    coordinator = WebChatRunCoordinator(queues)
    executor = BlockingExecutor()
    sessions = WorkSessionManager()
    work = WorkLoop(executor, sessions)
    ctx = SimpleNamespace(
        execution_context=SimpleNamespace(
            active_event_registry=ActiveEventRegistry(),
            background_tasks=set(),
        )
    )
    scheduler = PipelineScheduler(ctx)
    stage_classes = [lambda: SubmitStage(work), DecorateStage, SendStage]
    if stop_after_acknowledgement:
        stage_classes.append(StopAfterAcknowledgementStage)
    scheduler.stage_classes = stage_classes
    await scheduler.initialize()
    events = []
    for request_id in ("first", "second"):
        run = coordinator.create_run(
            session_id="shared", username="test", request_id=request_id
        )
        executor.started[request_id] = asyncio.Event()
        executor.release[request_id] = asyncio.Event()
        events.append(WorkEvent(run, queues, tmp_path))
    return scheduler, work, executor, queues, events


@pytest.mark.asyncio
async def test_background_webchat_keeps_each_request_until_its_final_result(tmp_path):
    scheduler, work, executor, queues, events = await setup_work(tmp_path)
    first, second = events
    try:
        await scheduler.execute(first)
        await scheduler.execute(second)
        await asyncio.wait_for(executor.started["first"].wait(), timeout=1)
        await asyncio.wait_for(executor.started["second"].wait(), timeout=1)
        for event in events:
            ack = queues.back_queues[event.message_id].get_nowait()
            assert ack["type"] == "plain"
            assert ack["message_id"] == event.message_id
            assert queues.back_queues[event.message_id].empty()
            assert event.cleaned == 0

        executor.release["first"].set()
        first_task = next(t for t, (event, _) in work._tasks.items() if event is first)
        await asyncio.wait_for(first_task, timeout=1)
        messages = [queues.back_queues["first"].get_nowait() for _ in range(3)]
        assert [message["type"] for message in messages] == ["plain", "plain", "end"]
        assert messages[0]["chain_type"] == "agent_stats"
        assert messages[1]["data"] == "finished first"
        assert {message["message_id"] for message in messages} == {"first"}
        assert queues.back_queues["second"].empty()
        assert first.cleaned == 1 and second.cleaned == 0
        assert first.trace == ["decorate-before", "send", "decorate-after"] * 2
        await scheduler.finalize_detached_event(first)
        assert first.cleaned == 1
    finally:
        await scheduler.close()
    assert second.cleaned == 1
    assert queues.back_queues["second"].get_nowait()["type"] == "end"


@pytest.mark.asyncio
async def test_closing_scheduler_cleans_work_cancelled_before_it_starts(tmp_path):
    scheduler, work, _, queues, events = await setup_work(tmp_path)
    event = events[0]
    await scheduler.execute(event)
    await scheduler.close()
    session = await work.sessions.get_for_origin(event.unified_msg_origin)
    assert session.status is WorkSessionStatus.CANCELLED
    assert event.cleaned == 1
    assert not scheduler.ctx.execution_context.active_event_registry._events
    assert [
        queues.back_queues[event.message_id].get_nowait()["type"] for _ in range(2)
    ] == ["plain", "end"]


@pytest.mark.asyncio
async def test_finalizer_releases_resources_even_when_completion_delivery_fails(
    tmp_path,
):
    scheduler, _, _, _, events = await setup_work(tmp_path)
    event = events[0]
    scheduler.ctx.execution_context.active_event_registry.register(event)

    async def fail(message):
        raise OSError("delivery unavailable")

    event.send = fail
    with pytest.raises(OSError, match="delivery unavailable"):
        await scheduler.finalize_detached_event(event)
    assert event.cleaned == 1
    assert not scheduler.ctx.execution_context.active_event_registry._events


@pytest.mark.asyncio
async def test_work_delivery_failure_marks_failed_and_finishes_the_request(tmp_path):
    scheduler, work, executor, _, events = await setup_work(tmp_path)
    event = events[0]
    await scheduler.execute(event)
    await asyncio.wait_for(executor.started[event.message_id].wait(), timeout=1)

    async def fail_delivery(event):
        raise OSError("cannot deliver")

    work._result_dispatcher = fail_delivery
    task = next(iter(work._tasks))
    executor.release[event.message_id].set()
    task_result = await task
    assert task_result is None
    session = await work.sessions.get_for_origin(event.unified_msg_origin)
    assert session.status is WorkSessionStatus.FAILED
    assert session.error == "Work task failed."
    assert event.cleaned == 1


@pytest.mark.asyncio
async def test_close_during_acknowledgement_prevents_late_background_submission(
    tmp_path,
):
    scheduler, work, _, _, events = await setup_work(tmp_path)
    event = events[0]
    admission = work.submit(event)
    await anext(admission)
    await work.close()
    assert [item async for item in admission] == []
    assert not work._tasks
    assert not event.get_extra("btw_detached_work")
    session = await work.sessions.get_for_origin(event.unified_msg_origin)
    assert session.status is WorkSessionStatus.CANCELLED


@pytest.mark.asyncio
async def test_closed_work_rejects_submission_without_creating_a_session(tmp_path):
    scheduler, work, _, _, events = await setup_work(tmp_path)
    await work.close()
    await scheduler.execute(events[0])
    assert await work.sessions.get_for_origin(events[0].unified_msg_origin) is None
    assert not work._tasks


@pytest.mark.asyncio
async def test_interrupted_acknowledgement_leaves_no_queued_work(tmp_path):
    """A stop between the acknowledgement and the hand-off must not strand work.

    The scheduler drops the submission generator the moment a later stage stops
    the event, so the acknowledgement is delivered while nothing owns the
    background run yet.
    """
    scheduler, work, _, queues, events = await setup_work(
        tmp_path, stop_after_acknowledgement=True
    )
    event = events[0]
    runtime_registry.register(PROFILE_ID, work.sessions)
    try:
        await scheduler.execute(event)
    finally:
        runtime_registry.unregister(PROFILE_ID, work.sessions)
        await scheduler.close()

    assert event.get_extra("btw_detached_work") is None
    assert queues.back_queues[event.message_id].get_nowait()["type"] == "plain"
    session = await work.sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.CANCELLED
    assert not work._tasks
    assert event.cleaned == 1


class ReceiptWorkEvent:
    """A work event whose platform answers every send with a real result."""

    requires_empty_completion = False

    def __init__(self, run, send_results):
        self.message_id = run.request_id
        self.unified_msg_origin = "webchat:FriendMessage:shared"
        self.message_str = "run work"
        self.resource = SimpleNamespace(config_id=PROFILE_ID)
        self.extras = {}
        self.result = None
        self.cleaned = 0
        self.trace = []
        self.plugins_name = []
        self.send_streaming = AsyncMock()
        self.stop_typing = AsyncMock()
        self._send_results = iter(send_results)

    def get_extra(self, key, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key, value):
        self.extras[key] = value

    def get_result(self):
        return self.result

    def set_result(self, result):
        self.result = result

    def clear_result(self):
        self.result = None

    def is_stopped(self):
        return False

    def cleanup_temporary_local_files(self):
        self.cleaned += 1

    def get_platform_id(self):
        return "test"

    def get_platform_name(self):
        return "test"

    def get_sender_name(self):
        return "tester"

    def get_sender_id(self):
        return "user"

    def _outline_chain(self, _chain):
        return "test"

    async def send(self, _chain):
        """Answer with the next scripted platform result."""
        result = next(self._send_results)
        if isinstance(result, BaseException):
            raise result
        return result


class WorkResultExecutor:
    """One work run that publishes a result and finishes."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process(self, event):
        self.started.set()
        await self.release.wait()
        event.set_result(MessageEventResult().message("work result"))
        yield


class ReceiptRespondStage(RespondStage):
    """The real respond stage bound to an isolated test runtime."""

    async def initialize(self, ctx):
        self.ctx = ctx
        self.config = {"provider_settings": {}}
        self.platform_settings = {"path_mapping": []}
        self.enable_seg = False


def _accepted() -> PlatformSendResult:
    return PlatformSendResult(
        platform_id="test",
        success=True,
        target="target",
        message_count=1,
        message_id="accepted-1",
    )


def _rejected() -> PlatformSendResult:
    return PlatformSendResult(
        platform_id="test",
        success=False,
        target="target",
        message_count=1,
        error_message="adapter rejected the final result",
    )


async def setup_receipt_work(executor, send_results):
    """Wire a real scheduler and respond stage around one work submission."""
    sessions = WorkSessionManager()
    work = WorkLoop(executor, sessions)
    ctx = SimpleNamespace(
        astrbot_config={},
        file_token_service=MagicMock(),
        handlers=SimpleNamespace(get_handlers_by_event_type=lambda *_a, **_k: []),
        plugins=SimpleNamespace(),
        execution_context=SimpleNamespace(
            active_event_registry=ActiveEventRegistry(),
            background_tasks=set(),
            persist_accepted_group_response=AsyncMock(),
        ),
    )
    scheduler = PipelineScheduler(ctx)
    scheduler.stage_classes = [
        lambda: SubmitStage(work),
        DecorateStage,
        ReceiptRespondStage,
    ]
    await scheduler.initialize()
    run = WebChatRunCoordinator(WebChatQueueManager()).create_run(
        session_id="shared", username="test", request_id="first"
    )
    return scheduler, work, ReceiptWorkEvent(run, send_results)


async def _run_receipt_work(scheduler, work, executor, event):
    await scheduler.execute(event)
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    executor.release.set()
    task = next(task for task, (owner, _) in work._tasks.items() if owner is event)
    await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_rejected_result_delivery_marks_the_work_failed():
    """The platform refused the final result after accepting the ack."""
    executor = WorkResultExecutor()
    scheduler, work, event = await setup_receipt_work(
        executor, [_accepted(), _rejected()]
    )
    try:
        await _run_receipt_work(scheduler, work, executor, event)
    finally:
        await scheduler.close()

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "failed"
    session = await work.sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.FAILED
    assert session.error == "Work result was not delivered."


@pytest.mark.asyncio
async def test_unconfirmed_result_delivery_is_not_reported_as_completed():
    """A send that raised proves neither delivery nor its absence."""
    executor = WorkResultExecutor()
    scheduler, work, event = await setup_receipt_work(
        executor, [_accepted(), OSError("delivery unavailable")]
    )
    try:
        await _run_receipt_work(scheduler, work, executor, event)
    finally:
        await scheduler.close()

    receipt = event.get_extra("delivery_receipt")
    assert receipt.status == "unknown"
    session = await work.sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.UNCONFIRMED
