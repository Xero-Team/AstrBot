import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import Image, Record
from astrbot.core.platform.sources.weixin_oc import weixin_oc_adapter
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter

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


def _make_adapter() -> WeixinOCAdapter:
    return WeixinOCAdapter({"id": "weixin-oc-test"}, {}, asyncio.Queue())


def _patch_media_resolver(monkeypatch) -> None:
    FakeMediaResolver.calls = []
    monkeypatch.setattr(weixin_oc_adapter, "MediaResolver", FakeMediaResolver)


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
