import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from requests import Response
from wechatpy.enterprise.messages import ImageMessage, TextMessage, VoiceMessage

os.environ.setdefault(
    "ASTRBOT_ROOT",
    tempfile.mkdtemp(prefix="astrbot-test-wecom-adapter-"),
)

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain, Record
from astrbot.api.platform import MessageType
from astrbot.core import db_helper
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.sources.wecom import wecom_adapter
from astrbot.core.platform.sources.wecom.wecom_adapter import (
    WecomPlatformAdapter,
    _extract_wecom_media_filename,
)


def _response(content: bytes, disposition: str | None = None) -> Response:
    resp = Response()
    resp._content = content
    if disposition:
        resp.headers["Content-Disposition"] = disposition
    return resp


def _adapter() -> WecomPlatformAdapter:
    adapter = WecomPlatformAdapter.__new__(WecomPlatformAdapter)
    adapter.config = {"id": "wecom-test"}
    adapter._event_queue = SimpleNamespace(put_nowait=MagicMock())
    adapter.client = SimpleNamespace(media=SimpleNamespace(download=MagicMock()))
    adapter.server = SimpleNamespace(
        handle_verify=AsyncMock(return_value="verified"),
        handle_callback=AsyncMock(return_value="handled"),
        shutdown_event=SimpleNamespace(set=MagicMock()),
        server=SimpleNamespace(shutdown=AsyncMock()),
    )
    adapter.agent_id = None
    adapter._wechat_kf_seen_text_messages = {}
    adapter.handle_msg = AsyncMock()
    return adapter


class FakeMediaResolver:
    calls: list[tuple[str, dict, dict]] = []
    result = "/tmp/wecom.wav"
    error: Exception | None = None

    def __init__(self, media_ref: str, **kwargs) -> None:
        self.media_ref = media_ref
        self.kwargs = kwargs

    async def to_path(self, **kwargs) -> str:
        FakeMediaResolver.calls.append((self.media_ref, self.kwargs, kwargs))
        if FakeMediaResolver.error:
            raise FakeMediaResolver.error
        return FakeMediaResolver.result


def _patch_media_resolver(monkeypatch, *, result: str = "/tmp/wecom.wav", error=None):
    FakeMediaResolver.calls = []
    FakeMediaResolver.result = result
    FakeMediaResolver.error = error
    monkeypatch.setattr(wecom_adapter, "MediaResolver", FakeMediaResolver)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _dispose_global_db_helper():
    yield
    await db_helper.engine.dispose()


def test_extract_wecom_media_filename_prefers_utf8_filename_star():
    disposition = (
        "attachment; filename=ignored.bin; "
        "filename*=UTF-8''..%2Fsafe%20name.txt"
    )

    assert _extract_wecom_media_filename(disposition) == "safe name.txt"


def test_extract_wecom_media_filename_uses_plain_filename_and_basename_only():
    disposition = 'attachment; filename="..\\\\nested\\\\report.pdf"'

    assert _extract_wecom_media_filename(disposition) == "report.pdf"


def test_extract_wecom_media_filename_returns_none_without_filename():
    assert _extract_wecom_media_filename("attachment") is None
    assert _extract_wecom_media_filename(None) is None


@pytest.mark.asyncio
async def test_wecom_send_by_session_rejects_kf_mode():
    adapter = _adapter()
    adapter.client.kf_message = object()

    with patch(
        "astrbot.core.platform.platform.Metric.upload",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(Exception, match="企业微信客服模式不支持 send_by_session"):
            await adapter.send_by_session(
                MessageSession(
                    platform_name="wecom",
                    message_type=MessageType.FRIEND_MESSAGE,
                    session_id="session-1",
                ),
                MessageChain([Plain("hello")]),
            )


@pytest.mark.asyncio
async def test_wecom_send_by_session_requires_agent_id():
    adapter = _adapter()

    with patch(
        "astrbot.core.platform.platform.Metric.upload",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(Exception, match="无法为会话 session-1 推断 agent_id"):
            await adapter.send_by_session(
                MessageSession(
                    platform_name="wecom",
                    message_type=MessageType.FRIEND_MESSAGE,
                    session_id="session-1",
                ),
                MessageChain([Plain("hello")]),
            )


@pytest.mark.asyncio
async def test_wecom_send_by_session_creates_proactive_event(monkeypatch):
    adapter = _adapter()
    adapter.agent_id = "agent-1"
    send = AsyncMock()
    created = []

    def fake_create_event(message):
        created.append(message)
        return SimpleNamespace(send=send)

    monkeypatch.setattr(adapter, "create_event", fake_create_event)

    await adapter.send_by_session(
        MessageSession(
            platform_name="wecom",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="session-1",
        ),
        MessageChain([Plain("hello")]),
    )

    assert len(created) == 1
    proactive = created[0]
    assert proactive.self_id == "agent-1"
    assert proactive.session_id == "session-1"
    assert proactive.raw_message == {"_proactive_send": True}
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_webhook_callback_dispatches_by_method():
    adapter = _adapter()

    assert (
        await adapter.webhook_callback(SimpleNamespace(method="GET"))
        == "verified"
    )
    assert (
        await adapter.webhook_callback(SimpleNamespace(method="POST"))
        == "handled"
    )
    adapter.server.handle_verify.assert_awaited_once()
    adapter.server.handle_callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_wecom_convert_message_text_builds_friend_message():
    adapter = _adapter()
    msg = TextMessage(
        {
            "MsgType": "text",
            "Content": "hello",
            "AgentID": 7,
            "FromUserName": "user-1",
            "MsgId": 101,
            "CreateTime": 123,
        }
    )

    result = await adapter.convert_message(msg)

    assert result is None
    adapter.handle_msg.assert_awaited_once()
    abm = adapter.handle_msg.await_args.args[0]
    assert adapter.agent_id == "7"
    assert abm.type == MessageType.FRIEND_MESSAGE
    assert abm.session_id == "user-1"
    assert abm.message_str == "hello"
    assert [type(component) for component in abm.message] == [Plain]
    assert abm.message[0].text == "hello"


@pytest.mark.asyncio
async def test_wecom_convert_message_image_builds_image_component():
    adapter = _adapter()
    msg = ImageMessage(
        {
            "MsgType": "image",
            "PicUrl": "https://img.test/1",
            "AgentID": 8,
            "FromUserName": "user-2",
            "MsgId": 102,
            "CreateTime": 456,
        }
    )

    await adapter.convert_message(msg)

    abm = adapter.handle_msg.await_args.args[0]
    assert abm.message_str == "[图片]"
    assert [type(component) for component in abm.message] == [Image]
    assert abm.message[0].url == "https://img.test/1"


@pytest.mark.asyncio
async def test_wecom_convert_message_voice_uses_media_resolver(monkeypatch, tmp_path):
    adapter = _adapter()
    adapter.client.media.download.return_value = _response(b"amr-bytes")
    _patch_media_resolver(monkeypatch, result="/tmp/wecom-converted.wav")
    monkeypatch.setattr(
        wecom_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    msg = VoiceMessage(
        {
            "MsgType": "voice",
            "MediaId": "media-1",
            "AgentID": 9,
            "FromUserName": "user-3",
            "MsgId": 103,
            "CreateTime": 789,
        }
    )

    await adapter.convert_message(msg)

    assert (tmp_path / "wecom_media-1.amr").read_bytes() == b"amr-bytes"
    assert FakeMediaResolver.calls == [
        (
            str(tmp_path / "wecom_media-1.amr"),
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]
    abm = adapter.handle_msg.await_args.args[0]
    assert [type(component) for component in abm.message] == [Record]
    assert abm.message[0].file == "/tmp/wecom-converted.wav"


@pytest.mark.asyncio
async def test_wecom_convert_message_voice_stops_on_media_resolver_failure(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download.return_value = _response(b"amr-bytes")
    _patch_media_resolver(monkeypatch, error=RuntimeError("ffmpeg missing"))
    monkeypatch.setattr(
        wecom_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    msg = VoiceMessage(
        {
            "MsgType": "voice",
            "MediaId": "media-2",
            "AgentID": 9,
            "FromUserName": "user-4",
            "MsgId": 104,
            "CreateTime": 790,
        }
    )

    result = await adapter.convert_message(msg)

    assert result is None
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_wecom_convert_message_unknown_type_returns_none():
    adapter = _adapter()
    msg = SimpleNamespace(type="location")

    result = await adapter.convert_message(msg)

    assert result is None
    adapter.handle_msg.assert_not_awaited()


def test_wecom_kf_text_dedup_expires_after_ttl():
    adapter = _adapter()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(wecom_adapter.time, "monotonic", lambda: 100.0)
        assert (
            adapter._is_duplicate_wechat_kf_text_message("user-1", " hello ")
            is False
        )
        assert (
            adapter._is_duplicate_wechat_kf_text_message("user-1", "hello")
            is True
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            wecom_adapter.time,
            "monotonic",
            lambda: 100.0
            + adapter.WECHAT_KF_TEXT_CONTENT_DEDUP_TTL_SECONDS
            + 1,
        )
        assert (
            adapter._is_duplicate_wechat_kf_text_message("user-1", "hello")
            is False
        )


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_deduplicates_text():
    adapter = _adapter()
    adapter._is_duplicate_wechat_kf_text_message = MagicMock(return_value=True)

    result = await adapter.convert_wechat_kf_message(
        {
            "msgtype": "text",
            "open_kfid": "kf-1",
            "external_userid": "user-1",
            "text": {"content": " hello "},
        }
    )

    assert result is None
    adapter.handle_msg.assert_not_awaited()
    adapter._is_duplicate_wechat_kf_text_message.assert_called_once_with(
        "user-1", "hello"
    )


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_voice_uses_media_resolver(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download.return_value = _response(b"amr-bytes")
    _patch_media_resolver(monkeypatch, result="/tmp/weixinkefu-converted.wav")
    monkeypatch.setattr(
        wecom_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    await adapter.convert_wechat_kf_message(
        {
            "msgtype": "voice",
            "open_kfid": "kf-1",
            "external_userid": "user-voice",
            "voice": {"media_id": "voice-1"},
        }
    )

    assert (tmp_path / "weixinkefu_voice-1.amr").read_bytes() == b"amr-bytes"
    assert FakeMediaResolver.calls == [
        (
            str(tmp_path / "weixinkefu_voice-1.amr"),
            {"media_type": "audio", "default_suffix": ".wav"},
            {"target_format": "wav"},
        )
    ]
    abm = adapter.handle_msg.await_args.args[0]
    assert [type(component) for component in abm.message] == [Record]
    assert abm.message[0].file == "/tmp/weixinkefu-converted.wav"


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_voice_returns_none_on_convert_failure(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download.return_value = _response(b"amr-bytes")
    _patch_media_resolver(monkeypatch, error=RuntimeError("ffmpeg missing"))
    monkeypatch.setattr(
        wecom_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    result = await adapter.convert_wechat_kf_message(
        {
            "msgtype": "voice",
            "open_kfid": "kf-1",
            "external_userid": "user-voice",
            "voice": {"media_id": "voice-2"},
        }
    )

    assert result is None
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_image_uses_detected_suffix(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download.return_value = _response(b"img-bytes")
    monkeypatch.setattr(
        wecom_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        wecom_adapter,
        "detect_image_mime_type_async",
        AsyncMock(return_value="image/png"),
    )

    await adapter.convert_wechat_kf_message(
        {
            "msgtype": "image",
            "open_kfid": "kf-1",
            "external_userid": "user-2",
            "image": {"media_id": "img-1"},
        }
    )

    abm = adapter.handle_msg.await_args.args[0]
    assert [type(component) for component in abm.message] == [Image]
    image_path = Path(abm.message[0].file)
    assert image_path.name == "weixinkefu_img-1.png"
    assert image_path.read_bytes() == b"img-bytes"


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_file_uses_content_disposition_filename(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download.return_value = _response(
        b"file-bytes",
        "attachment; filename*=UTF-8''..%2Freport.txt",
    )
    monkeypatch.setattr(
        wecom_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(wecom_adapter.uuid, "uuid4", lambda: SimpleNamespace(hex="fixed"))

    await adapter.convert_wechat_kf_message(
        {
            "msgtype": "file",
            "open_kfid": "kf-1",
            "external_userid": "user-3",
            "file": {"media_id": "file-1"},
        }
    )

    abm = adapter.handle_msg.await_args.args[0]
    assert [type(component) for component in abm.message] == [File]
    file_component = abm.message[0]
    assert file_component.name == "report.txt"
    assert Path(file_component.file).name == "weixinkefu_fixed_report.txt"
    assert Path(file_component.file).read_bytes() == b"file-bytes"


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_file_without_media_id_returns_none():
    adapter = _adapter()

    result = await adapter.convert_wechat_kf_message(
        {
            "msgtype": "file",
            "open_kfid": "kf-1",
            "external_userid": "user-4",
            "file": {},
        }
    )

    assert result is None
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_wecom_convert_wechat_kf_message_unknown_type_returns_none():
    adapter = _adapter()

    result = await adapter.convert_wechat_kf_message(
        {
            "msgtype": "video_call",
            "open_kfid": "kf-1",
            "external_userid": "user-5",
        }
    )

    assert result is None
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_wecom_terminate_swallows_shutdown_errors():
    adapter = _adapter()
    adapter.server.server.shutdown = AsyncMock(side_effect=RuntimeError("boom"))

    await adapter.terminate()

    adapter.server.shutdown_event.set.assert_called_once()
    adapter.server.server.shutdown.assert_awaited_once()
