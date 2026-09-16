"""Offline error and cleanup contracts for the GSVI TTS adapter."""

import asyncio
import builtins
from pathlib import Path

import pytest

from astrbot.core.provider.sources import gsvi_tts_source
from astrbot.core.provider.sources.gsvi_tts_source import ProviderGSVITTS

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=gsvi-api-key "
    "Bearer gsvi-bearer "
    "password=gsvi-password "
    "https://internal.example/gsvi "
    "C:\\private\\gsvi.txt "
    "/srv/astrbot/gsvi.json"
)
_SENSITIVE_VALUES = (
    "gsvi-api-key",
    "gsvi-bearer",
    "gsvi-password",
    "https://internal.example/gsvi",
    "C:\\private\\gsvi.txt",
    "/srv/astrbot/gsvi.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        for value in _SENSITIVE_VALUES:
            assert value not in str(text)


class _Response:
    def __init__(
        self,
        status: int,
        *,
        json_data: object = None,
        body: bytes = b"",
    ) -> None:
        self.status = status
        self.json_data = json_data
        self.body = body

    async def json(self) -> object:
        return self.json_data

    async def text(self) -> str:
        return _SENSITIVE_ERROR

    async def read(self) -> bytes:
        return self.body


class _Request:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(
        self,
        post_response: _Response | BaseException,
        get_response: _Response | BaseException,
    ) -> None:
        self.post_response = post_response
        self.get_response = get_response

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def post(self, *_args: object, **_kwargs: object) -> _Request:
        return _Request(self.post_response)

    def get(self, *_args: object, **_kwargs: object) -> _Request:
        return _Request(self.get_response)


def _provider() -> ProviderGSVITTS:
    provider = ProviderGSVITTS.__new__(ProviderGSVITTS)
    provider.request_headers = {}
    provider.api_key = "test-key"
    provider.api_base = "https://gsvi.example.test"
    provider.version = "v4"
    provider.character = "test"
    provider.prompt_text_lang = "中文"
    provider.emotion = "默认"
    provider.text_lang = "中文"
    return provider


def _patch_session(
    monkeypatch: pytest.MonkeyPatch,
    post_response: _Response | BaseException,
    get_response: _Response | BaseException,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        gsvi_tts_source.aiohttp,
        "ClientSession",
        lambda **_kwargs: _Session(post_response, get_response),
    )
    monkeypatch.setattr(gsvi_tts_source, "get_astrbot_temp_path", lambda: str(tmp_path))


@pytest.mark.asyncio
async def test_gsvi_tts_hides_synthesis_http_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    _patch_session(monkeypatch, _Response(500), _Response(200), tmp_path)

    with pytest.raises(
        RuntimeError, match="GSVI TTS audio generation failed"
    ) as caught:
        await _provider().get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_gsvi_tts_hides_sensitive_service_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    _patch_session(
        monkeypatch,
        _Response(200, json_data={"msg": _SENSITIVE_ERROR, "audio_url": "ignored"}),
        _Response(200),
        tmp_path,
    )

    with pytest.raises(
        RuntimeError, match="GSVI TTS audio generation failed"
    ) as caught:
        await _provider().get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_gsvi_tts_rejects_malformed_synthesis_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_session(
        monkeypatch,
        _Response(200, json_data=_SENSITIVE_ERROR),
        _Response(200),
        tmp_path,
    )

    with pytest.raises(
        RuntimeError, match="GSVI TTS audio generation failed"
    ) as caught:
        await _provider().get_audio("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value)


@pytest.mark.asyncio
async def test_gsvi_tts_cancellation_cleans_partial_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_session(
        monkeypatch,
        _Response(200, json_data={"msg": "合成成功", "audio_url": "ignored"}),
        _Response(200, body=b"audio"),
        tmp_path,
    )

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
        await _provider().get_audio("text")

    assert list(tmp_path.glob("*.wav")) == []
