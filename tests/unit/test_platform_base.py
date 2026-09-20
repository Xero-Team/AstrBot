import asyncio
import logging
from asyncio import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata


class _DummyPlatform(Platform):
    async def run(self):
        return None

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(name="Dummy", description="Dummy", id="dummy")


class _CappedEnvelopePlatform(_DummyPlatform):
    ENVELOPE_OBSERVER_CAPACITY = 1


def _make_event(origin: str) -> AstrMessageEvent:
    event = AstrMessageEvent(
        message_str="hello",
        message_obj=SimpleNamespace(type="FriendMessage"),
        platform_meta=PlatformMetadata(name="Dummy", description="Dummy", id="dummy"),
        session_id=origin,
    )
    event.unified_msg_origin = f"dummy:FriendMessage:{origin}"
    return event


def test_commit_event_returns_false_when_queue_is_full():
    queue: Queue[AstrMessageEvent] = Queue(maxsize=1)
    platform = _DummyPlatform({}, queue)
    queue.put_nowait(_make_event("dummy:first"))

    result = platform.commit_event(_make_event("dummy:second"))

    assert result is False


def test_commit_event_binds_runtime_metrics_to_event():
    """An adapter passes its instance-owned telemetry capability to each event."""
    platform = _DummyPlatform({}, Queue())
    metrics = SimpleNamespace(upload=AsyncMock())
    platform.bind_metrics(metrics)
    event = _make_event("runtime-owned")

    assert platform.commit_event(event)
    assert event._metrics is metrics


@pytest.mark.asyncio
async def test_platform_termination_cancels_send_metric_task():
    """A send metric cannot continue after its adapter has been terminated."""
    metric_started = asyncio.Event()

    async def blocked_metric_upload(**_kwargs) -> None:
        metric_started.set()
        await asyncio.Event().wait()

    platform = _DummyPlatform({}, Queue())
    platform.bind_metrics(SimpleNamespace(upload=blocked_metric_upload))
    session = MessageSession("dummy", MessageType.FRIEND_MESSAGE, "session")

    await platform.send_by_session(session, MessageChain())
    await asyncio.wait_for(metric_started.wait(), timeout=1)
    tasks = set(platform._background_tasks)
    assert len(tasks) == 1

    await platform._cancel_background_tasks()

    assert all(task.cancelled() for task in tasks)
    assert not platform._background_tasks


def test_commit_event_counts_event_queue_full_drops():
    """A dropped ingress event is counted instead of only logged."""
    queue: Queue[AstrMessageEvent] = Queue(maxsize=1)
    platform = _DummyPlatform({}, queue)
    queue.put_nowait(_make_event("dummy:first"))

    assert platform.commit_event(_make_event("dummy:second")) is False
    assert platform.envelope_dispatch_stats()["event_queue_full_drops"] == 1


def test_platform_stats_expose_dispatch_counters():
    """Drop counters reach the existing per-platform stats surface."""
    platform = _DummyPlatform({}, Queue())

    assert platform.get_stats()["dispatch_stats"] == {
        "event_queue_full_drops": 0,
        "envelope_capacity_drops": 0,
        "envelope_tasks_inflight": 0,
    }


@pytest.mark.asyncio
async def test_envelope_capacity_drop_is_counted_and_throttled(caplog):
    """Saturation drops forwarding, but counts and logs it without flooding."""
    release = asyncio.Event()

    async def observer(envelope) -> None:
        await release.wait()

    platform = _CappedEnvelopePlatform({}, Queue())
    platform.add_envelope_observer(observer)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        for index in range(4):
            assert platform.commit_event(_make_event(f"dummy:event-{index}"))
        await asyncio.sleep(0)

    capacity_logs = [
        record
        for record in caplog.records
        if "Envelope observer capacity" in record.getMessage()
    ]
    assert len(capacity_logs) == 1
    assert platform.envelope_dispatch_stats()["envelope_capacity_drops"] == 3

    release.set()
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_envelope_dispatch_is_all_or_nothing_per_event():
    """An event is never forwarded to only a subset of observers."""
    release = asyncio.Event()
    seen: dict[str, set[str]] = {}

    def make_observer(name: str):
        async def observer(envelope) -> None:
            seen.setdefault(envelope.source_umo, set()).add(name)
            await release.wait()

        return observer

    class _TwoObserverPlatform(_DummyPlatform):
        ENVELOPE_OBSERVER_CAPACITY = 2

    platform = _TwoObserverPlatform({}, Queue())
    platform.add_envelope_observer(make_observer("a"))
    platform.add_envelope_observer(make_observer("b"))

    for index in range(3):
        platform.commit_event(_make_event(f"dummy:event-{index}"))

    for _ in range(5):
        await asyncio.sleep(0)

    assert len(seen) == 1
    assert all(names == {"a", "b"} for names in seen.values())
    assert platform.envelope_dispatch_stats()["envelope_capacity_drops"] == 2

    release.set()
    for _ in range(10):
        await asyncio.sleep(0)
