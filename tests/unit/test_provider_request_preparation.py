"""Tests for copy-on-write provider request preparation."""

import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.llm_types import LLMResponse, ProviderRequest
from astrbot.core.agent.request_preparation import prepare_provider_request
from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.provider.provider import Provider


class _SDKProvider(Provider):
    def __init__(self) -> None:
        super().__init__({"id": "sdk", "modalities": ["text"]}, {})
        self.request_kwargs: dict = {}

    def get_current_key(self) -> str:
        return ""

    def set_key(self, key: str) -> None:
        del key

    async def get_models(self) -> list[str]:
        return []

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.request_kwargs = kwargs
        return LLMResponse(role="assistant", completion_text="prepared")


@pytest.mark.asyncio
async def test_prepare_provider_request_does_not_mutate_and_rejects_remote_media():
    data_image = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ"
        "/pLvAAAAAElFTkSuQmCC"
    )
    request = ProviderRequest(
        prompt="describe",
        image_urls=[data_image, "http://127.0.0.1/private.png"],
        contexts=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_image},
                    }
                ],
            }
        ],
    )

    prepared = await prepare_provider_request(request)

    assert request.image_urls == [data_image, "http://127.0.0.1/private.png"]
    assert len(prepared.image_urls) == 1
    assert prepared.image_urls[0].startswith("data:image/jpeg;base64,")
    assert "data:image" not in str(prepared.contexts)
    assert any(
        "image omitted" in part.text for part in prepared.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_prepare_provider_request_downgrades_unsupported_media_without_hooks():
    provider = MagicMock()
    provider.provider_config = {"modalities": ["text"]}
    request = ProviderRequest(image_urls=["base64://aGVsbG8="])

    prepared = await prepare_provider_request(request, provider=provider)

    assert prepared.image_urls == []
    assert any(
        "image omitted" in part.text for part in prepared.extra_user_content_parts
    )
    assert request.extra_user_content_parts == []


@pytest.mark.asyncio
async def test_sdk_llm_generate_uses_shared_preparation_without_global_hook():
    provider = _SDKProvider()
    context = CoreExecutionContext.__new__(CoreExecutionContext)
    context.provider_manager = SimpleNamespace(
        get_provider_by_id=AsyncMock(return_value=provider),
    )
    data_image = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
        "ScL9mQAAAABJRU5ErkJggg=="
    )

    response = await context.llm_generate(
        chat_provider_id="sdk",
        prompt="describe",
        image_urls=[data_image],
    )

    assert response.completion_text == "prepared"
    assert provider.request_kwargs["image_urls"] == []
    assert any(
        "image omitted" in part.text
        for part in provider.request_kwargs["extra_user_content_parts"]
    )
    assert not hasattr(context, "handlers")


def _gif_path(tmp_path, frames, duration) -> str:
    path = tmp_path / "source.gif"
    first, *rest = frames
    first.save(
        path,
        format="GIF",
        save_all=True,
        append_images=rest,
        duration=duration,
        loop=0,
        disposal=2,
    )
    return str(path)


@pytest.mark.asyncio
async def test_prepare_provider_request_converts_one_by_one_png_to_jpeg():
    from PIL import Image as PILImage

    buffer = BytesIO()
    PILImage.new("RGB", (1, 1), (12, 34, 56)).save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    request = ProviderRequest(prompt="look", image_urls=[data_url])

    prepared = await prepare_provider_request(request)

    assert len(prepared.image_urls) == 1
    assert prepared.image_urls[0].startswith("data:image/jpeg;base64,")
    jpeg_bytes = base64.b64decode(prepared.image_urls[0].split(",", 1)[1])
    with PILImage.open(BytesIO(jpeg_bytes)) as jpeg:
        assert jpeg.format == "JPEG"
        assert jpeg.size == (1, 1)


@pytest.mark.asyncio
async def test_prepare_provider_request_samples_three_scene_gif(tmp_path, monkeypatch):
    from PIL import Image as PILImage

    import astrbot.core.utils.media_utils as media_utils

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    gif = _gif_path(
        tmp_path,
        [
            PILImage.new("RGB", (32, 32), (220, 0, 0)),
            PILImage.new("RGB", (32, 32), (0, 220, 0)),
            PILImage.new("RGB", (32, 32), (0, 0, 220)),
        ],
        1000,
    )
    request = ProviderRequest(prompt="look", image_urls=[gif])

    prepared = await prepare_provider_request(request)

    assert 2 <= len(prepared.image_urls) <= 8
    assert all(url.startswith("data:image/jpeg;base64,") for url in prepared.image_urls)
    assert any(
        "Animated image:" in part.text and "sampled frames" in part.text
        for part in prepared.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_prepare_provider_request_drops_mp4_named_gif(tmp_path, monkeypatch):
    import astrbot.core.utils.media_utils as media_utils

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    fake_gif = tmp_path / "video.gif"
    fake_gif.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    request = ProviderRequest(prompt="look", image_urls=[str(fake_gif)])

    prepared = await prepare_provider_request(request)

    assert prepared.image_urls == []
    assert any(
        "image omitted during provider preparation" in part.text
        for part in prepared.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_prepare_provider_request_skips_jpeg_for_text_modalities(tmp_path):
    from PIL import Image as PILImage

    image_path = tmp_path / "pic.png"
    PILImage.new("RGB", (8, 8), (1, 2, 3)).save(image_path)
    provider = MagicMock()
    provider.provider_config = {"modalities": ["text"]}
    request = ProviderRequest(prompt="look", image_urls=[str(image_path)])

    prepared = await prepare_provider_request(request, provider=provider)

    assert prepared.image_urls == []
    assert not any(url.startswith("data:image/jpeg") for url in prepared.image_urls)
    assert any(
        "image omitted" in part.text for part in prepared.extra_user_content_parts
    )


@pytest.mark.asyncio
async def test_prepare_provider_request_gif_becomes_jpeg_when_compress_off(
    tmp_path, monkeypatch
):
    from PIL import Image as PILImage

    import astrbot.core.utils.media_utils as media_utils

    monkeypatch.setattr(
        media_utils, "get_astrbot_temp_path", lambda: str(tmp_path / "t")
    )
    gif = _gif_path(
        tmp_path,
        [PILImage.new("RGB", (8, 8), (10, 10, 200)) for _ in range(2)],
        100,
    )
    request = ProviderRequest(prompt="look", image_urls=[gif])

    prepared = await prepare_provider_request(request)

    assert prepared.image_urls
    assert all(url.startswith("data:image/jpeg;base64,") for url in prepared.image_urls)
    assert not any("data:image/gif" in url for url in prepared.image_urls)
