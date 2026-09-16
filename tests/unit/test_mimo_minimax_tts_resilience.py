"""Offline resilience contracts for MiMo and MiniMax TTS adapters."""

import asyncio
import base64
import logging
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest

from astrbot.core.provider.sources import (
    mimo_tts_api_source,
    minimax_tts_api_source,
)
from astrbot.core.provider.sources.mimo_api_common import MiMoAPIError
from astrbot.core.provider.sources.mimo_tts_api_source import ProviderMiMoTTSAPI
from astrbot.core.provider.sources.minimax_tts_api_source import ProviderMiniMaxTTSAPI

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
    def __init__(
        self,
        *,
        status_error: BaseException | None = None,
        data=None,
    ) -> None:
        self.status_error = status_error
        self.data = data
        self.status_code = 502
        self.text = _SENSITIVE_ERROR

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        return self.data


def _mimo_provider(response: _MiMoResponse) -> ProviderMiMoTTSAPI:
    provider = ProviderMiMoTTSAPI.__new__(ProviderMiMoTTSAPI)
    provider.request_headers = {}
    provider.chosen_api_key = "test-key"
    provider.api_base = "https://mimo.example.test/v1"
    provider.audio_format = "wav"
    provider._build_payload = lambda _text: {}

    async def post(*_args, **_kwargs):
        return response

    provider.client = SimpleNamespace(post=post)
    return provider


@pytest.mark.asyncio
async def test_mimo_tts_hides_http_response_body(monkeypatch, caplog) -> None:
    provider = _mimo_provider(
        _MiMoResponse(status_error=RuntimeError(_SENSITIVE_ERROR))
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(MiMoAPIError) as error:
            await provider.get_audio("hello")

    assert str(error.value) == "MiMo TTS API request failed."
    for sensitive_value in _SENSITIVE_VALUES:
        assert sensitive_value not in str(error.value)
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "message"),
    [
        (["not-a-response-object"], "MiMo TTS API returned an invalid response."),
        (
            {"choices": [], "debug": _SENSITIVE_ERROR},
            "MiMo TTS API returned no audio payload.",
        ),
        (
            {
                "choices": [
                    {"message": {"audio": {"data": "%%%invalid%%%"}}},
                ]
            },
            "MiMo TTS API returned an invalid audio payload.",
        ),
    ],
)
async def test_mimo_tts_rejects_malformed_or_empty_output(
    data,
    message: str,
) -> None:
    provider = _mimo_provider(_MiMoResponse(data=data))

    with pytest.raises(MiMoAPIError) as error:
        await provider.get_audio("hello")

    assert str(error.value) == message


@pytest.mark.asyncio
async def test_mimo_tts_cancellation_removes_partially_written_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_data = base64.b64encode(b"audio").decode()
    provider = _mimo_provider(
        _MiMoResponse(data={"choices": [{"message": {"audio": {"data": audio_data}}}]})
    )
    original_write_bytes = Path.write_bytes

    def partial_write_then_cancel(path: Path, data: bytes) -> int:
        original_write_bytes(path, data[:1])
        raise asyncio.CancelledError

    monkeypatch.setattr(mimo_tts_api_source, "get_temp_dir", lambda: tmp_path)
    monkeypatch.setattr(Path, "write_bytes", partial_write_then_cancel)

    with pytest.raises(asyncio.CancelledError):
        await provider.get_audio("hello")

    assert not list(tmp_path.glob("mimo_tts_api_*.wav"))


class _MiniMaxContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def read(self, _chunk_size: int) -> bytes:
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class _MiniMaxResponse:
    def __init__(
        self,
        *,
        chunks: list[bytes] | None = None,
        status_error: BaseException | None = None,
    ) -> None:
        self.content = _MiniMaxContent(chunks or [])
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error


class _MiniMaxRequest:
    def __init__(self, response: _MiniMaxResponse) -> None:
        self.response = response
        self.closed = False

    async def __aenter__(self) -> _MiniMaxResponse:
        return self.response

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.closed = True


class _MiniMaxSession:
    def __init__(self, request: _MiniMaxRequest) -> None:
        self.request = request
        self.closed = False

    async def __aenter__(self) -> _MiniMaxSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.closed = True

    def post(self, *_args, **_kwargs) -> _MiniMaxRequest:
        return self.request


def _minimax_provider() -> ProviderMiniMaxTTSAPI:
    provider = ProviderMiniMaxTTSAPI.__new__(ProviderMiniMaxTTSAPI)
    provider.request_headers = {}
    provider.concat_base_url = "https://minimax.example.test/v1/t2a"
    provider.headers = {}
    provider._build_tts_stream_body = lambda _text: "{}"
    return provider


@pytest.mark.asyncio
async def test_minimax_tts_hides_http_exception(monkeypatch, caplog) -> None:
    request = _MiniMaxRequest(
        _MiniMaxResponse(status_error=aiohttp.ClientError(_SENSITIVE_ERROR))
    )
    session = _MiniMaxSession(request)
    provider = _minimax_provider()
    monkeypatch.setattr(
        minimax_tts_api_source.aiohttp, "ClientSession", lambda **_kwargs: session
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(RuntimeError) as error:
            await anext(provider._call_tts_stream("hello"))

    assert str(error.value) == "MiniMax TTS API request failed."
    assert request.closed
    assert session.closed
    for sensitive_value in _SENSITIVE_VALUES:
        assert sensitive_value not in str(error.value)
        assert sensitive_value not in caplog.text


@pytest.mark.asyncio
async def test_minimax_tts_ignores_malformed_sse_message(monkeypatch, caplog) -> None:
    request = _MiniMaxRequest(_MiniMaxResponse(chunks=[b'data: ["invalid"]\n\n']))
    session = _MiniMaxSession(request)
    provider = _minimax_provider()
    monkeypatch.setattr(
        minimax_tts_api_source.aiohttp, "ClientSession", lambda **_kwargs: session
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        chunks = [chunk async for chunk in provider._call_tts_stream("hello")]

    assert chunks == []
    assert "MiniMax TTS received an invalid SSE message." in caplog.text


@pytest.mark.asyncio
async def test_minimax_tts_cancellation_removes_partially_written_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = _minimax_provider()
    original_write_bytes = Path.write_bytes

    async def audio_stream(_text: str):
        yield "7061727469616c"

    class _CancellingFile:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> _CancellingFile:
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            return None

        def write(self, data: bytes) -> int:
            original_write_bytes(self.path, data[:1])
            raise asyncio.CancelledError

    def open_partial_file(path: str, *_args, **_kwargs) -> _CancellingFile:
        return _CancellingFile(Path(path))

    provider._call_tts_stream = audio_stream
    monkeypatch.setattr(
        minimax_tts_api_source, "get_astrbot_temp_path", lambda: tmp_path
    )
    monkeypatch.setattr(
        minimax_tts_api_source, "open", open_partial_file, raising=False
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.get_audio("hello")

    assert not list(tmp_path.glob("minimax_tts_api_*.wav"))


@pytest.mark.asyncio
async def test_minimax_tts_rejects_empty_stream_without_creating_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provider = _minimax_provider()

    async def empty_stream(_text: str):
        if False:  # pragma: no cover - keeps this a typed async generator
            yield ""

    provider._call_tts_stream = empty_stream
    monkeypatch.setattr(
        minimax_tts_api_source, "get_astrbot_temp_path", lambda: tmp_path
    )

    with pytest.raises(RuntimeError) as error:
        await provider.get_audio("hello")

    assert str(error.value) == "MiniMax TTS audio generation failed."
    assert not list(tmp_path.glob("minimax_tts_api_*.wav"))
