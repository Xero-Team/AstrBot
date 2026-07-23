import asyncio
import importlib

import pytest

from astrbot.core.webchat.queue_manager import WebChatQueueManager


def test_webchat_queue_manager_module_has_no_runtime_singleton() -> None:
    module = importlib.import_module("astrbot.core.webchat.queue_manager")

    assert not hasattr(module, "webchat" + "_queue_mgr")


@pytest.mark.asyncio
async def test_webchat_queue_managers_isolate_identical_request_ids() -> None:
    first_manager = WebChatQueueManager()
    second_manager = WebChatQueueManager()
    first_queue = first_manager.get_or_create_back_queue("request-1")
    second_queue = second_manager.get_or_create_back_queue("request-1")

    assert await first_manager.put_back_queue("request-1", {"type": "plain"})
    assert await first_queue.get() == {"type": "plain"}
    assert second_queue.empty()


@pytest.mark.asyncio
async def test_webchat_queue_listener_processes_messages_concurrently() -> None:
    queue_mgr = WebChatQueueManager()
    queue = queue_mgr.get_or_create_queue("conversation-1")

    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_handled = asyncio.Event()
    handled: list[str] = []

    async def _callback(data: tuple) -> None:
        _, _, payload = data
        message_id = payload["message_id"]
        if message_id == "first":
            first_started.set()
            await release_first.wait()
        handled.append(message_id)
        if message_id == "second":
            second_handled.set()

    queue_mgr.set_listener(_callback)

    await queue.put(("user", "conversation-1", {"message_id": "first"}))
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    await queue.put(("user", "conversation-1", {"message_id": "second"}))
    await asyncio.wait_for(second_handled.wait(), timeout=1.0)

    release_first.set()
    await queue_mgr.clear_listener()

    assert "first" in handled
    assert "second" in handled
