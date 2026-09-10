from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.conversation_loop import ConversationLoop


class FakeAgentRequest:
    def __init__(self) -> None:
        self.initialize = AsyncMock()
        self.process_calls = []

    async def process(self, event):
        self.process_calls.append(event)
        yield "first"
        yield "second"


class FakeEvent:
    def __init__(self) -> None:
        self.extras = {}

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)


@pytest.mark.asyncio
@pytest.mark.parametrize("btw", [{"enabled": True}, {"enabled": False}, {}, None])
async def test_conversation_entry_preserves_agent_execution_and_disabled_metadata(btw):
    executor = FakeAgentRequest()
    loop = ConversationLoop(executor)
    ctx = SimpleNamespace(astrbot_config={"btw": btw})
    await loop.initialize(ctx)
    event = FakeEvent()

    assert [item async for item in loop.process(event)] == ["first", "second"]
    executor.initialize.assert_awaited_once_with(ctx)
    assert executor.process_calls == [event]
    assert event.extras == (
        {"btw_loop": "conversation"} if btw and btw["enabled"] else {}
    )


@pytest.mark.asyncio
async def test_explicit_work_uses_the_work_executor_without_a_classifier():
    executor = FakeAgentRequest()
    loop = ConversationLoop(executor)
    await loop.initialize(
        SimpleNamespace(
            astrbot_config={
                "btw": {"enabled": True, "work_loop": {"enabled": True}},
            }
        )
    )
    event = FakeEvent()
    event.message_str = "inspect the workspace"
    event.unified_msg_origin = "origin"
    event.set_extra("btw_force_work", True)

    assert [item async for item in loop.process(event)] == ["first", "second"]
    assert event.get_extra("btw_loop") == "work"
    session = await loop.work_sessions.get_for_origin("origin")
    assert session.status.value == "completed"
