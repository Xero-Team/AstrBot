"""Offline retry, security, and lifecycle contracts for self-hosted GSV TTS."""

import asyncio
import builtins
import logging
from pathlib import Path

import pytest

from astrbot.core.provider.sources import gsv_selfhosted_source
from astrbot.core.provider.sources.gsv_selfhosted_source import ProviderGSVTTS

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=gsv-api-key "
    "Bearer gsv-bearer "
    "password=gsv-password "
    "https://internal.example/gsv "
    "C:\\private\\gsv.txt "
    "/srv/astrbot/gsv.json"
)
_SENSITIVE_VALUES = (
    "gsv-api-key",
    "gsv-bearer",
    "gsv-password",
    "https://internal.example/gsv",
    "C:\\private\\gsv.txt",
    "/srv/astrbot/gsv.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        for value in _SENSITIVE_VALUES:
            assert value not in str(text)


class _Response:
    def __init__(self, status: int, body: bytes = b"audio") -> None:
        self.status = status
        self.body = body

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

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
        responses: tuple[_Response | BaseException, ...] = (_Response(200),),
        *,
        close_error: BaseException | None = None,
        closed: bool = False,
    ) -> None:
        self.responses = list(responses)
        self.close_error = close_error
        self.closed = closed
        self.close_called = False

    def get(self, *_args: object, **_kwargs: object) -> _Request:
        return _Request(self.responses.pop(0))

    async def close(self) -> None:
        self.close_called = True
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _provider(session: _Session | None = None) -> ProviderGSVTTS:
    provider = ProviderGSVTTS.__new__(ProviderGSVTTS)
    provider.request_headers = {}
    provider.api_base = "https://gsv.example.test"
    provider.gpt_weights_path = ""
    provider.sovits_weights_path = ""
    provider.default_params = {}
    provider.timeout = 1
    provider._session = session
    return provider


@pytest.mark.asyncio
async def test_gsv_request_retries_without_real_sleep_and_hides_response(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    provider = _provider(_Session((_Response(500), _Response(500))))
    sleeps: list[float] = []

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(gsv_selfhosted_source.asyncio, "sleep", _sleep)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        with pytest.raises(RuntimeError, match="GSV TTS request failed") as caught:
            await provider._make_request(
                "https://internal.example/gsv/tts",
                {"text": _SENSITIVE_ERROR},
                retries=2,
            )

    assert sleeps == [1]
    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_gsv_request_propagates_cancellation() -> None:
    provider = _provider(_Session((asyncio.CancelledError(),)))

    with pytest.raises(asyncio.CancelledError):
        await provider._make_request("https://gsv.example.test/tts", retries=1)


@pytest.mark.asyncio
async def test_gsv_initialize_failure_closes_session_and_hides_error(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    session = _Session()
    provider = _provider()
    monkeypatch.setattr(
        gsv_selfhosted_source.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )

    async def _fail() -> None:
        raise RuntimeError(_SENSITIVE_ERROR)

    monkeypatch.setattr(provider, "_set_model_weights", _fail)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="GSV TTS initialization failed"
        ) as caught:
            await provider.initialize()

    assert session.close_called is True
    assert provider._session is None
    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_gsv_weight_failure_is_not_swallowed_or_logged_with_paths(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    provider = _provider(_Session())
    provider.gpt_weights_path = _SENSITIVE_ERROR

    async def _fail(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("GSV TTS request failed")

    monkeypatch.setattr(provider, "_make_request", _fail)

    with caplog.at_level(logging.INFO, logger="astrbot"):
        with pytest.raises(RuntimeError, match="GSV TTS request failed"):
            await provider._set_model_weights()

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_gsv_audio_failure_hides_input_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    provider = _provider(_Session())
    monkeypatch.setattr(
        gsv_selfhosted_source, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    async def _fail(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(provider, "_make_request", _fail)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="GSV TTS audio generation failed"
        ) as caught:
            await provider.get_audio(_SENSITIVE_ERROR)

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_gsv_rejects_empty_audio_and_cleans_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = _provider(_Session())
    monkeypatch.setattr(
        gsv_selfhosted_source, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    async def _empty(*_args: object, **_kwargs: object) -> bytes:
        return b""

    monkeypatch.setattr(provider, "_make_request", _empty)

    with pytest.raises(RuntimeError, match="GSV TTS audio generation failed"):
        await provider.get_audio("text")

    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_gsv_cancellation_cleans_partial_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = _provider(_Session())
    monkeypatch.setattr(
        gsv_selfhosted_source, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    async def _audio(*_args: object, **_kwargs: object) -> bytes:
        return b"audio"

    monkeypatch.setattr(provider, "_make_request", _audio)

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

    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.asyncio
async def test_gsv_terminate_drops_session_and_hides_close_error(caplog) -> None:
    session = _Session(close_error=RuntimeError(_SENSITIVE_ERROR))
    provider = _provider(session)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.terminate()

    assert session.close_called is True
    assert provider._session is None
    _assert_no_sensitive_values(caplog.text)
