import asyncio

import pytest

from astrbot.core.webchat.queue_manager import WebChatQueueManager


@pytest.mark.asyncio
async def test_removed_back_queue_unblocks_pending_writer():
    queue_manager = WebChatQueueManager(back_queue_maxsize=1)
    request_id = "request-1"
    queue = queue_manager.get_or_create_back_queue(request_id, "conversation-1")
    await queue.put({"type": "plain", "data": "first"})

    blocked_writer = asyncio.create_task(
        queue_manager.put_back_queue(
            request_id,
            {"type": "plain", "data": "second"},
        )
    )
    await asyncio.sleep(0)
    assert not blocked_writer.done()

    queue_manager.remove_back_queue(request_id)

    assert await asyncio.wait_for(blocked_writer, timeout=1) is False
    assert not await queue_manager.put_back_queue(
        request_id,
        {"type": "plain", "data": "late"},
    )


@pytest.mark.asyncio
async def test_replaced_listener_remains_tracked_after_old_task_finishes():
    queue_manager = WebChatQueueManager()

    async def _callback(data: tuple) -> None:
        _ = data

    queue_manager.set_listener(_callback)
    queue_manager.get_or_create_queue("conversation-1")
    old_listener = queue_manager._listener_tasks["conversation-1"]

    queue_manager.remove_queue("conversation-1")
    queue_manager.get_or_create_queue("conversation-1")
    new_listener = queue_manager._listener_tasks["conversation-1"]

    await asyncio.gather(old_listener, return_exceptions=True)
    await asyncio.sleep(0)

    assert queue_manager._listener_tasks.get("conversation-1") is new_listener
    await queue_manager.clear_listener()


@pytest.mark.asyncio
async def test_replacing_listener_keeps_new_task_tracked():
    queue_manager = WebChatQueueManager()

    async def _callback(_data: tuple) -> None:
        return None

    queue_manager.set_listener(_callback)
    queue_manager.get_or_create_queue("conversation-1")
    old_listener = queue_manager._listener_tasks["conversation-1"]

    queue_manager.remove_queue("conversation-1")
    queue_manager.get_or_create_queue("conversation-1")
    new_listener = queue_manager._listener_tasks["conversation-1"]

    await asyncio.gather(old_listener, return_exceptions=True)
    await asyncio.sleep(0)

    assert queue_manager._listener_tasks.get("conversation-1") is new_listener
    await queue_manager.clear_listener()
