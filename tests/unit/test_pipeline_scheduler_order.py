import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.reply import reply_text
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.stage import Stage
from astrbot.core.utils.active_event_registry import ActiveEventRegistry


class PipelineEvent:
    def __init__(self) -> None:
        self.stopped = False
        self.result = None
        self.stage_trace: list[str] = []
        self.trace = MagicMock()
        self._execution_active = False
        self.requires_empty_completion = False
        self.unified_msg_origin = "webchat:FriendMessage:pipeline"
        self.cleaned = False
        self._extras: dict[str, object] = {}
        self.sent_none = False

    def is_stopped(self) -> bool:
        if self.stopped:
            return True
        return bool(self.result and self.result.is_stopped())

    def get_result(self):
        return self.result

    def set_result(self, result) -> None:
        self.result = result

    def clear_result(self) -> None:
        self.result = None

    def stop_event(self) -> None:
        self.stopped = True

    def cleanup_temporary_local_files(self) -> None:
        self.cleaned = True

    def get_platform_id(self) -> str:
        return "webchat"

    def get_platform_name(self) -> str:
        return "webchat"

    def get_message_outline(self) -> str:
        return "hi"

    def get_extra(self, key: str | None = None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def set_extra(self, key, value) -> None:
        self._extras[key] = value

    async def send(self, message) -> None:
        if message is None:
            self.sent_none = True


class OnionStage(Stage):
    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent):
        event.stage_trace.append("pre")
        yield
        event.stage_trace.append("post")


class TraceStage(Stage):
    def __init__(self, label: str, *, stop: bool = False) -> None:
        self.label = label
        self.stop = stop

    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent) -> None:
        event.stage_trace.append(self.label)
        if self.stop:
            event.stop_event()


class CancelStage(Stage):
    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent) -> None:
        event.stage_trace.append("cancel")
        raise asyncio.CancelledError


class StoppedReplyStage(Stage):
    def __init__(self) -> None:
        self.resumed = False

    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent):
        reply_text(event, "command reply")
        yield
        self.resumed = True


class StopWithoutResultStage(Stage):
    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent):
        event.stop_event()
        yield


class NonYieldingStage(Stage):
    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent):
        if False:
            yield


class RecordingResponderStage(Stage):
    def __init__(self) -> None:
        self.delivered: list[str] = []

    async def initialize(self, ctx) -> None:
        return None

    async def process(self, event: PipelineEvent) -> None:
        result = event.get_result()
        if result is not None:
            self.delivered.append(result.get_plain_text())
            event.clear_result()


def _scheduler(stages: list[Stage]) -> PipelineScheduler:
    ctx = SimpleNamespace(
        execution_context=SimpleNamespace(
            active_event_registry=ActiveEventRegistry(),
        )
    )
    scheduler = PipelineScheduler(MagicMock())
    scheduler.ctx = ctx  # type: ignore[assignment]
    scheduler.stages = stages
    return scheduler


def test_builtin_stage_order_matches_stage_classes():
    from astrbot.core.pipeline.bootstrap import (
        builtin_stage_classes,
        builtin_stage_order,
    )

    assert (
        tuple(cls.__name__ for cls in builtin_stage_classes()) == builtin_stage_order()
    )


@pytest.mark.asyncio
async def test_pipeline_stops_propagation_but_finishes_onion_post():
    scheduler = _scheduler(
        [OnionStage(), TraceStage("middle", stop=True), TraceStage("late")]
    )
    event = PipelineEvent()

    await scheduler._process_stages(event)

    assert "pre" in event.stage_trace
    assert "middle" in event.stage_trace
    assert "late" not in event.stage_trace
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_pipeline_execute_reraises_cancelled_error_and_unregisters():
    scheduler = _scheduler([CancelStage()])
    event = PipelineEvent()
    registry = scheduler.ctx.execution_context.active_event_registry

    with pytest.raises(asyncio.CancelledError):
        await scheduler.execute(event)

    assert event.cleaned is True
    assert event.unified_msg_origin not in registry._events


@pytest.mark.asyncio
async def test_pipeline_skips_empty_completion_when_coalesce_defers_it():
    scheduler = _scheduler([TraceStage("only")])
    event = PipelineEvent()
    event.requires_empty_completion = True
    event.set_extra("skip_empty_completion", True)

    await scheduler.execute(event)

    assert event.sent_none is False


@pytest.mark.asyncio
async def test_pipeline_sends_empty_completion_for_webchat_when_not_skipped():
    scheduler = _scheduler([TraceStage("only")])
    event = PipelineEvent()
    event.requires_empty_completion = True

    await scheduler.execute(event)

    assert event.sent_none is True


@pytest.mark.asyncio
async def test_pipeline_delivers_stopped_generator_result_before_stopping():
    reply_stage = StoppedReplyStage()
    responder = RecordingResponderStage()
    scheduler = _scheduler([reply_stage, responder])
    event = PipelineEvent()

    await scheduler._process_stages(event)

    assert responder.delivered == ["command reply"]
    assert event.get_result() is None
    assert reply_stage.resumed is False


@pytest.mark.asyncio
async def test_pipeline_skips_downstream_for_stopped_generator_without_result():
    scheduler = _scheduler([StopWithoutResultStage(), TraceStage("late")])
    event = PipelineEvent()

    await scheduler._process_stages(event)

    assert "late" not in event.stage_trace
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_pipeline_continues_past_generator_without_yields():
    scheduler = _scheduler([NonYieldingStage(), TraceStage("after")])
    event = PipelineEvent()

    await scheduler._process_stages(event)

    assert "after" in event.stage_trace
