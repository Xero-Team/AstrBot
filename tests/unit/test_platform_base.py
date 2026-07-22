import asyncio
from asyncio import Queue
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_platform_termination_cancels_send_metric_task(
    monkeypatch: pytest.MonkeyPatch,
):
    """A send metric cannot continue after its adapter has been terminated."""
    metric_started = asyncio.Event()

    async def blocked_metric_upload(**_kwargs) -> None:
        metric_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        "astrbot.core.platform.platform.Metric.upload",
        blocked_metric_upload,
    )
    platform = _DummyPlatform({}, Queue())
    session = MessageSession("dummy", MessageType.FRIEND_MESSAGE, "session")

    await platform.send_by_session(session, MessageChain())
    await asyncio.wait_for(metric_started.wait(), timeout=1)
    tasks = set(platform._background_tasks)
    assert len(tasks) == 1

    await platform._cancel_background_tasks()

    assert all(task.cancelled() for task in tasks)
    assert not platform._background_tasks
