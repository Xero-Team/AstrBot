"""Offline resilience contracts for MiMo and Xinference STT adapters."""

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources import (
    mimo_stt_api_source,
    xinference_stt_provider,
)
from astrbot.core.provider.sources.mimo_api_common import MiMoAPIError
from astrbot.core.provider.sources.mimo_stt_api_source import ProviderMiMoSTTAPI
from astrbot.core.provider.sources.xinference_stt_provider import ProviderXinferenceSTT

_SENSITIVE_ERROR = (
    "api_key=api-key-top-secret "
    "Bearer bearer-secret-token "
    "password=dashboard-password "
    "https://internal.example/private/config "
    "C:\\private\\config\\secret.txt "
    "/srv/astrbot/private/config.json"
)
_SENSITIVE_VALUES = (
    "api-key-top-secret",
    "bearer-secret-token",
    "dashboard-password",
    "internal.example",
    "C:\\private\\config\\secret.txt",
    "/srv/astrbot/private/config.json",
)


class _MiMoResponse:
    def __init__(self, *, status_error: BaseException | None = None, data=None) -> None:
        self.status_error = status_error
        self.data = data
        self.status_code = 502
        self.text = _SENSITIVE_ERROR

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        return self.data


def _mimo_provider(response: _MiMoResponse) -> ProviderMiMoSTTAPI:
    provider = ProviderMiMoSTTAPI.__new__(ProviderMiMoSTTAPI)
    provider.request_headers = {}
    provider.chosen_api_key = "test-key"
    provider.api_base = "https://mimo.example.test/v1"
    provider.model_name = "mimo-v2.5-asr"

    async def post(*_args, **_kwargs):
        return response

    provider.client = SimpleNamespace(post=post)
    return provider


@pytest.mark.asyncio
async def test_mimo_stt_hides_http_response_body_and_cleans_up(
    monkeypatch,
    caplog,
) -> None:
    cleaned_paths: list[Path] = []
    response = _MiMoResponse(status_error=RuntimeError(_SENSITIVE_ERROR))
    provider = _mimo_provider(response)

    async def prepare_audio(_audio_url: str) -> tuple[str, list[Path]]:
        return "data:audio/wav;base64,AAAA", [Path("temporary.wav")]

    monkeypatch.setattr(mimo_stt_api_source, "prepare_audio_input", prepare_audio)
    monkeypatch.setattr(
        mimo_stt_api_source,
        "cleanup_files",
        lambda paths: cleaned_paths.extend(paths),
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(MiMoAPIError) as error:
            await provider.get_text("audio.wav")

    assert str(error.value) == "MiMo STT API request failed."
    assert cleaned_paths == [Path("temporary.wav")]
    for sensitive_value in _SENSITIVE_VALUES:
        assert sensitive_value not in str(error.value)
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_mimo_stt_rejects_malformed_success_response_and_cleans_up(
    monkeypatch,
) -> None:
    cleaned_paths: list[Path] = []
    provider = _mimo_provider(_MiMoResponse(data=["not-a-response-object"]))

    async def prepare_audio(_audio_url: str) -> tuple[str, list[Path]]:
        return "data:audio/wav;base64,AAAA", [Path("temporary.wav")]

    monkeypatch.setattr(mimo_stt_api_source, "prepare_audio_input", prepare_audio)
    monkeypatch.setattr(
        mimo_stt_api_source,
        "cleanup_files",
        lambda paths: cleaned_paths.extend(paths),
    )

    with pytest.raises(MiMoAPIError, match="MiMo STT API returned an invalid response"):
        await provider.get_text("audio.wav")

    assert cleaned_paths == [Path("temporary.wav")]


@pytest.mark.asyncio
async def test_mimo_stt_propagates_cancellation_and_cleans_up(monkeypatch) -> None:
    cleaned_paths: list[Path] = []
    provider = _mimo_provider(_MiMoResponse())

    async def prepare_audio(_audio_url: str) -> tuple[str, list[Path]]:
        return "data:audio/wav;base64,AAAA", [Path("temporary.wav")]

    async def cancelled_post(*_args, **_kwargs):
        raise asyncio.CancelledError

    provider.client = SimpleNamespace(post=cancelled_post)
    monkeypatch.setattr(mimo_stt_api_source, "prepare_audio_input", prepare_audio)
    monkeypatch.setattr(
        mimo_stt_api_source,
        "cleanup_files",
        lambda paths: cleaned_paths.extend(paths),
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.get_text("audio.wav")

    assert cleaned_paths == [Path("temporary.wav")]


class _FakeMediaResolver:
    def __init__(self, audio_path: Path) -> None:
        self.audio_path = audio_path
        self.closed = False

    def as_path(self, *, target_format: str) -> _FakeMediaResolver:
        assert target_format == "wav"
        return self

    async def __aenter__(self) -> Path:
        return self.audio_path

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.closed = True


class _FakeXinferenceResponse:
    def __init__(self, *, status: int, data=None, error_text: str = "") -> None:
        self.status = status
        self.data = data
        self.error_text = error_text

    async def json(self):
        return self.data

    async def text(self) -> str:
        return self.error_text


class _FakeRequest:
    def __init__(
        self,
        response: _FakeXinferenceResponse | None = None,
        failure: BaseException | None = None,
    ) -> None:
        self.response = response
        self.failure = failure
        self.closed = False

    async def __aenter__(self) -> _FakeXinferenceResponse:
        if self.failure is not None:
            raise self.failure
        assert self.response is not None
        return self.response

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.closed = True


class _FakeSession:
    def __init__(self, request: _FakeRequest) -> None:
        self.request = request

    def post(self, *_args, **_kwargs) -> _FakeRequest:
        return self.request


def _xinference_provider(request: _FakeRequest) -> ProviderXinferenceSTT:
    provider = ProviderXinferenceSTT.__new__(ProviderXinferenceSTT)
    provider.base_url = "https://xinference.example.test"
    provider.timeout = 10
    provider.model_uid = "test-model-uid"
    provider.client = SimpleNamespace(
        _headers={},
        session=_FakeSession(request),
    )
    return provider


@pytest.mark.asyncio
async def test_xinference_stt_redacts_server_error_response(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"wav-data")
    resolver = _FakeMediaResolver(audio_path)
    request = _FakeRequest(
        _FakeXinferenceResponse(status=503, error_text=_SENSITIVE_ERROR)
    )
    provider = _xinference_provider(request)
    monkeypatch.setattr(
        xinference_stt_provider,
        "MediaResolver",
        lambda *_args, **_kwargs: resolver,
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        result = await provider.get_text("audio.wav")

    assert result == ""
    assert request.closed
    assert resolver.closed
    for sensitive_value in _SENSITIVE_VALUES:
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_xinference_stt_rejects_malformed_success_response(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"wav-data")
    resolver = _FakeMediaResolver(audio_path)
    provider = _xinference_provider(
        _FakeRequest(_FakeXinferenceResponse(status=200, data=["invalid"]))
    )
    monkeypatch.setattr(
        xinference_stt_provider,
        "MediaResolver",
        lambda *_args, **_kwargs: resolver,
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        result = await provider.get_text("audio.wav")

    assert result == ""
    assert resolver.closed
    assert "Xinference STT returned an invalid transcription response." in caplog.text


@pytest.mark.asyncio
async def test_xinference_stt_propagates_cancellation_and_closes_media_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"wav-data")
    resolver = _FakeMediaResolver(audio_path)
    request = _FakeRequest(failure=asyncio.CancelledError())
    provider = _xinference_provider(request)
    monkeypatch.setattr(
        xinference_stt_provider,
        "MediaResolver",
        lambda *_args, **_kwargs: resolver,
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.get_text("audio.wav")

    assert resolver.closed
