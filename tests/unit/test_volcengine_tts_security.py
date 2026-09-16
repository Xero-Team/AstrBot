"""Offline security contracts for the Volcengine TTS adapter."""

import base64
import json
import logging
from pathlib import Path

import pytest

from astrbot.core.provider.sources import volcengine_tts
from astrbot.core.provider.sources.volcengine_tts import ProviderVolcengineTTS

_SENSITIVE_ERROR = (
    "api_key=volc-api-key "
    "Bearer volc-bearer-token "
    "password=volc-password "
    "https://internal.example/volcengine "
    "C:\\private\\volcengine.txt "
    "/srv/astrbot/volcengine.json"
)
_SENSITIVE_VALUES = (
    "volc-api-key",
    "volc-bearer-token",
    "volc-password",
    "https://internal.example/volcengine",
    "C:\\private\\volcengine.txt",
    "/srv/astrbot/volcengine.json",
)


class _Response:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        self.closed = False

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    async def text(self) -> str:
        return self.body


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.closed = False

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    def post(self, *_args: object, **_kwargs: object) -> _Response:
        return self.response


def _provider() -> ProviderVolcengineTTS:
    return ProviderVolcengineTTS(
        {
            "type": "volcengine_tts",
            "api_key": "volc-api-key",
            "appid": "app-id",
            "volcengine_cluster": "cluster",
            "volcengine_voice_type": "voice",
            "api_base": "https://internal.example/volcengine",
        },
        {},
    )


@pytest.mark.asyncio
async def test_volcengine_tts_hides_http_error_details_and_closes_resources(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    response = _Response(500, _SENSITIVE_ERROR)
    session = _Session(response)
    monkeypatch.setattr(
        volcengine_tts.aiohttp, "ClientSession", lambda **_kwargs: session
    )
    monkeypatch.setattr(volcengine_tts, "get_astrbot_temp_path", lambda: tmp_path)

    with caplog.at_level(logging.DEBUG, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="Volcengine TTS audio generation failed"
        ) as caught:
            await _provider().get_audio("secret text")

    assert caught.value.__cause__ is None
    assert response.closed
    assert session.closed
    assert not list(tmp_path.glob("volcengine_tts_*.mp3"))
    for value in _SENSITIVE_VALUES:
        assert value not in str(caught.value)
        assert value not in caplog.text


@pytest.mark.asyncio
async def test_volcengine_tts_writes_nonempty_audio_without_an_executor(
    monkeypatch,
    tmp_path: Path,
) -> None:
    response = _Response(
        200,
        json.dumps({"data": base64.b64encode(b"audio-data").decode()}),
    )
    session = _Session(response)
    monkeypatch.setattr(
        volcengine_tts.aiohttp, "ClientSession", lambda **_kwargs: session
    )
    monkeypatch.setattr(volcengine_tts, "get_astrbot_temp_path", lambda: tmp_path)

    output_path = Path(await _provider().get_audio("hello"))

    try:
        assert output_path.read_bytes() == b"audio-data"
        assert response.closed
        assert session.closed
    finally:
        output_path.unlink(missing_ok=True)
