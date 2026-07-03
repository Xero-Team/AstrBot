from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Plain
from astrbot.api.platform import MessageType
from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter


def _adapter() -> LinePlatformAdapter:
    adapter = LinePlatformAdapter.__new__(LinePlatformAdapter)
    adapter.config = {"id": "line-test", "unified_webhook_mode": True}
    adapter.destination = "dest-bot"
    adapter.settings = {}
    adapter._event_id_timestamps = {}
    adapter.shutdown_event = MagicMock()
    adapter.line_api = SimpleNamespace(
        get_message_content=AsyncMock(),
        verify_signature=MagicMock(return_value=True),
        close=AsyncMock(),
    )
    return adapter


def test_line_parse_text_with_mentions_splits_user_mentions_and_plain_text():
    adapter = _adapter()

    components = adapter._parse_text_with_mentions(
        "Hello @Alice and @all",
        {
            "mentionees": [
                {"index": 6, "length": 6, "type": "user", "userId": "user-1"},
                {"index": 17, "length": 4, "type": "all"},
            ]
        },
    )

    assert [type(component) for component in components] == [Plain, At, Plain, Plain]
    assert components[0].text == "Hello "
    assert components[1].qq == "user-1"
    assert components[1].name == "Alice"
    assert components[2].text == " and "
    assert components[3].text == "@all"


@pytest.mark.asyncio
async def test_line_convert_message_maps_group_message_and_external_image():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "type": "message",
            "mode": "active",
            "timestamp": 1710000000123,
            "webhookEventId": "evt-1",
            "source": {
                "type": "group",
                "groupId": "group-1",
                "userId": "user-1",
            },
            "message": {
                "id": "msg-1",
                "type": "image",
                "contentProvider": {
                    "type": "external",
                    "originalContentUrl": "https://example.test/image.png",
                },
            },
        }
    )

    assert result is not None
    assert result.type == MessageType.GROUP_MESSAGE
    assert result.group.group_id == "group-1"
    assert result.session_id == "group-1"
    assert result.sender.user_id == "user-1"
    assert result.self_id == "dest-bot"
    assert result.timestamp == 1710000000
    assert result.message_str == "[image]"
    assert result.message[0].file == "https://example.test/image.png"


@pytest.mark.asyncio
async def test_line_convert_message_maps_room_without_user_to_group_sender_fallback():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "type": "message",
            "source": {
                "type": "room",
                "roomId": "room-1",
            },
            "message": {
                "id": "msg-room",
                "type": "text",
                "text": "hello room",
            },
        }
    )

    assert result is not None
    assert result.type == MessageType.GROUP_MESSAGE
    assert result.session_id == "room-1"
    assert result.sender.user_id == "room-1"
    assert result.message_str == "hello room"


@pytest.mark.asyncio
async def test_line_convert_message_unknown_source_becomes_other_message():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "type": "message",
            "source": {"type": "beacon"},
            "message": {"type": "sticker", "id": "msg-sticker"},
        }
    )

    assert result is not None
    assert result.type == MessageType.OTHER_MESSAGE
    assert result.session_id == "unknown"
    assert result.sender.user_id == "unknown"
    assert result.message_str == "[sticker]"


@pytest.mark.asyncio
async def test_line_convert_message_returns_none_for_non_message_or_standby_or_bad_shapes():
    adapter = _adapter()

    assert await adapter.convert_message({"type": "follow"}) is None
    assert (
        await adapter.convert_message(
            {
                "type": "message",
                "mode": "standby",
                "source": {"type": "user", "userId": "user-1"},
                "message": {"type": "text", "text": "ignored"},
            }
        )
        is None
    )
    assert (
        await adapter.convert_message(
            {
                "type": "message",
                "source": "bad-source",
                "message": {"type": "text", "text": "ignored"},
            }
        )
        is None
    )
    assert (
        await adapter.convert_message(
            {
                "type": "message",
                "source": {"type": "user", "userId": "user-1"},
                "message": "bad-message",
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_line_parse_message_components_file_falls_back_to_placeholder_when_download_fails():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(return_value=None)

    components = await adapter._parse_line_message_components(
        {"id": "file-1", "type": "file", "fileName": "report.pdf"}
    )

    assert len(components) == 1
    assert isinstance(components[0], Plain)
    assert components[0].text == "[file]"


@pytest.mark.asyncio
async def test_line_build_file_component_uses_downloaded_filename_when_available():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"file-bytes", "application/pdf", "invoice.pdf")
    )

    component = await adapter._build_file_component(
        "msg-file",
        {"id": "msg-file", "type": "file", "fileName": "fallback.bin"},
    )

    assert isinstance(component, File)
    assert component.name == "invoice.pdf"
    assert component.file.endswith(".bin")
    assert component.url == component.file


@pytest.mark.asyncio
async def test_line_send_by_session_pushes_built_messages(monkeypatch):
    adapter = _adapter()
    adapter.line_api.push_message = AsyncMock()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_event.LineMessageEvent.build_line_messages",
        AsyncMock(return_value=[{"type": "text", "text": "hello"}]),
    )
    with patch(
        "astrbot.core.platform.platform.Platform.send_by_session",
        AsyncMock(),
    ) as super_send:
        await adapter.send_by_session(
            SimpleNamespace(session_id="user-1", message_type=MessageType.FRIEND_MESSAGE),
            MessageChain([Plain("hello")]),
        )

    adapter.line_api.push_message.assert_awaited_once_with(
        "user-1",
        [{"type": "text", "text": "hello"}],
    )
    super_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_send_by_session_skips_push_for_empty_built_messages(monkeypatch):
    adapter = _adapter()
    adapter.line_api.push_message = AsyncMock()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_event.LineMessageEvent.build_line_messages",
        AsyncMock(return_value=[]),
    )
    with patch(
        "astrbot.core.platform.platform.Platform.send_by_session",
        AsyncMock(),
    ) as super_send:
        await adapter.send_by_session(
            SimpleNamespace(session_id="user-1", message_type=MessageType.FRIEND_MESSAGE),
            MessageChain(chain=[]),
        )

    adapter.line_api.push_message.assert_not_called()
    super_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_handle_webhook_event_skips_duplicates_and_non_message_events():
    adapter = _adapter()
    adapter.convert_message = AsyncMock(
        side_effect=[SimpleNamespace(message_id="msg-1"), None]
    )
    adapter.handle_msg = AsyncMock()

    await adapter.handle_webhook_event(
        {
            "destination": "new-destination",
            "events": [
                {"webhookEventId": "evt-1", "type": "message", "message": {}},
                {"webhookEventId": "evt-1", "type": "message", "message": {}},
                {"webhookEventId": "evt-2", "type": "follow"},
            ],
        }
    )

    assert adapter.destination == "new-destination"
    assert adapter.convert_message.await_count == 2
    adapter.handle_msg.assert_awaited_once()


@pytest.mark.asyncio
async def test_line_handle_webhook_event_ignores_non_list_events_and_bad_entries():
    adapter = _adapter()
    adapter.convert_message = AsyncMock(return_value=None)
    adapter.handle_msg = AsyncMock()

    await adapter.handle_webhook_event({"destination": "dest-1", "events": "bad"})
    await adapter.handle_webhook_event(
        {"events": ["bad-entry", {"webhookEventId": "evt-3", "type": "message"}]}
    )

    assert adapter.destination == "dest-1"
    adapter.convert_message.assert_awaited_once_with(
        {"webhookEventId": "evt-3", "type": "message"}
    )
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_webhook_callback_rejects_bad_signature_bad_body_and_non_dict_payload():
    adapter = _adapter()
    adapter.handle_webhook_event = AsyncMock()

    bad_signature_request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(),
        headers={"x-line-signature": "sig"},
    )
    adapter.line_api.verify_signature = MagicMock(return_value=False)
    assert await adapter.webhook_callback(bad_signature_request) == (
        "invalid signature",
        400,
    )

    bad_body_request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(side_effect=RuntimeError("bad json")),
        headers={"x-line-signature": "sig"},
    )
    adapter.line_api.verify_signature = MagicMock(return_value=True)
    assert await adapter.webhook_callback(bad_body_request) == ("bad request", 400)

    non_dict_request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(return_value=["bad"]),
        headers={"x-line-signature": "sig"},
    )
    assert await adapter.webhook_callback(non_dict_request) == ("bad request", 400)
    adapter.handle_webhook_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_webhook_callback_accepts_valid_payload():
    adapter = _adapter()
    adapter.handle_webhook_event = AsyncMock()

    request = SimpleNamespace(
        get_data=AsyncMock(return_value=b"body"),
        get_json=AsyncMock(return_value={"events": []}),
        headers={"x-line-signature": "sig"},
    )

    assert await adapter.webhook_callback(request) == ("ok", 200)
    adapter.line_api.verify_signature.assert_called_once_with(b"body", "sig")
    adapter.handle_webhook_event.assert_awaited_once_with({"events": []})


@pytest.mark.asyncio
async def test_line_build_audio_component_uses_external_url_with_media_resolver(monkeypatch):
    adapter = _adapter()

    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value="C:/tmp/converted.wav")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.MediaResolver",
        MagicMock(return_value=media_resolver),
    )

    component = await adapter._build_audio_component(
        "msg-audio",
        {
            "type": "audio",
            "contentProvider": {
                "type": "external",
                "originalContentUrl": "https://example.test/audio.m4a",
            },
        },
    )

    assert component is not None
    assert component.file == "C:/tmp/converted.wav"
    assert component.url == "C:/tmp/converted.wav"
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")
    adapter.line_api.get_message_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_line_build_audio_component_downloads_and_converts_content(monkeypatch, tmp_path):
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"audio-bytes", "audio/mp4", "voice.m4a")
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value="C:/tmp/voice.wav")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.MediaResolver",
        MagicMock(return_value=media_resolver),
    )

    component = await adapter._build_audio_component(
        "msg-audio",
        {"id": "msg-audio", "type": "audio"},
    )

    assert component is not None
    assert component.file == "C:/tmp/voice.wav"
    saved_files = list(tmp_path.glob("line_audio_msg-audio_*.m4a"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"audio-bytes"
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")


@pytest.mark.asyncio
async def test_line_build_video_component_returns_none_when_download_fails():
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(return_value=None)

    component = await adapter._build_video_component(
        "msg-video",
        {"id": "msg-video", "type": "video"},
    )

    assert component is None


@pytest.mark.asyncio
async def test_line_build_video_component_stores_downloaded_video(monkeypatch, tmp_path):
    adapter = _adapter()
    adapter.line_api.get_message_content = AsyncMock(
        return_value=(b"video-bytes", "video/mp4", "clip.mp4")
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    component = await adapter._build_video_component(
        "msg-video",
        {"id": "msg-video", "type": "video"},
    )

    assert component is not None
    assert component.file.endswith(".mp4")
    assert component.path == component.file
    saved_files = list(tmp_path.glob("line_video_msg-video_*.mp4"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"video-bytes"


def test_line_clean_expired_events_removes_only_old_entries(monkeypatch):
    adapter = _adapter()
    adapter._event_id_timestamps = {
        "expired": 100.0,
        "fresh": 1000.0,
    }
    monkeypatch.setattr("astrbot.core.platform.sources.line.line_adapter.time.time", lambda: 2000.1)

    adapter._clean_expired_events()

    assert adapter._event_id_timestamps == {"fresh": 1000.0}


def test_line_is_duplicate_event_reaccepts_event_after_expiration(monkeypatch):
    adapter = _adapter()
    current = {"value": 100.0}
    monkeypatch.setattr(
        "astrbot.core.platform.sources.line.line_adapter.time.time",
        lambda: current["value"],
    )

    assert adapter._is_duplicate_event("evt-1") is False
    assert adapter._is_duplicate_event("evt-1") is True

    current["value"] = 2001.0

    assert adapter._is_duplicate_event("evt-1") is False
