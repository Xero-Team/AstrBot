import asyncio

import pytest

from astrbot.core.utils.active_event_registry import ActiveEventRegistry


class _Event:
    def __init__(self, umo: str) -> None:
        self.unified_msg_origin = umo
        self.extras: dict[str, object] = {}
        self.stopped = False

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def stop_event(self) -> None:
        self.stopped = True


def test_request_agent_stop_invokes_all_callbacks_despite_one_failure():
    registry = ActiveEventRegistry()
    first = _Event("webchat:session")
    second = _Event("webchat:session")
    called: list[str] = []

    def broken_callback() -> None:
        called.append("broken")
        raise RuntimeError("callback failure")

    registry.register(first)
    registry.register(second)
    registry.register_agent_stop_callback(first, broken_callback)
    registry.register_agent_stop_callback(second, lambda: called.append("second"))

    assert registry.request_agent_stop_all("webchat:session") == 2
    assert first.extras["agent_stop_requested"] is True
    assert second.extras["agent_stop_requested"] is True
    assert set(called) == {"broken", "second"}


def test_unregister_agent_stop_callback_and_event_release_runner_controls():
    registry = ActiveEventRegistry()
    event = _Event("webchat:session")
    called: list[str] = []

    def callback() -> None:
        called.append("stop")

    registry.register(event)
    registry.register_agent_stop_callback(event, callback)

    registry.unregister_agent_stop_callback(event, callback)
    registry.request_agent_stop_all("webchat:session")
    assert called == []

    registry.register_agent_stop_callback(event, callback)
    registry.unregister(event)
    assert registry.request_agent_stop_all("webchat:session") == 0
    assert called == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_method", ["stop_all", "request_agent_stop_all"])
async def test_background_stop_cancels_only_matching_session(stop_method: str) -> None:
    registry = ActiveEventRegistry()
    event = _Event("session")
    excluded = _Event("session")
    other = _Event("other")
    owners = (event, event, excluded, other)
    tasks = [asyncio.create_task(asyncio.Event().wait()) for _ in owners]
    for owner, task in zip(owners, tasks, strict=True):
        registry.register_background_task(owner, task)

    try:
        assert getattr(registry, stop_method)("session", exclude=excluded) == 1
        await asyncio.gather(*tasks[:2], return_exceptions=True)
        assert all(task.cancelled() for task in tasks[:2])
        assert all(not task.done() for task in tasks[2:])
        assert event.stopped == (stop_method == "stop_all")
        assert not excluded.stopped and not other.stopped

        late_event = _Event("session")
        late_event.set_extra(
            "_background_stop_signal",
            registry.get_background_stop_signal(event),
        )
        late_task = asyncio.create_task(asyncio.sleep(0))
        tasks.append(late_task)
        registry.register_background_task(late_event, late_task)
        await asyncio.gather(late_task, return_exceptions=True)
        assert late_task.cancelled()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert not registry._background_tasks


@pytest.mark.asyncio
async def test_repeated_stop_does_not_interrupt_background_cleanup() -> None:
    registry = ActiveEventRegistry()
    event = _Event("session")
    started = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()

    async def run() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    task = asyncio.create_task(run())
    registry.register_background_task(event, task)
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert registry.request_agent_stop_all("session") == 1
        await asyncio.wait_for(cleaning.wait(), timeout=1)
        assert registry.request_agent_stop_all("session") == 1
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1)

    assert task.cancelled()
    assert not registry._background_cancel_requested
