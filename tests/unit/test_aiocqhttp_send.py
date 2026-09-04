from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_aiocqhttp_send_keeps_text_and_image_in_one_message(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr(
        Comp.Image,
        "convert_to_base64",
        AsyncMock(return_value="dGVzdA=="),
    )
    chain = MessageChain(
        [
            Comp.Plain("caption"),
            Comp.Image.fromURL("https://example.com/a.jpg"),
        ]
    )

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=True,
        session_id="123456",
    )

    bot.send_group_msg.assert_awaited_once()
    messages = bot.send_group_msg.await_args.kwargs["message"]
    assert [segment["type"] for segment in messages] == ["text", "image"]
    assert messages[0]["data"]["text"] == "caption"


@pytest.mark.asyncio
async def test_aiocqhttp_send_splits_video_from_text_and_image(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr(
        Comp.Image,
        "convert_to_base64",
        AsyncMock(return_value="dGVzdA=="),
    )
    chain = MessageChain(
        [
            Comp.Plain("before"),
            Comp.Image.fromURL("https://example.com/a.jpg"),
            Comp.Video.fromURL("https://example.com/a.mp4"),
            Comp.Plain("after"),
        ]
    )

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=True,
        session_id="123456",
    )

    assert bot.send_group_msg.await_count == 3
    first, video, last = bot.send_group_msg.await_args_list
    assert [segment["type"] for segment in first.kwargs["message"]] == [
        "text",
        "image",
    ]
    assert [segment["type"] for segment in video.kwargs["message"]] == ["video"]
    assert video.kwargs["message"][0]["data"]["file"] == "https://example.com/a.mp4"
    assert [segment["type"] for segment in last.kwargs["message"]] == ["text"]
    assert last.kwargs["message"][0]["data"]["text"] == "after"
