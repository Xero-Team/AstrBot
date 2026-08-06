from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.btw import WorkSessionManager, WorkSessionStatus
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
    def __init__(self, message: str = "hello") -> None:
        self.unified_msg_origin = "umo-1"
        self.message_str = message
        self.extras = {}
        self.result = None

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def set_result(self, value) -> None:
        self.result = value


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        astrbot_config={
            "btw": {
                "enabled": True,
                "classifier": {"enabled": True},
                "work_loop": {"enabled": True, "max_concurrent": 2},
            }
        }
    )


@pytest.mark.asyncio
async def test_conversation_loop_initializes_the_current_agent_request_path():
    loop = ConversationLoop(FakeAgentRequest())
    ctx = _ctx()

    await loop.initialize(ctx)

    loop.agent_request.initialize.assert_awaited_once_with(ctx)
    assert loop.work_loop is not None


@pytest.mark.asyncio
async def test_conversation_loop_forwards_simple_chat_to_agent_request():
    loop = ConversationLoop(FakeAgentRequest())
    await loop.initialize(_ctx())
    event = FakeEvent()

    output = [item async for item in loop.process(event)]

    assert output == ["first", "second"]
    assert loop.agent_request.process_calls == [event]
    assert event.get_extra("btw_loop") == "conversation"


@pytest.mark.asyncio
async def test_conversation_loop_runs_classified_work_and_completes_session():
    loop = ConversationLoop(FakeAgentRequest())
    await loop.initialize(_ctx())
    event = FakeEvent("请帮我重构这个项目")

    output = [item async for item in loop.process(event)]

    assert output == ["first", "second"]
    assert event.get_extra("btw_loop") == "work"
    session = await loop.work_sessions.get_for_origin(event.unified_msg_origin)
    assert session is not None
    assert session.status is WorkSessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_conversation_loop_answers_recent_work_status_without_agent_call():
    sessions = WorkSessionManager()
    session = await sessions.create("umo-1", "重构项目")
    await sessions.update_status(session.id, WorkSessionStatus.RUNNING)
    agent_request = FakeAgentRequest()
    loop = ConversationLoop(agent_request, work_sessions=sessions)
    await loop.initialize(_ctx())
    event = FakeEvent("进度怎么样了？")

    output = [item async for item in loop.process(event)]

    assert output == [None]
    assert agent_request.process_calls == []
    assert event.result.get_plain_text() == "📊 工作任务正在执行。"


@pytest.mark.asyncio
async def test_conversation_loop_answers_completed_work_status_without_agent_call():
    sessions = WorkSessionManager()
    session = await sessions.create("umo-1", "重构项目")
    await sessions.update_status(session.id, WorkSessionStatus.COMPLETED)
    agent_request = FakeAgentRequest()
    loop = ConversationLoop(agent_request, work_sessions=sessions)
    await loop.initialize(_ctx())
    event = FakeEvent("任务状态")

    output = [item async for item in loop.process(event)]

    assert output == [None]
    assert agent_request.process_calls == []
    assert event.result.get_plain_text() == "📊 工作任务已完成。"
