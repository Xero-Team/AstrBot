"""Offline System One wire contracts from https://docs.typesafe.ai/api."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from astrbot.core.config.default import JEV_SYSTEMONE_TEMPLATE
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.sources.jev_systemone_source import JevSystemOneProvider
from astrbot.core.typed_decision import (
    ChoiceQuestion,
    ClassifierResult,
    NoulQuestion,
    ScoreQuestion,
)

QUESTIONS = {
    "urgent": NoulQuestion(instructions="Is it urgent?"),
    "team": ChoiceQuestion(
        instructions="Which team?", criteria={"billing": None, "sales": None}
    ),
    "mood": ScoreQuestion(instructions="How frustrated?", criteria=["calm", "angry"]),
}
RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "urgent": {"type": "noul", "noul": 0.95},
        "team": {
            "type": "choice",
            "choice": "billing",
            "probabilities": {"billing": 0.9, "sales": 0.1},
            "confidence": 0.8,
        },
        "mood": {
            "type": "score",
            "score": 0.75,
            "legend": {"0": "calm", "1": "angry"},
            "probabilities": {"0": 0.25, "1": 0.75},
            "confidence": 0.6,
        },
    },
    "usage": {"input_tokens": 100, "output_tokens": 20},
}


@pytest.fixture
def provider(monkeypatch):
    client = MagicMock()
    client.close = AsyncMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(aiohttp, "ClientSession", factory)
    instance = JevSystemOneProvider({**JEV_SYSTEMONE_TEMPLATE, "key": ["test-key"]}, {})
    return instance, client, factory


def response(client, status=200, body=None):
    result = MagicMock(status=status)
    result.json = AsyncMock(return_value=deepcopy(RESPONSE if body is None else body))
    client.post.return_value.__aenter__ = AsyncMock(return_value=result)
    return result


@pytest.mark.asyncio
async def test_wire_contract_and_proxy_tls_defaults(provider):
    instance, client, factory = provider
    response(client)
    instance.provider_config.update(
        proxy_mode="custom", proxy_url="http://proxy.example:8080"
    )
    result = await instance.evaluate({"message": "help"}, QUESTIONS)
    assert result.model == "jev-1.13.0"
    assert result.answers["urgent"].noul == 0.95
    assert result.answers["team"].confidence == 0.8
    assert result.answers["mood"].score == 0.75
    assert result.usage.input_tokens == 100
    kwargs = client.post.call_args.kwargs
    assert client.post.call_args.args == ("https://api.typesafe.ai/v1/systemone",)
    assert kwargs["json"]["questions"]["team"]["criteria"] == {
        "billing": None,
        "sales": None,
    }
    assert kwargs["proxy"] == "http://proxy.example:8080"
    assert kwargs["allow_redirects"] is False
    assert "ssl" not in kwargs
    assert "connector" not in factory.call_args.kwargs
    assert factory.call_args.kwargs["trust_env"] is False
    assert factory.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert instance.meta().provider_type == ProviderType.CLASSIFIER
    await instance.terminate()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 422, 500, 302])
async def test_http_failures_are_safe_and_not_retried(provider, status):
    instance, client, _ = provider
    remote = response(client, status)
    with pytest.raises(RuntimeError, match="JEV evaluation failed"):
        await instance.evaluate("help", QUESTIONS)
    assert client.post.call_count == 1
    remote.json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 529])
@pytest.mark.parametrize("recovers", [True, False])
async def test_overload_backoff_is_bounded(provider, monkeypatch, status, recovers):
    instance, client, _ = provider
    remote = response(client, status)
    attempts = [MagicMock(status=status), MagicMock(status=status), remote]
    remote.status = 200 if recovers else status
    client.post.return_value.__aenter__.side_effect = attempts
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    if recovers:
        assert (await instance.evaluate("help", QUESTIONS)).model == RESPONSE["model"]
    else:
        with pytest.raises(RuntimeError):
            await instance.evaluate("help", QUESTIONS)
    assert client.post.call_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [0.5, 1.0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("secret"),
        aiohttp.ClientError("secret"),
        ValueError("secret"),
        asyncio.CancelledError(),
    ],
)
async def test_network_failure_timeout_and_cancellation(provider, error):
    instance, client, _ = provider
    response(client)
    client.post.return_value.__aenter__.side_effect = error
    expected = (
        type(error)
        if isinstance(error, TimeoutError | asyncio.CancelledError)
        else RuntimeError
    )
    with pytest.raises(expected) as caught:
        await instance.evaluate("help", QUESTIONS)
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_total_timeout_includes_backoff(provider, monkeypatch):
    instance, client, _ = provider
    instance.timeout = 0.01
    response(client, 429)
    with pytest.raises(TimeoutError, match="timed out"):
        await instance.evaluate("help", QUESTIONS)
    assert client.post.call_count == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["answers"].pop("urgent"),
        lambda d: d["answers"]["urgent"].update(noul=True),
        lambda d: d["answers"]["urgent"].update(noul=float("nan")),
        lambda d: d["answers"]["urgent"].update(noul=1.5),
        lambda d: d["answers"]["urgent"].update(type="score"),
        lambda d: d["answers"]["team"].update(choice="invented"),
        lambda d: d["answers"]["team"].update(confidence="0.9"),
        lambda d: d["answers"]["team"].update(
            probabilities={"billing": 0.9, "sales": 0.9}
        ),
        lambda d: d["answers"]["team"].update(
            probabilities={"billing": 0.9, "other": 0.1}
        ),
        lambda d: d["answers"]["mood"].update(score=0.1),
        lambda d: d["answers"]["mood"].update(legend={"2": "wrong"}),
        lambda d: d["usage"].update(input_tokens=-1),
    ],
)
def test_malformed_answers_are_rejected(mutation):
    body = deepcopy(RESPONSE)
    mutation(body)
    with pytest.raises(ValueError):
        ClassifierResult.model_validate(body).validate_questions(QUESTIONS)


@pytest.mark.asyncio
async def test_malformed_remote_body_and_empty_questions(provider):
    instance, client, _ = provider
    response(client, body={"message": "private provider data"})
    with pytest.raises(RuntimeError, match="^JEV evaluation failed$"):
        await instance.evaluate("help", QUESTIONS)
    with pytest.raises(ValueError, match="at least one"):
        await instance.evaluate("help", {})


@pytest.mark.parametrize(
    "config",
    [
        {"api_base": "http://typesafe.ai"},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"key": []},
    ],
)
def test_invalid_configuration_never_opens_a_client(monkeypatch, config):
    factory = MagicMock()
    monkeypatch.setattr(aiohttp, "ClientSession", factory)
    with pytest.raises(ValueError):
        JevSystemOneProvider(
            {**JEV_SYSTEMONE_TEMPLATE, "key": ["test-key"], **config}, {}
        )
    factory.assert_not_called()
