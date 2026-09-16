"""Offline lifecycle and error-boundary contracts for rerank adapters."""

import asyncio
import logging

import aiohttp
import pytest

import astrbot.core.provider.sources.xinference_rerank_source as xinference_module
from astrbot.core.provider.sources.bailian_rerank_source import (
    BailianAPIError,
    BailianNetworkError,
    BailianRerankProvider,
)
from astrbot.core.provider.sources.xinference_rerank_source import (
    XinferenceRerankProvider,
)

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=bailian-api-key "
    "Bearer rerank-bearer-token "
    "password=rerank-password "
    "https://internal.example/rerank "
    "C:\\private\\rerank.txt "
    "/srv/astrbot/rerank.json"
)
_SENSITIVE_VALUES = (
    "bailian-api-key",
    "rerank-bearer-token",
    "rerank-password",
    "https://internal.example/rerank",
    "C:\\private\\rerank.txt",
    "/srv/astrbot/rerank.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        rendered = str(text)
        for value in _SENSITIVE_VALUES:
            assert value not in rendered


class _Request:
    def __init__(self, response: object | BaseException) -> None:
        self.response = response

    async def __aenter__(self) -> object:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _BailianResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    async def json(self) -> object:
        return self.payload


class _BailianClient:
    def __init__(self, response: object | BaseException) -> None:
        self.response = response
        self.closed = False
        self.close_error: BaseException | None = None

    def post(self, _url: str, *, json: dict) -> _Request:
        return _Request(self.response)

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class _XinferenceModel:
    def __init__(self, response: object | BaseException) -> None:
        self.response = response

    async def rerank(
        self, _documents: list[str], _query: str, _top_n: int | None
    ) -> object:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class _XinferenceClient:
    def __init__(self, list_models_result: object | BaseException) -> None:
        self.list_models_result = list_models_result
        self._headers: dict[str, str] = {}
        self.closed = False
        self.close_error: BaseException | None = None

    async def list_models(self) -> object:
        if isinstance(self.list_models_result, BaseException):
            raise self.list_models_result
        return self.list_models_result

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _bailian_provider(client: _BailianClient) -> BailianRerankProvider:
    provider = BailianRerankProvider.__new__(BailianRerankProvider)
    provider.client = client
    provider.base_url = "https://rerank.example.test"
    provider.model = "qwen3-rerank"
    provider.return_documents = False
    provider.instruct = ""
    return provider


def _xinference_provider(
    client: _XinferenceClient | None,
    model: _XinferenceModel | None,
) -> XinferenceRerankProvider:
    provider = XinferenceRerankProvider.__new__(XinferenceRerankProvider)
    provider.client = client
    provider.model = model
    provider.model_uid = "rerank-model"
    return provider


@pytest.mark.asyncio
async def test_bailian_hides_network_error_from_exception_and_logs(caplog) -> None:
    provider = _bailian_provider(_BailianClient(aiohttp.ClientError(_SENSITIVE_ERROR)))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            BailianNetworkError, match="Bailian rerank request failed"
        ) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_bailian_hides_api_error_details_from_exception() -> None:
    provider = _bailian_provider(
        _BailianClient(
            _BailianResponse({"code": "500", "message": _SENSITIVE_ERROR, "output": {}})
        )
    )

    with pytest.raises(
        BailianAPIError, match="Bailian rerank request failed"
    ) as caught:
        await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value)


def test_bailian_parser_skips_malformed_results_without_logging_contents(
    caplog,
) -> None:
    provider = _bailian_provider(_BailianClient(_BailianResponse({})))

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        result = provider._parse_results(
            {
                "output": {
                    "results": [
                        {"index": 0, "relevance_score": 0.8},
                        {"index": 1, "relevance_score": _SENSITIVE_ERROR},
                        _SENSITIVE_ERROR,
                    ]
                }
            }
        )

    assert [(item.index, item.relevance_score) for item in result] == [(0, 0.8)]
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_bailian_propagates_cancellation() -> None:
    provider = _bailian_provider(_BailianClient(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await provider.rerank("query", ["document"])


@pytest.mark.asyncio
async def test_bailian_terminate_sanitizes_close_failure_and_drops_client(
    caplog,
) -> None:
    client = _BailianClient(_BailianResponse({}))
    client.close_error = RuntimeError(_SENSITIVE_ERROR)
    provider = _bailian_provider(client)

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await provider.terminate()

    assert client.closed is True
    assert provider.client is None
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_xinference_hides_model_errors_from_logs(caplog) -> None:
    provider = _xinference_provider(
        _XinferenceClient({}), _XinferenceModel(RuntimeError(_SENSITIVE_ERROR))
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        assert await provider.rerank("query", ["document"]) == []

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_xinference_preserves_valid_results_when_response_is_malformed(
    caplog,
) -> None:
    provider = _xinference_provider(
        _XinferenceClient({}),
        _XinferenceModel(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.6},
                    {"index": 1, "relevance_score": _SENSITIVE_ERROR},
                    _SENSITIVE_ERROR,
                ]
            }
        ),
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        result = await provider.rerank("query", ["document"])

    assert [(item.index, item.relevance_score) for item in result] == [(0, 0.6)]
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_xinference_propagates_rerank_cancellation() -> None:
    provider = _xinference_provider(
        _XinferenceClient({}), _XinferenceModel(asyncio.CancelledError())
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.rerank("query", ["document"])


@pytest.mark.asyncio
async def test_xinference_initialize_closes_client_after_failure(
    caplog, monkeypatch
) -> None:
    client = _XinferenceClient(RuntimeError(_SENSITIVE_ERROR))
    monkeypatch.setattr(xinference_module, "Client", lambda *_args, **_kwargs: client)
    provider = XinferenceRerankProvider(
        {"type": "xinference_rerank", "rerank_api_base": "https://rerank.test"},
        {},
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        await provider.initialize()

    assert client.closed is True
    assert provider.client is None
    assert provider.model is None
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_xinference_initialize_propagates_cancellation_and_closes_client(
    monkeypatch,
) -> None:
    client = _XinferenceClient(asyncio.CancelledError())
    monkeypatch.setattr(xinference_module, "Client", lambda *_args, **_kwargs: client)
    provider = XinferenceRerankProvider(
        {"type": "xinference_rerank", "rerank_api_base": "https://rerank.test"},
        {},
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.initialize()

    assert client.closed is True
    assert provider.client is None
    assert provider.model is None


@pytest.mark.asyncio
async def test_xinference_terminate_closes_and_drops_client() -> None:
    client = _XinferenceClient({})
    provider = _xinference_provider(client, _XinferenceModel({"results": []}))

    await provider.terminate()

    assert client.closed is True
    assert provider.client is None
    assert provider.model is None
    assert provider.model_uid is None


@pytest.mark.asyncio
async def test_xinference_terminate_sanitizes_close_failure_and_drops_client(
    caplog,
) -> None:
    client = _XinferenceClient({})
    client.close_error = RuntimeError(_SENSITIVE_ERROR)
    provider = _xinference_provider(client, _XinferenceModel({"results": []}))

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.terminate()

    assert client.closed is True
    assert provider.client is None
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_xinference_terminate_propagates_cancellation_after_cleanup() -> None:
    client = _XinferenceClient({})
    client.close_error = asyncio.CancelledError()
    provider = _xinference_provider(client, _XinferenceModel({"results": []}))

    with pytest.raises(asyncio.CancelledError):
        await provider.terminate()

    assert client.closed is True
    assert provider.client is None
    assert provider.model is None
    assert provider.model_uid is None
