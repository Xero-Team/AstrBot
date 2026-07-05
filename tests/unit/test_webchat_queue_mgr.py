import asyncio

import pytest

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr


@pytest.mark.asyncio
async def test_webchat_queue_listener_processes_messages_concurrently() -> None:
    queue_mgr = WebChatQueueMgr()
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

