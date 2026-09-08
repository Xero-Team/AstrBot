import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import Image, Plain, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.weixin_oc import weixin_oc_adapter
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter
from astrbot.core.platform.sources.weixin_oc.weixin_oc_text import (
    TOOL_CALL_RESULT_TYPE,
    TOOL_CALL_START_TYPE,
)

pytestmark = pytest.mark.platform


WAV_PATH = "/tmp/astrbot-weixin-oc.wav"


class FakeMediaResolver:
    calls = []

    def __init__(self, media_ref: str, **kwargs) -> None:
        self.media_ref = media_ref
        self.kwargs = kwargs
        self.calls.append((media_ref, kwargs))

    async def to_path(self, **kwargs) -> str:
        self.calls[-1] = (*self.calls[-1], kwargs)
        return WAV_PATH


class RuntimeConfig(dict):
    def __init__(self, platform_config: dict, *, committed: bool) -> None:
        super().__init__(platform=[platform_config])
        self.save_config_async = AsyncMock(return_value=committed)


def _make_adapter(config: dict | None = None) -> WeixinOCAdapter:
    return WeixinOCAdapter(config or {"id": "weixin-oc-test"}, {}, asyncio.Queue())


def _patch_media_resolver(monkeypatch) -> None:
    FakeMediaResolver.calls = []
    monkeypatch.setattr(weixin_oc_adapter, "MediaResolver", FakeMediaResolver)


def _account_state(
    *,
    token: str,
    account_id: str,
    sync_buf: str,
    base_url: str,
    context_tokens: dict[str, str],
) -> dict[str, object]:
    return {
        "weixin_oc_token": token,
        "weixin_oc_account_id": account_id,
        "weixin_oc_sync_buf": sync_buf,
        "weixin_oc_base_url": base_url,
        "weixin_oc_context_tokens": context_tokens,
    }


@pytest.mark.asyncio
async def test_save_account_state_restores_persisted_state_when_superseded():
    persisted_state = _account_state(
        token="persisted-token",
        account_id="persisted-account",
        sync_buf="persisted-sync",
        base_url="https://persisted.example",
        context_tokens={"persisted-user": "persisted-context"},
    )
    platform_config = {
        "id": "weixin-oc-test",
        "type": "weixin_oc",
        **persisted_state,
    }
    adapter = _make_adapter(platform_config)
    runtime_config = RuntimeConfig(platform_config, committed=False)
    adapter.runtime_config = runtime_config

    adapter.token = "candidate-token"
    adapter.account_id = "candidate-account"
    adapter._sync_buf = "candidate-sync"
    adapter.base_url = "https://candidate.example"
    adapter._context_tokens = {"candidate-user": "candidate-context"}
    adapter._context_tokens_dirty = True
    adapter._context_tokens_revision = 1

    await adapter._save_account_state()

    runtime_config.save_config_async.assert_awaited_once()
    assert {key: platform_config[key] for key in persisted_state} == persisted_state
    assert adapter.token == "persisted-token"
    assert adapter.account_id == "persisted-account"
    assert adapter._sync_buf == "persisted-sync"
    assert adapter.base_url == "https://persisted.example"
    assert adapter._context_tokens == {"persisted-user": "persisted-context"}
    assert adapter._context_tokens_dirty is False
    assert adapter.client.token == "persisted-token"
    assert adapter.client.base_url == "https://persisted.example"


@pytest.mark.asyncio
async def test_save_account_state_keeps_newer_runtime_state_when_superseded():
    persisted_state = _account_state(
        token="persisted-token",
        account_id="persisted-account",
        sync_buf="persisted-sync",
        base_url="https://persisted.example",
        context_tokens={"persisted-user": "persisted-context"},
    )
    newer_state = _account_state(
        token="newer-token",
        account_id="newer-account",
        sync_buf="newer-sync",
        base_url="https://newer.example",
        context_tokens={"newer-user": "newer-context"},
    )
    platform_config = {
        "id": "weixin-oc-test",
        "type": "weixin_oc",
        **persisted_state,
    }
    adapter = _make_adapter(platform_config)
    runtime_config = RuntimeConfig(platform_config, committed=False)

    async def superseded_save() -> bool:
        platform_config.update(newer_state)
        return False

    runtime_config.save_config_async.side_effect = superseded_save
    adapter.runtime_config = runtime_config
    adapter.token = "candidate-token"
    adapter.account_id = "candidate-account"
    adapter._sync_buf = "candidate-sync"
    adapter.base_url = "https://candidate.example"
    adapter._context_tokens = {"candidate-user": "candidate-context"}

    await adapter._save_account_state()

    assert {key: platform_config[key] for key in newer_state} == newer_state
    assert adapter.token == "newer-token"
    assert adapter.account_id == "newer-account"
    assert adapter._sync_buf == "newer-sync"
    assert adapter.base_url == "https://newer.example"
    assert adapter._context_tokens == {"newer-user": "newer-context"}
    assert adapter.client.token == "newer-token"
    assert adapter.client.base_url == "https://newer.example"


@pytest.mark.asyncio
async def test_save_account_state_syncs_adapter_after_successful_commit():
    persisted_state = _account_state(
        token="persisted-token",
        account_id="persisted-account",
        sync_buf="persisted-sync",
        base_url="https://persisted.example",
        context_tokens={"persisted-user": "persisted-context"},
    )
    platform_config = {
        "id": "weixin-oc-test",
        "type": "weixin_oc",
        **persisted_state,
    }
    adapter = _make_adapter(platform_config)
    runtime_config = RuntimeConfig(platform_config, committed=True)
    adapter.runtime_config = runtime_config
    adapter.token = "candidate-token"
    adapter.account_id = "candidate-account"
    adapter._sync_buf = "candidate-sync"
    adapter.base_url = "https://candidate.example"
    adapter._context_tokens = {"candidate-user": "candidate-context"}
    adapter._context_tokens_dirty = True
    adapter._context_tokens_revision = 1

    await adapter._save_account_state()

    expected_state = _account_state(
        token="candidate-token",
        account_id="candidate-account",
        sync_buf="candidate-sync",
        base_url="https://candidate.example",
        context_tokens={"candidate-user": "candidate-context"},
    )
    runtime_config.save_config_async.assert_awaited_once()
    assert {key: platform_config[key] for key in expected_state} == expected_state
    assert adapter.token == "candidate-token"
    assert adapter.account_id == "candidate-account"
    assert adapter._sync_buf == "candidate-sync"
    assert adapter.base_url == "https://candidate.example"
    assert adapter._context_tokens == {"candidate-user": "candidate-context"}
    assert adapter._context_tokens_dirty is False
    assert adapter.client.token == "candidate-token"
    assert adapter.client.base_url == "https://candidate.example"


@pytest.mark.asyncio
async def test_handle_inbound_message_does_not_download_voice_during_ingress(
    monkeypatch,
):
    adapter = _make_adapter()
    adapter.client.download_and_decrypt_media = AsyncMock(return_value=b"voice")
    committed = []

    monkeypatch.setattr(adapter, "create_event", lambda message: message)
    monkeypatch.setattr(adapter, "commit_event", committed.append)
    monkeypatch.setattr(adapter, "_cache_recent_message", lambda *args, **kwargs: None)

    await adapter._handle_inbound_message(
        {
            "from_user_id": "user-1",
            "message_id": "msg-1",
            "create_time": 1,
            "item_list": [
                {
                    "type": adapter.VOICE_ITEM_TYPE,
                    "voice_item": {
                        "media": {
                            "encrypt_query_param": "enc-query",
                            "aes_key": "aes-key",
                        }
                    },
                }
            ],
        }
    )

    assert adapter.client.download_and_decrypt_media.await_count == 0
    assert len(committed) == 1
    assert isinstance(committed[0].message[0], Record)
    assert committed[0].message[0].file == ""
    assert getattr(committed[0], "temporary_file_paths", []) == []


@pytest.mark.asyncio
async def test_resolve_inbound_image_component_downloads_on_demand(
    monkeypatch,
    tmp_path: Path,
):
    adapter = _make_adapter()
    adapter.client.download_cdn_bytes = AsyncMock(return_value=b"image-bytes")
    adapter.client.download_and_decrypt_media = AsyncMock(return_value=b"image-bytes")
    saved_paths = []

    async def fake_detect_image_mime_type_async(content: bytes, default_mime_type=None):
        assert content == b"image-bytes"
        return "image/png"

    def fake_save_inbound_media(
        content: bytes,
        *,
        prefix: str,
        file_name: str,
        fallback_suffix: str,
    ) -> Path:
        path = tmp_path / f"{prefix}_{file_name}"
        path.write_bytes(content)
        saved_paths.append(path)
        return path

    monkeypatch.setattr(
        weixin_oc_adapter,
        "detect_image_mime_type_async",
        fake_detect_image_mime_type_async,
    )
    monkeypatch.setattr(adapter, "_save_inbound_media", fake_save_inbound_media)

    tracked_paths: list[str] = []
    image = await adapter._resolve_inbound_media_component(
        {
            "type": adapter.IMAGE_ITEM_TYPE,
            "image_item": {
                "media": {
                    "encrypt_query_param": "enc-query",
                }
            },
        },
        tracked_paths,
    )

    assert isinstance(image, Image)
    assert image.file == ""
    assert adapter.client.download_cdn_bytes.await_count == 0
    assert saved_paths == []

    await image._resolve_deferred_source()

    assert adapter.client.download_cdn_bytes.await_count == 1
    assert [str(path) for path in saved_paths] == tracked_paths
    assert image.file == str(saved_paths[0])
    assert image.path == str(saved_paths[0])


@pytest.mark.asyncio
async def test_resolve_inbound_voice_component_downloads_and_converts_on_demand(
    monkeypatch,
    tmp_path: Path,
):
    _patch_media_resolver(monkeypatch)
    adapter = _make_adapter()
    adapter.client.download_and_decrypt_media = AsyncMock(return_value=b"voice-bytes")
    saved_paths = []

    def fake_save_inbound_media(
        content: bytes,
        *,
        prefix: str,
        file_name: str,
        fallback_suffix: str,
    ) -> Path:
        path = tmp_path / f"{prefix}_{file_name}"
        path.write_bytes(content)
        saved_paths.append(path)
        return path

    monkeypatch.setattr(adapter, "_save_inbound_media", fake_save_inbound_media)

    tracked_paths: list[str] = []
    record = await adapter._resolve_inbound_media_component(
        {
            "type": adapter.VOICE_ITEM_TYPE,
            "voice_item": {
                "media": {
                    "encrypt_query_param": "enc-query",
                    "aes_key": "aes-key",
                }
            },
        },
        tracked_paths,
    )

    assert isinstance(record, Record)
    assert record.file == ""
    assert adapter.client.download_and_decrypt_media.await_count == 0
    assert FakeMediaResolver.calls == []

    await record._resolve_deferred_source()

    assert adapter.client.download_and_decrypt_media.await_count == 1
    assert FakeMediaResolver.calls == [
        (
            str(saved_paths[0]),
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]
    assert tracked_paths == [str(saved_paths[0]), WAV_PATH]
    assert record.file == WAV_PATH
    assert record.path == WAV_PATH


@pytest.mark.asyncio
async def test_build_reply_from_svr_id_uses_recent_cache():
    adapter = _make_adapter()
    adapter._cache_recent_message(
        "user-1",
        message_id="svr-99",
        sender_id="user-1",
        sender_nickname="user-1",
        timestamp=1,
        timestamp_ms=1000,
        components=[Plain("hello quoted")],
        message_str="hello quoted",
    )

    reply, metadata = await adapter._build_reply_component_from_ref(
        session_id="user-1",
        ref_msg={"svr_id": "svr-99"},
    )

    assert reply is not None
    assert metadata.is_reply is True
    assert metadata.quoted_text == "hello quoted"
    assert metadata.reply_to["strategy"] == "server-message-id"


@pytest.mark.asyncio
async def test_poll_inbound_updates_applies_server_long_poll_timeout():
    adapter = _make_adapter()
    adapter.token = "token"
    adapter.client.request_json = AsyncMock(
        return_value={
            "ret": 0,
            "msgs": [],
            "longpolling_timeout_ms": 42_000,
        }
    )

    await adapter._poll_inbound_updates()

    assert adapter.long_poll_timeout_ms == 42_000


@pytest.mark.asyncio
async def test_terminate_sends_notify_stop_after_start():
    adapter = _make_adapter()
    adapter.token = "token"
    adapter._notified_start = True
    adapter.client.notify_stop = AsyncMock(return_value={"ret": 0})
    adapter.client.notify_start = AsyncMock(return_value={"ret": 0})

    await adapter.terminate()

    adapter.client.notify_stop.assert_awaited_once()
    assert adapter._notified_start is False


@pytest.mark.asyncio
async def test_send_by_session_sends_record_as_voice():
    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    adapter._send_media_segment = AsyncMock(return_value=True)
    session = MessageSession(
        platform_name="weixin-oc-test",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="user-1",
    )

    await adapter.send_by_session(session, MessageChain([Record(file="voice.wav")]))

    adapter._send_media_segment.assert_awaited_once()
    sent_segment = adapter._send_media_segment.await_args.args[1]
    assert isinstance(sent_segment, Record)


@pytest.mark.asyncio
async def test_prepare_media_item_builds_voice_payload(tmp_path: Path):
    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    silk_path = tmp_path / "out.silk"
    silk_path.write_bytes(b"silk-bytes")
    adapter.client.request_json = AsyncMock(
        return_value={"upload_param": "param", "upload_full_url": "https://cdn/upload"}
    )
    adapter.client.upload_to_cdn = AsyncMock(return_value="enc-query")

    item = await adapter._prepare_media_item(
        "user-1",
        silk_path,
        adapter.VOICE_UPLOAD_TYPE,
        adapter.VOICE_ITEM_TYPE,
        "out.silk",
        playtime_ms=1500,
    )

    assert item["type"] == adapter.VOICE_ITEM_TYPE
    assert item["voice_item"]["encode_type"] == adapter.VOICE_ENCODE_SILK
    assert item["voice_item"]["sample_rate"] == adapter.VOICE_SAMPLE_RATE_HZ
    assert item["voice_item"]["playtime"] == 1500
    assert (
        adapter.client.request_json.await_args.kwargs["payload"]["media_type"]
        == adapter.VOICE_UPLOAD_TYPE
    )


@pytest.mark.asyncio
async def test_resolve_outbound_voice_encodes_silk(monkeypatch, tmp_path: Path):
    wav_path = tmp_path / "in.wav"
    wav_path.write_bytes(b"RIFF")
    adapter = _make_adapter()
    record = Record(file=str(wav_path))

    async def fake_convert_to_file_path(self: Record) -> str:
        return str(wav_path)

    async def fake_wav_to_tencent_silk(_wav: str, output_path: str) -> float:
        Path(output_path).write_bytes(b"silk")
        return 1.5

    monkeypatch.setattr(Record, "convert_to_file_path", fake_convert_to_file_path)
    monkeypatch.setattr(adapter, "_resolve_inbound_media_dir", lambda: tmp_path)
    monkeypatch.setattr(
        weixin_oc_adapter, "wav_to_tencent_silk", fake_wav_to_tencent_silk
    )

    resolved = await adapter._resolve_outbound_voice(record)

    assert resolved is not None
    silk_path, playtime_ms = resolved
    assert playtime_ms == 1500
    assert silk_path.read_bytes() == b"silk"


@pytest.mark.asyncio
async def test_send_to_session_chunks_long_text():
    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    adapter._context_tokens["user-1"] = "ctx"
    adapter._send_items_to_session = AsyncMock(return_value=True)
    text = "。".join(["块" * 2000, "尾" * 2000])

    sent = await adapter._send_to_session("user-1", text)

    assert sent is True
    assert adapter._send_items_to_session.await_count >= 2
    first_item = adapter._send_items_to_session.await_args_list[0].args[1][0]
    assert first_item["type"] == 1
    assert len(first_item["text_item"]["text"]) <= 4000


@pytest.mark.asyncio
async def test_send_by_session_sends_tool_call_start_item():
    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    adapter._context_tokens["user-1"] = "ctx"
    adapter._send_items_to_session = AsyncMock(return_value=True)
    session = MessageSession(
        platform_name="weixin-oc-test",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="user-1",
    )

    await adapter.send_by_session(
        session,
        MessageChain(type="tool_call").message("🔨 调用工具: search"),
    )

    item = adapter._send_items_to_session.await_args.args[1][0]
    assert item["type"] == TOOL_CALL_START_TYPE
    assert item["tool_call_start_item"]["tool_name"] == "search"


@pytest.mark.asyncio
async def test_send_by_session_sends_tool_call_result_item():
    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    adapter._context_tokens["user-1"] = "ctx"
    adapter._send_items_to_session = AsyncMock(return_value=True)
    session = MessageSession(
        platform_name="weixin-oc-test",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="user-1",
    )

    await adapter.send_by_session(
        session,
        MessageChain(type="tool_call").message(
            "🔨 调用工具: search\n📎 返回结果: done"
        ),
    )

    item = adapter._send_items_to_session.await_args.args[1][0]
    assert item["type"] == TOOL_CALL_RESULT_TYPE
    assert item["tool_call_result_item"]["status"] == "completed"


@pytest.mark.asyncio
async def test_inbound_poll_backs_off_after_consecutive_failures(monkeypatch):
    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(weixin_oc_adapter.asyncio, "sleep", fake_sleep)
    await adapter._backoff_inbound_failure()
    await adapter._backoff_inbound_failure()
    await adapter._backoff_inbound_failure()

    assert sleeps == [2, 2, 30]
    assert adapter._inbound_consecutive_failures == 0


@pytest.mark.asyncio
async def test_send_streaming_flushes_when_min_chars_reached():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember

    adapter = _make_adapter({"id": "weixin-oc-test", "weixin_oc_token": "token"})
    adapter._context_tokens["user-1"] = "ctx"
    adapter._send_items_to_session = AsyncMock(return_value=True)
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.session_id = "user-1"
    message.sender = MessageMember("user-1", "tester")
    message.message_str = "hi"
    message.message = []
    event = adapter.create_event(message)

    async def gen():
        yield MessageChain().message("a" * 120)
        yield MessageChain().message("b" * 120)

    await event.send_streaming(gen())

    assert adapter._send_items_to_session.await_count == 1
    sent_text = adapter._send_items_to_session.await_args.args[1][0]["text_item"][
        "text"
    ]
    assert sent_text == ("a" * 120) + ("b" * 120)


def test_weixin_oc_create_event_does_not_promote_roles():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember

    adapter = _make_adapter()
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.session_id = "user-1"
    message.sender = MessageMember("user-1", "tester")
    message.raw_message = {"role": "admin"}
    message.message_str = "hello"
    message.message = []
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"
