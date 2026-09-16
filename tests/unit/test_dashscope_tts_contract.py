"""Offline error, logging, and cleanup contracts for Dashscope TTS."""

import asyncio
import builtins
import logging
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest

from astrbot.core.provider.sources import dashscope_tts
from astrbot.core.provider.sources.dashscope_tts import ProviderDashscopeTTSAPI

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=dashscope-api-key "
    "Bearer dashscope-bearer "
    "password=dashscope-password "
    "https://internal.example/dashscope "
    "C:\\private\\dashscope.txt "
    "/srv/astrbot/dashscope.json"
)
_SENSITIVE_VALUES = (
    "dashscope-api-key",
    "dashscope-bearer",
    "dashscope-password",
    "https://internal.example/dashscope",
    "C:\\private\\dashscope.txt",
    "/srv/astrbot/dashscope.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        for value in _SENSITIVE_VALUES:
            assert value not in str(text)


def _provider(model: str = "qwen3-tts-flash") -> ProviderDashscopeTTSAPI:
    provider = ProviderDashscopeTTSAPI.__new__(ProviderDashscopeTTSAPI)
    provider.request_headers = {"User-Agent": "astrbot/test"}
    provider.model_name = model
    provider.voice = "test-voice"
    provider.chosen_api_key = "test-key"
    provider.timeout_ms = 1_000
    return provider


@pytest.mark.asyncio
async def test_dashscope_tts_hides_qwen_sdk_error_from_logs_and_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    provider = _provider()
    monkeypatch.setattr(dashscope_tts, "get_astrbot_temp_path", lambda: str(tmp_path))

    def _raise(*_args: object) -> object:
        raise RuntimeError(_SENSITIVE_ERROR)

    monkeypatch.setattr(provider, "_call_qwen_tts", _raise)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            RuntimeError, match="Dashscope TTS audio generation failed"
        ) as caught:
            await provider.get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)
    assert list(tmp_path.glob("*")) == []


@pytest.mark.asyncio
async def test_dashscope_tts_hides_qwen_malformed_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    provider = _provider()
    monkeypatch.setattr(dashscope_tts, "get_astrbot_temp_path", lambda: str(tmp_path))

    class _Response:
        output = SimpleNamespace(audio=None)

        def __str__(self) -> str:
            return _SENSITIVE_ERROR

    response = _Response()
    monkeypatch.setattr(provider, "_call_qwen_tts", lambda *_args: response)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            RuntimeError, match="Dashscope TTS audio generation failed"
        ) as caught:
            await provider.get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_dashscope_tts_hides_cosyvoice_error_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    provider = _provider("cosyvoice-v1")
    monkeypatch.setattr(dashscope_tts, "get_astrbot_temp_path", lambda: str(tmp_path))

    class _Synthesizer:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def call(self, *_args: object) -> None:
            return None

        def get_response(self) -> dict[str, str]:
            return {"detail": _SENSITIVE_ERROR}

    monkeypatch.setattr(dashscope_tts, "SpeechSynthesizer", _Synthesizer)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            RuntimeError, match="Dashscope TTS audio generation failed"
        ) as caught:
            await provider.get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_dashscope_tts_sanitizes_download_failure(caplog, monkeypatch) -> None:
    provider = _provider()

    class _Request:
        async def __aenter__(self) -> object:
            raise aiohttp.ClientError(_SENSITIVE_ERROR)

        async def __aexit__(self, *_args: object) -> None:
            return None

    class _Session:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def get(self, *_args: object, **_kwargs: object) -> _Request:
            return _Request()

    monkeypatch.setattr(dashscope_tts.aiohttp, "ClientSession", _Session)

    with caplog.at_level(logging.ERROR):
        assert await provider._download_audio_from_url(_SENSITIVE_ERROR) is None

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_dashscope_tts_cancellation_cleans_partial_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = _provider()
    monkeypatch.setattr(dashscope_tts, "get_astrbot_temp_path", lambda: str(tmp_path))

    async def _synthesize(*_args: object) -> tuple[bytes, str]:
        return b"audio", ".wav"

    monkeypatch.setattr(provider, "_synthesize_with_qwen_tts", _synthesize)

    class _Writer:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> _Writer:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def write(self, _data: bytes) -> None:
            self.path.write_bytes(b"partial")
            raise asyncio.CancelledError()

    monkeypatch.setattr(
        builtins,
        "open",
        lambda path, *_args, **_kwargs: _Writer(Path(path)),
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.get_audio("text")

    assert list(tmp_path.glob("*")) == []
