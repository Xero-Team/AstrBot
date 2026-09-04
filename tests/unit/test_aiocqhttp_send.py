from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
import astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event as aiocqhttp_send
from astrbot.core.message.message_event_result import MessageChain

AiocqhttpMessageEvent = aiocqhttp_send.AiocqhttpMessageEvent

pytestmark = pytest.mark.platform


@pytest.fixture(autouse=True)
def zero_split_send_interval(monkeypatch):
    monkeypatch.setattr(aiocqhttp_send, "_SPLIT_SEND_INTERVAL_SECONDS", 0.0)


def _patch_media_converters(monkeypatch) -> None:
    monkeypatch.setattr(
        Comp.Image,
        "convert_to_base64",
        AsyncMock(return_value="dGVzdA=="),
    )
    monkeypatch.setattr(
        Comp.Record,
        "convert_to_base64",
        AsyncMock(return_value="cmVjb3Jk"),
    )


def _types(call) -> list[str]:
    return [segment["type"] for segment in call.kwargs["message"]]


async def _send(
    bot,
    chain: MessageChain,
    *,
    is_group: bool = True,
    session_id: str = "123456",
) -> None:
    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=is_group,
        session_id=session_id,
    )


@pytest.mark.asyncio
async def test_aiocqhttp_send_keeps_text_and_image_in_one_message(monkeypatch):
    bot = AsyncMock()
    _patch_media_converters(monkeypatch)
    chain = MessageChain(
        [
            Comp.Plain("caption"),
            Comp.Image.fromURL("https://example.com/a.jpg"),
        ]
    )

    await _send(bot, chain)

    bot.send_group_msg.assert_awaited_once()
    messages = bot.send_group_msg.await_args.kwargs["message"]
    assert [segment["type"] for segment in messages] == ["text", "image"]
    assert messages[0]["data"]["text"] == "caption"


@pytest.mark.asyncio
async def test_aiocqhttp_send_splits_video_from_text_and_image(monkeypatch):
    bot = AsyncMock()
    _patch_media_converters(monkeypatch)
    chain = MessageChain(
        [
            Comp.Plain("before"),
            Comp.Image.fromURL("https://example.com/a.jpg"),
            Comp.Video.fromURL("https://example.com/a.mp4"),
            Comp.Plain("after"),
        ]
    )

    await _send(bot, chain)

    assert bot.send_group_msg.await_count == 3
    first, video, last = bot.send_group_msg.await_args_list
    assert _types(first) == ["text", "image"]
    assert _types(video) == ["video"]
    assert video.kwargs["message"][0]["data"]["file"] == "https://example.com/a.mp4"
    assert _types(last) == ["text"]
    assert last.kwargs["message"][0]["data"]["text"] == "after"


@pytest.mark.asyncio
async def test_aiocqhttp_send_splits_record_from_text_and_image(monkeypatch):
    bot = AsyncMock()
    _patch_media_converters(monkeypatch)
    chain = MessageChain(
        [
            Comp.Plain("before"),
            Comp.Image.fromURL("https://example.com/a.jpg"),
            Comp.Record.fromURL("https://example.com/a.wav"),
            Comp.Plain("after"),
        ]
    )

    await _send(bot, chain)

    assert bot.send_group_msg.await_count == 3
    first, record, last = bot.send_group_msg.await_args_list
    assert _types(first) == ["text", "image"]
    assert _types(record) == ["record"]
    assert record.kwargs["message"][0]["data"]["file"] == "base64://cmVjb3Jk"
    assert _types(last) == ["text"]
    assert last.kwargs["message"][0]["data"]["text"] == "after"


@pytest.mark.asyncio
async def test_aiocqhttp_send_keeps_mixable_neighbors_around_file(monkeypatch):
    bot = AsyncMock()
    _patch_media_converters(monkeypatch)
    chain = MessageChain(
        [
            Comp.Plain("before"),
            Comp.Image.fromURL("https://example.com/a.jpg"),
            Comp.File(name="demo.bin", url="https://example.com/demo.bin"),
            Comp.Plain("after"),
        ]
    )

    await _send(bot, chain)

    assert bot.send_group_msg.await_count == 3
    first, file_call, last = bot.send_group_msg.await_args_list
    assert _types(first) == ["text", "image"]
    assert _types(file_call) == ["file"]
    assert (
        file_call.kwargs["message"][0]["data"]["file"] == "https://example.com/demo.bin"
    )
    assert _types(last) == ["text"]
    assert last.kwargs["message"][0]["data"]["text"] == "after"


@pytest.mark.asyncio
async def test_aiocqhttp_send_splits_consecutive_videos():
    bot = AsyncMock()
    chain = MessageChain(
        [
            Comp.Video.fromURL("https://example.com/a.mp4"),
            Comp.Video.fromURL("https://example.com/b.mp4"),
        ]
    )

    await _send(bot, chain)

    assert bot.send_group_msg.await_count == 2
    first, second = bot.send_group_msg.await_args_list
    assert _types(first) == ["video"]
    assert first.kwargs["message"][0]["data"]["file"] == "https://example.com/a.mp4"
    assert _types(second) == ["video"]
    assert second.kwargs["message"][0]["data"]["file"] == "https://example.com/b.mp4"


@pytest.mark.asyncio
async def test_aiocqhttp_send_splits_video_on_private_messages(monkeypatch):
    bot = AsyncMock()
    _patch_media_converters(monkeypatch)
    chain = MessageChain(
        [
            Comp.Plain("caption"),
            Comp.Video.fromURL("https://example.com/a.mp4"),
        ]
    )

    await _send(bot, chain, is_group=False)

    assert bot.send_private_msg.await_count == 2
    bot.send_group_msg.assert_not_awaited()
    first, video = bot.send_private_msg.await_args_list
    assert _types(first) == ["text"]
    assert _types(video) == ["video"]


@pytest.mark.asyncio
async def test_aiocqhttp_send_paces_consecutive_split_messages(monkeypatch):
    monkeypatch.setattr(aiocqhttp_send, "_SPLIT_SEND_INTERVAL_SECONDS", 0.5)
    sleep = AsyncMock()
    monkeypatch.setattr(aiocqhttp_send, "asyncio", SimpleNamespace(sleep=sleep))
    bot = AsyncMock()
    chain = MessageChain(
        [
            Comp.Plain("before"),
            Comp.Video.fromURL("https://example.com/a.mp4"),
            Comp.Plain("after"),
        ]
    )

    await _send(bot, chain)

    assert bot.send_group_msg.await_count == 3
    assert sleep.await_count == 2
    assert all(call.args == (0.5,) for call in sleep.await_args_list)
