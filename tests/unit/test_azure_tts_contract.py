"""Offline lifecycle and error-boundary contracts for Azure TTS."""

import asyncio
import logging
import time
from pathlib import Path

import pytest

from astrbot.core.provider.sources import azure_tts_source
from astrbot.core.provider.sources.azure_tts_source import (
    AzureNativeProvider,
    AzureTTSProvider,
    OTTSProvider,
)

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=azure-api-key "
    "Bearer azure-bearer-token "
    "password=azure-password "
    "https://internal.example/tts "
    "C:\\private\\tts.wav "
    "/srv/astrbot/tts.wav"
)
_SENSITIVE_VALUES = (
    "azure-api-key",
    "azure-bearer-token",
    "azure-password",
    "https://internal.example/tts",
    "C:\\private\\tts.wav",
    "/srv/astrbot/tts.wav",
)
_TTS_ERROR = "Azure TTS audio generation failed"


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        rendered = str(text)
        for value in _SENSITIVE_VALUES:
            assert value not in rendered


class _Response:
    def __init__(
        self,
        *,
        async_chunks: list[object] | None = None,
        sync_chunks: list[object] | None = None,
        stream_error: BaseException | None = None,
        status_error: BaseException | None = None,
    ) -> None:
        self.async_chunks = async_chunks or []
        self.sync_chunks = sync_chunks or []
        self.stream_error = stream_error
        self.status_error = status_error
        self.text = "token"

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error

    async def aiter_bytes(self, _chunk_size: int):
        for chunk in self.async_chunks:
            yield chunk
        if self.stream_error is not None:
            raise self.stream_error

    def iter_bytes(self, _chunk_size: int):
        yield from self.sync_chunks
        if self.stream_error is not None:
            raise self.stream_error


class _Client:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response
        self.closed = False
        self.close_error: BaseException | None = None
        self.post_calls: list[tuple[str, dict[str, object]]] = []

    async def post(self, url: str, **kwargs: object) -> _Response:
        self.post_calls.append((url, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _otts_provider(client: _Client) -> OTTSProvider:
    provider = OTTSProvider(
        {
            "OTTS_SKEY": "otts-signing-key",
            "OTTS_URL": "https://tts.example.test/speech",
            "OTTS_AUTH_TIME": "https://tts.example.test/time",
        }
    )
    provider._client = client
    provider.retry_count = 1
    return provider


def _native_provider(client: _Client) -> AzureNativeProvider:
    provider = AzureNativeProvider.__new__(AzureNativeProvider)
    provider.request_headers = {}
    provider._client = client
    provider.token = "token"
    provider.token_expire = time.time() + 60
    provider.endpoint = "https://tts.example.test/speech"
    provider.voice_params = {
        "voice": "zh-CN-TestNeural",
        "style": "cheerful",
        "role": "Boy",
        "rate": "1",
        "volume": "100",
    }
    return provider


@pytest.mark.asyncio
async def test_otts_failure_is_generic_redacted_and_removes_partial_audio(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    client = _Client(
        _Response(
            async_chunks=[b"partial"], stream_error=RuntimeError(_SENSITIVE_ERROR)
        )
    )
    provider = _otts_provider(client)
    provider._generate_signature = lambda: _completed("signature")
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_TTS_ERROR) as caught:
            await provider.get_audio("hello", _voice_params())

    _assert_no_sensitive_values(caught.value, caplog.text)
    assert not list(tmp_path.glob("otts-*.wav"))


@pytest.mark.asyncio
async def test_otts_cancellation_removes_partial_audio(
    monkeypatch, tmp_path: Path
) -> None:
    client = _Client(
        _Response(async_chunks=[b"partial"], stream_error=asyncio.CancelledError())
    )
    provider = _otts_provider(client)
    provider._generate_signature = lambda: _completed("signature")
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    with pytest.raises(asyncio.CancelledError):
        await provider.get_audio("hello", _voice_params())

    assert not list(tmp_path.glob("otts-*.wav"))


@pytest.mark.asyncio
async def test_otts_rejects_empty_audio_stream(monkeypatch, tmp_path: Path) -> None:
    provider = _otts_provider(_Client(_Response()))
    provider._generate_signature = lambda: _completed("signature")
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    with pytest.raises(RuntimeError, match=_TTS_ERROR):
        await provider.get_audio("hello", _voice_params())

    assert not list(tmp_path.glob("otts-*.wav"))


@pytest.mark.asyncio
async def test_native_failure_is_generic_redacted_and_removes_partial_audio(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    provider = _native_provider(
        _Client(
            _Response(
                sync_chunks=[b"partial"], stream_error=RuntimeError(_SENSITIVE_ERROR)
            )
        )
    )
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_TTS_ERROR) as caught:
            await provider.get_audio("hello")

    _assert_no_sensitive_values(caught.value, caplog.text)
    assert not list(tmp_path.glob("azure-*.wav"))


@pytest.mark.asyncio
async def test_native_token_failure_is_generic_redacted_and_leaves_no_audio(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    provider = _native_provider(_Client(RuntimeError(_SENSITIVE_ERROR)))
    provider.token = None
    provider.token_expire = 0
    provider.region = "eastus"
    provider.subscription_key = "a" * 32
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_TTS_ERROR) as caught:
            await provider.get_audio("hello")

    _assert_no_sensitive_values(caught.value, caplog.text)
    assert not list(tmp_path.glob("azure-*.wav"))


@pytest.mark.asyncio
async def test_native_cancellation_removes_partial_audio(
    monkeypatch, tmp_path: Path
) -> None:
    provider = _native_provider(
        _Client(
            _Response(sync_chunks=[b"partial"], stream_error=asyncio.CancelledError())
        )
    )
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    with pytest.raises(asyncio.CancelledError):
        await provider.get_audio("hello")

    assert not list(tmp_path.glob("azure-*.wav"))


@pytest.mark.asyncio
async def test_native_tts_writes_nonempty_audio_and_cleans_test_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = _native_provider(_Client(_Response(sync_chunks=[b"RIFF", b"data"])))
    monkeypatch.setattr(azure_tts_source, "TEMP_DIR", tmp_path)

    path = Path(await provider.get_audio("hello"))
    try:
        assert path.read_bytes() == b"RIFFdata"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [_otts_provider, _native_provider])
async def test_context_exit_sanitizes_close_failure_and_drops_client(
    factory,
    caplog,
) -> None:
    client = _Client(_Response())
    client.close_error = RuntimeError(_SENSITIVE_ERROR)
    provider = factory(client)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.__aexit__(None, None, None)

    assert client.closed is True
    assert provider._client is None
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_top_level_terminate_closes_active_provider_client() -> None:
    client = _Client(_Response())
    provider = AzureTTSProvider.__new__(AzureTTSProvider)
    provider.provider = _otts_provider(client)

    await provider.terminate()

    assert client.closed is True
    assert provider.provider._client is None


@pytest.mark.asyncio
@pytest.mark.parametrize("factory", [_otts_provider, _native_provider])
async def test_context_exit_propagates_cancellation_after_dropping_client(
    factory,
) -> None:
    client = _Client(_Response())
    client.close_error = asyncio.CancelledError()
    provider = factory(client)

    with pytest.raises(asyncio.CancelledError):
        await provider.__aexit__(None, None, None)

    assert client.closed is True
    assert provider._client is None


@pytest.mark.parametrize("provider_kind", ["otts", "native"])
def test_provider_constructors_do_not_log_proxy_contents(
    caplog,
    provider_kind: str,
) -> None:
    config = {
        "OTTS_SKEY": "otts-signing-key",
        "OTTS_URL": "https://tts.example.test/speech",
        "OTTS_AUTH_TIME": "https://tts.example.test/time",
        "proxy": _SENSITIVE_ERROR,
    }
    if provider_kind == "native":
        config = {
            "azure_tts_subscription_key": "a" * 32,
            "proxy": _SENSITIVE_ERROR,
        }

    with caplog.at_level(logging.INFO, logger="astrbot"):
        if provider_kind == "otts":
            OTTSProvider(config)
        else:
            AzureNativeProvider(config, {})

    _assert_no_sensitive_values(caplog.text)


def test_other_config_parse_error_does_not_echo_sensitive_context() -> None:
    provider = AzureTTSProvider.__new__(AzureTTSProvider)
    provider.provider_settings = {}

    with pytest.raises(ValueError) as caught:
        provider._parse_provider(f'other[{{"token": "{_SENSITIVE_ERROR}"]', {})

    assert "JSON" in str(caught.value)
    _assert_no_sensitive_values(caught.value)


def _voice_params() -> dict[str, str]:
    return {
        "voice": "zh-CN-TestNeural",
        "style": "cheerful",
        "role": "Boy",
        "rate": "1",
        "volume": "100",
    }


async def _completed(value: str) -> str:
    return value
