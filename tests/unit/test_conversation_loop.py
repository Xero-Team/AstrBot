import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

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
    def __init__(self, message: str = "hello") -> None:
        self.extras = {}
        self.message_str = message
        self.unified_msg_origin = "origin"
        self.result = None

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def set_result(self, result):
        self.result = result


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("btw_enabled", "work_enabled", "classifier_enabled", "expected_loop"),
    [
        (False, True, True, None),
        (True, False, True, "conversation"),
        (True, True, False, "conversation"),
        (True, True, True, "work"),
    ],
)
async def test_rule_routing_requires_all_three_flags(
    btw_enabled, work_enabled, classifier_enabled, expected_loop
):
    executor = FakeAgentRequest()
    loop = ConversationLoop(executor)
    await loop.initialize(
        SimpleNamespace(
            astrbot_config={
                "btw": {
                    "enabled": btw_enabled,
                    "work_loop": {"enabled": work_enabled},
                    "classifier": {"enabled": classifier_enabled},
                }
            }
        )
    )
    event = FakeEvent("请帮我重构这个项目")

    assert [item async for item in loop.process(event)] == ["first", "second"]
    assert event.get_extra("btw_loop") == expected_loop
    assert executor.process_calls == [event]
    session = await loop.work_sessions.get_for_origin("origin")
    if expected_loop == "work":
        assert session is not None
        assert session.status.value == "completed"
    else:
        assert session is None


@pytest.mark.asyncio
async def test_explicit_work_skips_rule_classification():
    executor = FakeAgentRequest()
    loop = ConversationLoop(executor)
    await loop.initialize(
        SimpleNamespace(
            astrbot_config={
                "btw": {
                    "enabled": True,
                    "work_loop": {"enabled": True},
                    "classifier": {"enabled": True},
                }
            }
        )
    )
    loop.classifier.classify = AsyncMock(side_effect=AssertionError("not consulted"))
    event = FakeEvent("hello")
    event.set_extra("btw_force_work", True)

    assert [item async for item in loop.process(event)] == ["first", "second"]
    assert event.get_extra("btw_loop") == "work"
    loop.classifier.classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_classified_work_keeps_distinct_background_requests_for_one_origin():
    executor = FakeAgentRequest()
    loop = ConversationLoop(executor)
    await loop.initialize(
        SimpleNamespace(
            astrbot_config={
                "btw": {
                    "enabled": True,
                    "work_loop": {"enabled": True},
                    "classifier": {"enabled": True},
                }
            }
        )
    )
    tasks = set()
    dispatch = AsyncMock()
    finalize = AsyncMock()
    loop.configure_detached_work(
        background_tasks=tasks, result_dispatcher=dispatch, event_finalizer=finalize
    )
    events = [FakeEvent("refactor first module"), FakeEvent("refactor second module")]
    try:
        for event in events:
            assert [item async for item in loop.process(event)] == [None]
            assert event.get_extra("btw_loop") == "work"
            assert event.get_extra("btw_detached_work") is True
        assert len(tasks) == 2
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)
        session_ids = {event.get_extra("btw_work_session_id") for event in events}
        assert len(session_ids) == 2
        assert len(executor.process_calls) == 2
        assert dispatch.await_count == 4
        assert finalize.await_count == 2
        for event in events:
            assert executor.process_calls.count(event) == 1
            assert dispatch.await_args_list.count(call(event)) == 2
            assert finalize.await_args_list.count(call(event)) == 1
            session = await loop.work_sessions.get_by_id(
                event.get_extra("btw_work_session_id")
            )
            assert session.request == event.message_str
            assert session.status.value == "completed"
    finally:
        await loop.close()
