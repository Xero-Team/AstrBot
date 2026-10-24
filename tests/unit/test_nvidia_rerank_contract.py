"""Offline lifecycle and error-boundary contracts for NVIDIA reranking."""

import asyncio
import logging

import pytest

from astrbot.core.provider.sources.nvidia_rerank_source import NvidiaRerankProvider

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=nvidia-api-key "
    "Bearer nvidia-bearer-token "
    "password=nvidia-password "
    "https://internal.example/rerank "
    "C:\\private\\rerank.txt "
    "/srv/astrbot/rerank.json"
)
_SENSITIVE_VALUES = (
    "nvidia-api-key",
    "nvidia-bearer-token",
    "nvidia-password",
    "https://internal.example/rerank",
    "C:\\private\\rerank.txt",
    "/srv/astrbot/rerank.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        rendered = str(text)
        for value in _SENSITIVE_VALUES:
            assert value not in rendered


class _Response:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload

    async def json(self) -> dict:
        return self.payload

    async def text(self) -> str:
        return _SENSITIVE_ERROR


class _Request:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Client:
    def __init__(
        self, response: _Response | BaseException, *, closed: bool = False
    ) -> None:
        self.response = response
        self.closed = closed
        self.closed_by_terminate = False

    def post(self, _url: str, *, json: dict) -> _Request:
        return _Request(self.response)

    async def close(self) -> None:
        self.closed_by_terminate = True
        self.closed = True


def _provider(client: _Client) -> NvidiaRerankProvider:
    provider = NvidiaRerankProvider.__new__(NvidiaRerankProvider)
    provider.client = client
    provider.base_url = "https://rerank.example.test"
    provider.model = "nvidia/test-reranker"
    provider.model_endpoint = "/reranking"
    provider.truncate = ""
    return provider


@pytest.mark.asyncio
async def test_rerank_hides_provider_error_from_exception_and_logs(caplog) -> None:
    provider = _provider(_Client(_Response(500, {"detail": _SENSITIVE_ERROR})))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="NVIDIA rerank request failed"
        ) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


def test_rerank_parser_hides_malformed_provider_payload(caplog) -> None:
    provider = _provider(_Client(_Response(200, {})))

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        result = provider._parse_results(
            {"rankings": [{"index": 0, "relevance_score": _SENSITIVE_ERROR}]},
            top_n=None,
        )

    assert result == []
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_rerank_ignores_malformed_usage_after_valid_results() -> None:
    provider = _provider(
        _Client(
            _Response(
                200,
                {
                    "rankings": [{"index": 0, "relevance_score": 0.9}],
                    "usage": {"total_tokens": _SENSITIVE_ERROR},
                },
            )
        )
    )

    result = await provider.rerank("query", ["document"])

    assert [(item.index, item.relevance_score) for item in result] == [(0, 0.9)]


@pytest.mark.asyncio
async def test_rerank_propagates_cancellation() -> None:
    provider = _provider(_Client(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await provider.rerank("query", ["document"])


@pytest.mark.asyncio
async def test_rerank_terminate_drops_an_already_closed_client() -> None:
    client = _Client(_Response(200, {}), closed=True)
    provider = _provider(client)

    await provider.terminate()

    assert provider.client is None
    assert client.closed_by_terminate is False


@pytest.mark.parametrize(
    ("model", "expected_path"),
    [
        (
            "nvidia/nemotron-3.5-rerank-8b",
            "nvidia/nemotron-3.5-rerank-8b",
        ),
        (
            "nvidia/llama-3.2-nv-rerankqa-1b-v1",
            "nvidia/llama-3_2-nv-rerankqa-1b-v1",
        ),
        (
            "nvidia/llama-3.2-nv-rerankqa-1b-v2",
            "nvidia/llama-3_2-nv-rerankqa-1b-v2",
        ),
        (
            "nvidia/llama-3.2-nemoretriever-500m-rerank-v2",
            "nvidia/llama-3_2-nemoretriever-500m-rerank-v2",
        ),
        ("nv-rerank-qa-mistral-4b:1", "nvidia"),
    ],
)
def test_nvidia_rerank_preserves_model_specific_endpoint_paths(
    model: str, expected_path: str
) -> None:
    provider = NvidiaRerankProvider.__new__(NvidiaRerankProvider)
    provider.base_url = "https://rerank.example.test"
    provider.model_endpoint = "/v1/retrieval/reranking"
    provider.model = model

    assert (
        provider._get_endpoint()
        == f"https://rerank.example.test/{expected_path}/v1/retrieval/reranking"
    )
