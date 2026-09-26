import copy
import socket
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiohttp import web

from astrbot import __version__
from astrbot.core.provider.headers import (
    CONVERSATION_ID_HEADER,
    DEFAULT_USER_AGENT,
    build_conversation_headers,
    build_provider_headers,
    drop_sdk_user_agent,
)
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.bailian_rerank_source import BailianRerankProvider
from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.gemini_tts_source import ProviderGeminiTTSAPI
from astrbot.core.provider.sources.kimi_code_source import ProviderKimiCode
from astrbot.core.provider.sources.nvidia_embedding_source import (
    NvidiaEmbeddingProvider,
)
from astrbot.core.provider.sources.nvidia_rerank_source import NvidiaRerankProvider
from astrbot.core.provider.sources.ollama_embedding_source import (
    OllamaEmbeddingProvider,
)
from astrbot.core.provider.sources.openai_chat_completions_source import (
    ProviderOpenAIChatCompletions,
)
from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_tts_api_source import ProviderOpenAITTSAPI
from astrbot.core.provider.sources.request_extra_headers import extra_headers_kwargs
from astrbot.core.provider.sources.vllm_rerank_source import VLLMRerankProvider
from astrbot.core.provider.sources.whisper_api_source import ProviderOpenAIWhisperAPI


@pytest.mark.parametrize(
    "custom_headers", [None, {}, [], "invalid", {"User-Agent": " "}]
)
def test_provider_headers_default_to_current_version(custom_headers):
    assert build_provider_headers(custom_headers) == {
        "User-Agent": f"astrbot/{__version__}"
    }


@pytest.mark.parametrize("name", ["User-Agent", "user-agent", "USER-AGENT"])
def test_provider_headers_preserve_custom_values_without_mutation(name):
    custom = {name: "custom/1.0", "X-Trace-Id": 123}
    original = copy.deepcopy(custom)
    assert build_provider_headers(custom) == {
        "User-Agent": "custom/1.0",
        "X-Trace-Id": "123",
    }
    assert custom == original


def test_drop_sdk_user_agent_ignores_incomplete_clients_and_pops_lowercase_header():
    drop_sdk_user_agent(object())
    drop_sdk_user_agent(
        SimpleNamespace(_api_client=SimpleNamespace(_http_options=SimpleNamespace()))
    )

    headers = {"user-agent": "sdk/1.0", "User-Agent": DEFAULT_USER_AGENT}
    client = SimpleNamespace(
        _api_client=SimpleNamespace(_http_options=SimpleNamespace(headers=headers))
    )
    drop_sdk_user_agent(client)
    assert headers == {"User-Agent": DEFAULT_USER_AGENT}


def test_build_conversation_headers_only_when_id_present():
    assert build_conversation_headers(None) == {}
    assert build_conversation_headers("") == {}
    assert build_conversation_headers("conversation-1") == {
        CONVERSATION_ID_HEADER: "conversation-1"
    }


def test_extra_headers_kwargs_layer_conversation_id():
    assert extra_headers_kwargs(None) == {}
    assert extra_headers_kwargs({"X-Trace": "1"}) == {
        "extra_headers": {"X-Trace": "1"}
    }
    assert extra_headers_kwargs(None, "conversation-1") == {
        "extra_headers": {CONVERSATION_ID_HEADER: "conversation-1"}
    }
    assert extra_headers_kwargs({"X-Trace": "1"}, "conversation-1") == {
        "extra_headers": {
            "X-Trace": "1",
            CONVERSATION_ID_HEADER: "conversation-1",
        }
    }


@pytest.mark.parametrize(
    "provider_cls",
    [
        ProviderOpenAIChatCompletions,
        ProviderOpenAIResponses,
        ProviderAnthropic,
    ],
)
def test_provider_request_extra_headers_include_conversation_id(provider_cls):
    provider = provider_cls.__new__(provider_cls)
    assert provider._request_extra_headers_kwargs("conversation-1") == {
        "extra_headers": {CONVERSATION_ID_HEADER: "conversation-1"}
    }
    assert provider._request_extra_headers_kwargs() == {}


@pytest.fixture
def unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest_asyncio.fixture
async def provider_http_server(unused_tcp_port, monkeypatch):
    """Capture actual SDK requests without contacting external providers."""
    requests = []
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    async def handle(request):
        requests.append(request.headers)
        return web.json_response(
            {
                "object": "list",
                "data": [],
                "models": [],
                "output": {"embeddings": [{"embedding": [0.1], "text_index": 0}]},
            }
        )

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        yield f"http://127.0.0.1:{unused_tcp_port}", requests
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls",
    [
        ProviderOpenAIChatCompletions,
        ProviderOpenAIResponses,
        OpenAIEmbeddingProvider,
        ProviderOpenAITTSAPI,
        ProviderOpenAIWhisperAPI,
        ProviderAnthropic,
        ProviderKimiCode,
        ProviderGoogleGenAI,
        GeminiEmbeddingProvider,
        ProviderGeminiTTSAPI,
    ],
)
@pytest.mark.parametrize("custom_headers", [{}, {"user-agent": "custom/1.0"}])
async def test_provider_sdk_sends_exactly_one_user_agent(
    provider_cls, custom_headers, provider_http_server
):
    base_url, requests = provider_http_server
    config = {
        "id": "test-provider",
        "model": "test-model",
        "key": ["test-key"],
        "api_key": "test-key",
        "api_base": base_url,
        "embedding_api_key": "test-key",
        "embedding_api_base": base_url,
        "gemini_tts_api_key": "test-key",
        "gemini_tts_api_base": base_url,
        "custom_headers": custom_headers,
    }
    original = copy.deepcopy(config)
    provider = provider_cls(config, {})
    try:
        await provider.client.models.list()
        assert len(requests) == 1
        assert requests[0].getall("User-Agent") == [
            custom_headers.get("user-agent", DEFAULT_USER_AGENT)
        ]
        assert config == original
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls",
    [
        BailianRerankProvider,
        VLLMRerankProvider,
        NvidiaEmbeddingProvider,
        NvidiaRerankProvider,
        OllamaEmbeddingProvider,
    ],
)
@pytest.mark.parametrize("custom_headers", [{}, {"USER-AGENT": "custom/1.0"}])
async def test_aiohttp_provider_sends_user_agent(
    provider_cls, custom_headers, provider_http_server
):
    base_url, requests = provider_http_server
    provider = provider_cls(
        {
            "embedding_api_key": "test-key",
            "embedding_api_base": base_url,
            "rerank_api_key": "test-key",
            "rerank_api_base": base_url,
            "custom_headers": custom_headers,
        },
        {},
    )
    try:
        client = provider.client or await provider._get_client()
        async with client.get(base_url) as response:
            assert response.status == 200
        assert requests[0].getall("User-Agent") == [
            custom_headers.get("USER-AGENT", DEFAULT_USER_AGENT)
        ]
    finally:
        await provider.terminate()
