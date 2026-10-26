from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wechatpy.messages import TextMessage, VoiceMessage

from astrbot.core.platform.sources.weixin_official_account import weixin_offacc_adapter
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
    WeixinOfficialAccountPlatformAdapter,
)

pytestmark = pytest.mark.platform


def _adapter() -> WeixinOfficialAccountPlatformAdapter:
    adapter = WeixinOfficialAccountPlatformAdapter(
        {
            "id": "weixin-offacc-test",
            "appid": "appid",
            "secret": "secret",
            "token": "token",
            "encoding_aes_key": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "port": 10000,
        },
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_weixin_offacc_convert_message_voice_resolves_lazily(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download = MagicMock(
        return_value=SimpleNamespace(content=b"amr")
    )
    monkeypatch.setattr(
        weixin_offacc_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    msg = VoiceMessage(
        {
            "MsgType": "voice",
            "MediaId": "media-1",
            "ToUserName": "bot-1",
            "FromUserName": "user-1",
            "MsgId": 101,
            "CreateTime": 789,
        }
    )

    await adapter.convert_message(msg)

    abm = adapter.handle_msg.await_args.args[0]
    record = abm.message[0]
    assert record.file == ""
    adapter.client.media.download.assert_not_called()

    media_resolver = SimpleNamespace(
        to_path=AsyncMock(return_value="/tmp/weixin-offacc.wav")
    )
    with patch(
        "astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter.MediaResolver",
        return_value=media_resolver,
    ):
        await record._resolve_deferred_source()

    adapter.client.media.download.assert_called_once_with("media-1")
    assert record.file == "/tmp/weixin-offacc.wav"
    assert record.path == "/tmp/weixin-offacc.wav"
    assert (tmp_path / "weixin_offacc_media-1.amr").read_bytes() == b"amr"
    assert getattr(abm, "temporary_file_paths", []) == [
        str(tmp_path / "weixin_offacc_media-1.amr"),
        "/tmp/weixin-offacc.wav",
    ]


@pytest.mark.asyncio
async def test_weixin_offacc_convert_message_voice_keeps_raw_audio_when_conversion_fails(
    monkeypatch,
    tmp_path,
):
    adapter = _adapter()
    adapter.client.media.download = MagicMock(
        return_value=SimpleNamespace(content=b"amr")
    )
    monkeypatch.setattr(
        weixin_offacc_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    msg = VoiceMessage(
        {
            "MsgType": "voice",
            "MediaId": "media-2",
            "ToUserName": "bot-1",
            "FromUserName": "user-2",
            "MsgId": 102,
            "CreateTime": 790,
        }
    )

    await adapter.convert_message(msg)

    abm = adapter.handle_msg.await_args.args[0]
    record = abm.message[0]
    media_resolver = SimpleNamespace(
        to_path=AsyncMock(side_effect=RuntimeError("ffmpeg missing"))
    )
    with patch(
        "astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter.MediaResolver",
        return_value=media_resolver,
    ):
        await record._resolve_deferred_source()

    raw_path = str(tmp_path / "weixin_offacc_media-2.amr")
    assert record.file == raw_path
    assert record.path == raw_path
    assert getattr(abm, "temporary_file_paths", []) == [raw_path]


@pytest.mark.asyncio
async def test_unparseable_callback_raises_value_error(monkeypatch):
    adapter = _adapter()
    adapter.server.crypto = SimpleNamespace(decrypt_message=lambda *_args: "<xml/>")

    class _Request:
        args = {"msg_signature": "sig", "timestamp": "1", "nonce": "n"}

        async def get_data(self):
            return b"<xml/>"

    monkeypatch.setattr(weixin_offacc_adapter, "parse_message", lambda _xml: None)

    with pytest.raises(ValueError, match="Failed to parse WeChat message"):
        await adapter.server.handle_callback(_Request())


@pytest.mark.asyncio
async def test_active_send_mode_still_commits_inbound_events():
    adapter = _adapter()
    adapter.active_send_mode = True
    adapter.server.active_send_mode = True

    async def handle(message):
        await WeixinOfficialAccountPlatformAdapter.handle_msg(adapter, message)

    adapter.handle_msg = handle
    msg = TextMessage(
        {
            "MsgType": "text",
            "Content": "hello active",
            "ToUserName": "bot-1",
            "FromUserName": "user-active",
            "MsgId": 201,
            "CreateTime": 900,
        }
    )

    await adapter.convert_message(msg)

    event = adapter._event_queue.get_nowait()
    assert event.message_str == "hello active"
    assert event.message_obj.sender.user_id == "user-active"
    assert adapter.user_buffer == {}


@pytest.mark.asyncio
async def test_passive_send_accumulates_components_and_completes_future(monkeypatch):
    from astrbot.core.message.components import Plain
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_event import (
        WeixinOfficialAccountPlatformEvent,
    )

    async def fake_send(_self, _message):
        return None

    monkeypatch.setattr(AstrMessageEvent, "send", fake_send)
    future = asyncio.get_running_loop().create_future()
    event = object.__new__(WeixinOfficialAccountPlatformEvent)
    event.message_obj = SimpleNamespace(
        raw_message={"active_send_mode": False, "future": future},
        sender=SimpleNamespace(user_id="user-1"),
    )
    event.message_out = {"cached_xml": []}

    await event.send(MessageChain([Plain("first"), Plain("second")]))
    await event.send(MessageChain([Plain("third")]))

    assert event.message_out["cached_xml"] == ["first", "second", "third"]
    assert future.done()
    assert future.result() is None


@pytest.mark.asyncio
async def test_callback_keeps_completed_state_to_ignore_same_message_retries(
    monkeypatch,
):
    adapter = _adapter()
    adapter.server._maybe_encrypt = lambda xml, *_args: xml

    class _Request:
        args = {"msg_signature": "sig", "timestamp": "1", "nonce": "n"}

        async def get_data(self):
            return b"<xml/>"

    adapter.server.crypto = SimpleNamespace(decrypt_message=lambda *_args: "<xml/>")
    msg = TextMessage(
        {
            "MsgType": "text",
            "Content": "trigger",
            "ToUserName": "bot-1",
            "FromUserName": "user-stuck",
            "MsgId": 301,
            "CreateTime": 901,
        }
    )
    monkeypatch.setattr(
        weixin_offacc_adapter,
        "parse_message",
        lambda _xml: msg,
    )

    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    adapter.user_buffer["user-stuck"] = {
        "msg_id": "300",
        "preview": "old",
        "task": completed,
        "cached_xml": [],
        "started_at": 0.0,
    }
    adapter.server.callback = AsyncMock(return_value=None)

    result = await adapter.server.handle_callback(_Request())

    assert result == "success"
    assert adapter.user_buffer["user-stuck"]["msg_id"] == "301"
    assert adapter.server.callback.await_count == 1

    retry_result = await adapter.server.handle_callback(_Request())

    assert retry_result == "success"
    assert adapter.server.callback.await_count == 1


@pytest.mark.asyncio
async def test_callback_does_not_reprocess_a_completed_same_message(monkeypatch):
    adapter = _adapter()
    adapter.server._maybe_encrypt = lambda xml, *_args: xml

    class _Request:
        args = {"msg_signature": "sig", "timestamp": "1", "nonce": "n"}

        async def get_data(self):
            return b"<xml/>"

    adapter.server.crypto = SimpleNamespace(decrypt_message=lambda *_args: "<xml/>")
    msg = TextMessage(
        {
            "MsgType": "text",
            "Content": "retry",
            "ToUserName": "bot-1",
            "FromUserName": "user-retry",
            "MsgId": 401,
            "CreateTime": 902,
        }
    )
    monkeypatch.setattr(weixin_offacc_adapter, "parse_message", lambda _xml: msg)

    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    adapter.user_buffer["user-retry"] = {
        "msg_id": "401",
        "preview": "retry",
        "task": completed,
        "cached_xml": [],
        "started_at": 0.0,
    }
    adapter.server.callback = AsyncMock(return_value=None)

    result = await adapter.server.handle_callback(_Request())

    assert result == "success"
    assert adapter.user_buffer["user-retry"]["msg_id"] == "401"
    adapter.server.callback.assert_not_awaited()


def _request_stub():
    class _Request:
        args = {"msg_signature": "sig", "timestamp": "1", "nonce": "n"}

        async def get_data(self):
            return b"<xml/>"

    return _Request()


def _text_message(*, user: str, msg_id: int) -> TextMessage:
    return TextMessage(
        {
            "MsgType": "text",
            "Content": "retry",
            "ToUserName": "bot-1",
            "FromUserName": user,
            "MsgId": msg_id,
            "CreateTime": 903,
        }
    )


@pytest.mark.asyncio
async def test_callback_ignores_same_message_retry_after_cached_reply_drains(
    monkeypatch,
):
    adapter = _adapter()
    adapter.server._maybe_encrypt = lambda xml, *_args: xml
    adapter.server.crypto = SimpleNamespace(decrypt_message=lambda *_args: "<xml/>")
    msg = _text_message(user="user-drained", msg_id=501)
    monkeypatch.setattr(weixin_offacc_adapter, "parse_message", lambda _xml: msg)

    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    adapter.user_buffer["user-drained"] = {
        "msg_id": "501",
        "preview": "retry",
        "task": completed,
        "cached_xml": ["final reply"],
        "started_at": 0.0,
    }
    adapter.server.callback = AsyncMock(return_value=None)

    first = await adapter.server.handle_callback(_request_stub())

    assert "final reply" in first
    assert adapter.user_buffer["user-drained"]["msg_id"] == "501"

    retry = await adapter.server.handle_callback(_request_stub())

    assert retry == "success"
    adapter.server.callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_starts_a_new_trigger_when_message_has_no_unique_id(
    monkeypatch,
):
    adapter = _adapter()
    adapter.server._maybe_encrypt = lambda xml, *_args: xml
    adapter.server.crypto = SimpleNamespace(decrypt_message=lambda *_args: "<xml/>")
    msg = _text_message(user="user-event", msg_id=0)
    monkeypatch.setattr(weixin_offacc_adapter, "parse_message", lambda _xml: msg)

    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    adapter.user_buffer["user-event"] = {
        "msg_id": "0",
        "preview": "event",
        "task": completed,
        "cached_xml": [],
        "started_at": 0.0,
    }
    adapter.server.callback = AsyncMock(return_value=None)

    await adapter.server.handle_callback(_request_stub())

    assert adapter.server.callback.await_count == 1


@pytest.mark.asyncio
async def test_callback_returns_cached_media_xml_without_wrapping(monkeypatch):
    adapter = _adapter()
    adapter.server._maybe_encrypt = lambda xml, *_args: xml
    adapter.server.crypto = SimpleNamespace(decrypt_message=lambda *_args: "<xml/>")
    msg = _text_message(user="user-media", msg_id=601)
    monkeypatch.setattr(weixin_offacc_adapter, "parse_message", lambda _xml: msg)

    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    media_xml = "<xml><Image><MediaId>media-1</MediaId></Image></xml>"
    adapter.user_buffer["user-media"] = {
        "msg_id": "601",
        "preview": "image",
        "task": completed,
        "cached_xml": [{"xml": media_xml}],
        "started_at": 0.0,
    }
    adapter.server.callback = AsyncMock(return_value=None)

    result = await adapter.server.handle_callback(_request_stub())

    assert result == media_xml
    assert "&lt;" not in result
