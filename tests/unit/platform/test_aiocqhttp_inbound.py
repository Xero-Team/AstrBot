from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Forward, Node

pytestmark = pytest.mark.platform


class _FakeEvent(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _adapter(settings: dict):
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
        AiocqhttpAdapter,
    )

    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = AsyncMock()
    forward_settings = settings.get("onebot_forward")
    adapter._onebot_forward_settings = (
        forward_settings if isinstance(forward_settings, dict) else {}
    )
    return adapter


def _message_event() -> _FakeEvent:
    return _FakeEvent(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 654321,
            "self_id": 123456,
            "message_id": 900,
            "message": [{"type": "forward", "data": {"id": "f"}}],
            "sender": {"user_id": 111222, "nickname": "tester"},
        }
    )


@pytest.mark.asyncio
async def test_aiocqhttp_expands_forward_from_node_wrapped_payload() -> None:
    adapter = _adapter({"onebot_forward": {"expand_on_ingress": True}})
    adapter.bot.call_action = AsyncMock(
        return_value={
            "status": "ok",
            "retcode": 0,
            "data": {
                "messages": [
                    {
                        "type": "node",
                        "data": {
                            "user_id": 111222,
                            "nickname": "tester",
                            "content": [{"type": "text", "data": {"text": "hi"}}],
                        },
                    }
                ]
            },
        }
    )

    abm = await adapter._convert_handle_message_event(_message_event())

    forward = abm.message[0]
    assert isinstance(forward, Forward)
    assert forward.content is not None
    assert isinstance(forward.content[0], Node)
    assert forward.content[0].name == "tester"
    assert forward.content[0].content[0].text == "hi"
    adapter.bot.call_action.assert_awaited_once_with("get_forward_msg", id="f")


@pytest.mark.asyncio
async def test_aiocqhttp_parses_flat_nodes_and_skips_unknown_segments() -> None:
    adapter = _adapter({"onebot_forward": {"expand_on_ingress": True}})
    adapter.bot.call_action = AsyncMock(
        return_value={
            "data": {
                "messages": [
                    {
                        "sender": {"user_id": 222, "nickname": "B"},
                        "message": [
                            {"type": "text", "data": {"text": "flat"}},
                            {"type": "future_segment", "data": {"x": 1}},
                        ],
                    }
                ]
            }
        }
    )

    abm = await adapter._convert_handle_message_event(_message_event())

    forward = abm.message[0]
    assert isinstance(forward, Forward)
    node = forward.content[0]
    assert node.name == "B"
    assert [type(component).__name__ for component in node.content] == ["Plain"]
    assert node.content[0].text == "flat"


@pytest.mark.asyncio
async def test_aiocqhttp_accepts_top_level_list_payload() -> None:
    adapter = _adapter({"onebot_forward": {"expand_on_ingress": True}})
    adapter.bot.call_action = AsyncMock(
        return_value={
            "data": [
                {
                    "user_id": 1,
                    "nickname": "A",
                    "message": "raw text",
                }
            ]
        }
    )

    abm = await adapter._convert_handle_message_event(_message_event())

    forward = abm.message[0]
    assert isinstance(forward, Forward)
    node = forward.content[0]
    assert node.name == "A"
    assert node.uin == "1"
    assert node.content[0].text == "raw text"


@pytest.mark.asyncio
async def test_aiocqhttp_forward_fetch_failure_preserves_original() -> None:
    adapter = _adapter({"onebot_forward": {"expand_on_ingress": True}})
    adapter.bot.call_action = AsyncMock(side_effect=RuntimeError("boom"))

    abm = await adapter._convert_handle_message_event(_message_event())

    forward = abm.message[0]
    assert isinstance(forward, Forward)
    assert forward.id == "f"
    assert forward.content is None


@pytest.mark.asyncio
async def test_aiocqhttp_expansion_disabled_never_calls_backend() -> None:
    adapter = _adapter({})
    adapter.bot.call_action = AsyncMock()

    abm = await adapter._convert_handle_message_event(_message_event())

    forward = abm.message[0]
    assert isinstance(forward, Forward)
    assert forward.content is None
    adapter.bot.call_action.assert_not_awaited()
