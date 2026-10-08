"""Offline lifecycle and error-boundary contracts for Gemini embeddings."""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from google.genai.errors import APIError

import astrbot.core.provider.sources.gemini_embedding_source as gemini_module
from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=gemini-api-key "
    "Bearer gemini-bearer-token "
    "password=gemini-password "
    "https://internal.example/embedding "
    "C:\\private\\embedding.txt "
    "/srv/astrbot/embedding.json"
)
_SENSITIVE_VALUES = (
    "gemini-api-key",
    "gemini-bearer-token",
    "gemini-password",
    "https://internal.example/embedding",
    "C:\\private\\embedding.txt",
    "/srv/astrbot/embedding.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        rendered = str(text)
        for value in _SENSITIVE_VALUES:
            assert value not in rendered


class _Models:
    def __init__(self, response: object | BaseException) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def embed_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class _Client:
    def __init__(self, response: object | BaseException) -> None:
        self.models = _Models(response)
        self.closed = False
        self.close_error: BaseException | None = None

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _provider(client: _Client) -> GeminiEmbeddingProvider:
    provider = GeminiEmbeddingProvider.__new__(GeminiEmbeddingProvider)
    provider.client = client
    provider.model = "gemini-embedding-test"
    provider.provider_config = {"embedding_dimensions": 3}
    return provider


def _response(*values: list[object]) -> SimpleNamespace:
    return SimpleNamespace(
        embeddings=[SimpleNamespace(values=value) for value in values]
    )


@pytest.mark.asyncio
async def test_get_embedding_hides_api_error_from_exception_and_logs(caplog) -> None:
    provider = _provider(_Client(APIError(500, {"message": _SENSITIVE_ERROR})))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="Gemini embedding request failed"
        ) as caught:
            await provider.get_embedding("document")

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_get_embeddings_hides_unexpected_provider_error_and_logs(caplog) -> None:
    provider = _provider(_Client(RuntimeError(_SENSITIVE_ERROR)))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="Gemini embedding request failed"
        ) as caught:
            await provider.get_embeddings(["first", "second"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_get_embeddings_rejects_malformed_values_without_leaking_them(
    caplog,
) -> None:
    provider = _provider(_Client(_response([0.1, 0.2], [_SENSITIVE_ERROR])))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="Gemini embedding request failed"
        ) as caught:
            await provider.get_embeddings(["first", "second"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_get_embedding_rejects_missing_embedding_response(caplog) -> None:
    provider = _provider(_Client(_response()))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match="Gemini embedding request failed"):
            await provider.get_embedding("document")

    assert "AssertionError" not in caplog.text


@pytest.mark.asyncio
async def test_get_embedding_propagates_cancellation() -> None:
    provider = _provider(_Client(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await provider.get_embedding("document")


@pytest.mark.asyncio
async def test_terminate_sanitizes_close_failure_and_drops_client(caplog) -> None:
    client = _Client(_response([0.1, 0.2, 0.3]))
    client.close_error = RuntimeError(_SENSITIVE_ERROR)
    provider = _provider(client)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.terminate()

    assert client.closed is True
    assert provider.client is None
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_terminate_propagates_cancellation_after_dropping_client() -> None:
    client = _Client(_response([0.1, 0.2, 0.3]))
    client.close_error = asyncio.CancelledError()
    provider = _provider(client)

    with pytest.raises(asyncio.CancelledError):
        await provider.terminate()

    assert client.closed is True
    assert provider.client is None


def test_constructor_does_not_log_proxy_contents(caplog, monkeypatch) -> None:
    client = _Client(_response([0.1, 0.2, 0.3]))
    monkeypatch.setattr(
        gemini_module.genai,
        "Client",
        lambda **_kwargs: SimpleNamespace(aio=client),
    )

    with caplog.at_level(logging.INFO, logger="astrbot"):
        provider = GeminiEmbeddingProvider(
            {
                "type": "gemini_embedding",
                "embedding_api_key": "gemini-api-key",
                "embedding_api_base": "https://embedding.example.test",
                "proxy": _SENSITIVE_ERROR,
            },
            {},
        )

    assert provider.client is client
    _assert_no_sensitive_values(caplog.text)


def test_constructor_uses_current_embedding_model_by_default(monkeypatch) -> None:
    client = _Client(_response([0.1, 0.2, 0.3]))
    monkeypatch.setattr(
        gemini_module.genai,
        "Client",
        lambda **_kwargs: SimpleNamespace(aio=client),
    )

    provider = GeminiEmbeddingProvider(
        {
            "type": "gemini_embedding",
            "embedding_api_key": "gemini-api-key",
            "embedding_api_base": "",
        },
        {},
    )

    assert provider.model == "gemini-embedding-001"
