import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from anthropic.types import Message, TextBlock, Usage
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

import astrbot.core.provider.sources.anthropic_source as anthropic_source
from astrbot.core.config.default import VERSION
from astrbot.core.exceptions import ProviderResponseError
from astrbot.core.provider.sources.openai_chat_completions_source import (
    ProviderOpenAIChatCompletions,
)
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.opencode_go_chat_source import ProviderOpenCodeGoChat
from astrbot.core.provider.sources.opencode_go_common import (
    OPENCODE_GO_API_BASE,
    OPENCODE_GO_AUX_SESSION,
    OPENCODE_GO_USER_AGENT,
    apply_default_user_agent,
    opencode_go_session_value,
)
from astrbot.core.provider.sources.opencode_go_messages_source import (
    ProviderOpenCodeGoMessages,
)
from astrbot.core.provider.sources.opencode_go_responses_source import (
    ProviderOpenCodeGoResponses,
)


def _hashed_session(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return f"astrbot-{digest}"


def _chat_stream_chunk() -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "go-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
    )


def _chat_completion() -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "go-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
    )


def test_opencode_go_session_value_hashes_known_string():
    session_id = "umo-1"
    value = opencode_go_session_value(session_id)
    assert value == _hashed_session(session_id)
    assert value.startswith("astrbot-")
    assert session_id not in value
    assert len(value) == len("astrbot-") + 32


@pytest.mark.parametrize("session_id", [None, "", "   "])
def test_opencode_go_session_value_blank_uses_aux(session_id):
    assert opencode_go_session_value(session_id) == OPENCODE_GO_AUX_SESSION


def test_opencode_go_user_agent_fill_if_empty():
    filled = apply_default_user_agent({}, OPENCODE_GO_USER_AGENT)
    assert filled["custom_headers"]["User-Agent"] == f"AstrBot/{VERSION}"
    blank = apply_default_user_agent(
        {"custom_headers": {"User-Agent": "  "}},
        OPENCODE_GO_USER_AGENT,
    )
    assert blank["custom_headers"]["User-Agent"] == OPENCODE_GO_USER_AGENT


def test_opencode_go_user_agent_preserved():
    original = {"custom_headers": {"User-Agent": "custom-agent/1.0"}}
    merged = apply_default_user_agent(original, OPENCODE_GO_USER_AGENT)
    assert merged["custom_headers"]["User-Agent"] == "custom-agent/1.0"
    original["custom_headers"]["User-Agent"] = "changed"
    assert merged["custom_headers"]["User-Agent"] == "custom-agent/1.0"


def _make_go_chat(overrides: dict | None = None) -> ProviderOpenCodeGoChat:
    provider_config = {
        "id": "opencode-go-chat",
        "type": "opencode_go_chat_completion",
        "model": "go-model",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenCodeGoChat(
        provider_config=provider_config,
        provider_settings={},
    )


def test_opencode_go_chat_defaults_api_base_and_user_agent():
    provider = _make_go_chat()
    assert provider.provider_config["api_base"] == OPENCODE_GO_API_BASE
    assert provider.custom_headers == {"User-Agent": OPENCODE_GO_USER_AGENT}
    assert issubclass(ProviderOpenCodeGoChat, ProviderOpenAIChatCompletions)


def test_opencode_go_chat_user_agent_preserved_on_client():
    provider = _make_go_chat(
        {"custom_headers": {"User-Agent": "custom-agent/1.0"}},
    )
    assert provider.custom_headers == {"User-Agent": "custom-agent/1.0"}


@pytest.mark.asyncio
async def test_opencode_go_chat_create_extra_headers():
    provider = _make_go_chat()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _chat_completion()

    provider._request_client = lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        assert captured["extra_headers"] == {
            "x-opencode-session": _hashed_session("umo-1"),
        }

        captured.clear()
        await provider.text_chat(prompt="hello")
        assert captured["extra_headers"] == {
            "x-opencode-session": OPENCODE_GO_AUX_SESSION,
        }

        captured.clear()
        await provider.text_chat(prompt="hello", session_id="   ")
        assert captured["extra_headers"] == {
            "x-opencode-session": OPENCODE_GO_AUX_SESSION,
        }
        assert "umo-1" not in captured["extra_headers"]["x-opencode-session"]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_chat_stream_extra_headers():
    provider = _make_go_chat()
    captured = {}

    async def fake_stream():
        yield _chat_stream_chunk()

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_stream()

    provider._request_client = lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    try:
        async for _ in provider.text_chat_stream(prompt="hello", session_id="umo-1"):
            pass
        assert captured["stream"] is True
        assert captured["extra_headers"] == {
            "x-opencode-session": _hashed_session("umo-1"),
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_chat_concurrent_sessions_do_not_race():
    provider = _make_go_chat()
    captured: dict[str, str] = {}

    async def fake_create(**kwargs):
        content = kwargs["messages"][-1]["content"]
        prompt = content if isinstance(content, str) else content[0]["text"]
        await asyncio.sleep(0)
        captured[prompt] = kwargs["extra_headers"]["x-opencode-session"]
        return _chat_completion()

    provider._request_client = lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    try:
        await asyncio.gather(
            provider.text_chat(prompt="alpha", session_id="umo-a"),
            provider.text_chat(prompt="beta", session_id="umo-b"),
        )
        assert captured["alpha"] == _hashed_session("umo-a")
        assert captured["beta"] == _hashed_session("umo-b")
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_chat_get_models_extra_headers():
    provider = _make_go_chat()
    captured = {}

    async def fake_list(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(id="go-model")])

    provider.client.models.list = fake_list
    try:
        models = await provider.get_models()
        assert models == ["go-model"]
        assert captured["extra_headers"] == {
            "x-opencode-session": OPENCODE_GO_AUX_SESSION,
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_chat_create_omits_go_headers():
    provider = ProviderOpenAIChatCompletions(
        provider_config={
            "id": "test-openai",
            "type": "openai_chat_completions",
            "model": "gpt-4o-mini",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _chat_completion()

    provider._request_client = lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        assert "extra_headers" not in captured
        assert provider._request_extra_headers() is None
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_anthropic_create_omits_go_headers(monkeypatch):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider = anthropic_source.ProviderAnthropic(
        provider_config={
            "id": "test-anthropic",
            "type": "anthropic_chat_completion",
            "model": "claude-test",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        assert "extra_headers" not in provider.client.messages.create_calls[0]
        assert provider._request_extra_headers() is None
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_responses_create_omits_go_headers():
    provider = ProviderOpenAIResponses(
        provider_config={
            "id": "test-responses",
            "type": "openai_responses",
            "model": "gpt-test",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    fake_responses = _FakeGoResponses()
    provider._client_for = lambda _key: SimpleNamespace(
        responses=fake_responses,
        models=_FakeGoResponsesModels(),
        conversations=_FakeGoConversations(),
    )
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        assert "extra_headers" not in fake_responses.create_calls[0]
        assert provider._request_extra_headers() is None
    finally:
        await provider.terminate()


class _FakeAnthropicStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._events = [
            SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(type="text_delta", text="Hello"),
            )
        ]
        self._index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event


class _FakeAnthropicMessages:
    def __init__(self):
        self.create_calls = []
        self.stream_calls = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return Message(
            id="msg_fake",
            content=[TextBlock(type="text", text="Hello")],
            model="claude-test",
            role="assistant",
            stop_reason=None,
            stop_sequence=None,
            type="message",
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        return _FakeAnthropicStream(**kwargs)


class _FakeAnthropicModels:
    def __init__(self):
        self.list_calls = []

    async def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(id="claude-go")])


class _FakeAsyncAnthropic:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages = _FakeAnthropicMessages()
        self.models = _FakeAnthropicModels()

    async def close(self):
        return None


def _make_go_messages(monkeypatch, overrides: dict | None = None):
    monkeypatch.setattr(anthropic_source, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider_config = {
        "id": "opencode-go-messages",
        "type": "opencode_go_messages",
        "model": "claude-test",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenCodeGoMessages(
        provider_config=provider_config,
        provider_settings={},
    )


def test_opencode_go_messages_defaults_and_user_agent(monkeypatch):
    provider = _make_go_messages(monkeypatch)
    assert issubclass(ProviderOpenCodeGoMessages, anthropic_source.ProviderAnthropic)
    assert provider.base_url == "https://opencode.ai/zen/go"
    assert provider.client.kwargs["base_url"] == "https://opencode.ai/zen/go"
    assert provider.client.kwargs["default_headers"] == {
        "User-Agent": OPENCODE_GO_USER_AGENT,
    }


def test_opencode_go_messages_user_agent_preserved(monkeypatch):
    provider = _make_go_messages(
        monkeypatch,
        {"custom_headers": {"User-Agent": "custom-agent/1.0"}},
    )
    assert provider.client.kwargs["default_headers"] == {
        "User-Agent": "custom-agent/1.0",
    }


@pytest.mark.asyncio
async def test_opencode_go_messages_create_extra_headers(monkeypatch):
    provider = _make_go_messages(monkeypatch)
    await provider.text_chat(prompt="hello", session_id="umo-1")
    assert provider.client.messages.create_calls[0]["extra_headers"] == {
        "x-opencode-session": _hashed_session("umo-1"),
    }

    await provider.text_chat(prompt="hello")
    assert provider.client.messages.create_calls[1]["extra_headers"] == {
        "x-opencode-session": OPENCODE_GO_AUX_SESSION,
    }


@pytest.mark.asyncio
async def test_opencode_go_messages_stream_extra_headers(monkeypatch):
    provider = _make_go_messages(monkeypatch)
    async for _ in provider.text_chat_stream(prompt="hello", session_id="umo-1"):
        pass
    assert provider.client.messages.stream_calls[0]["extra_headers"] == {
        "x-opencode-session": _hashed_session("umo-1"),
    }


@pytest.mark.asyncio
async def test_opencode_go_messages_get_models_extra_headers(monkeypatch):
    provider = _make_go_messages(monkeypatch)
    models = await provider.get_models()
    assert models == ["claude-go"]
    assert provider.client.models.list_calls[0]["extra_headers"] == {
        "x-opencode-session": OPENCODE_GO_AUX_SESSION,
    }


def _completed_go_response():
    return SimpleNamespace(
        id="resp_1",
        model="go-model",
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=2,
            output_tokens=1,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
        ),
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(type="output_text", text="done", annotations=[])
                ],
            )
        ],
    )


class _EmptyResponsesStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _FakeGoResponses:
    def __init__(self):
        self.create_calls = []
        self.retrieve_calls = []
        self.cancel_calls = []
        self.create_response = _completed_go_response()

    async def create(self, **options):
        self.create_calls.append(options)
        if options.get("stream"):
            return _EmptyResponsesStream()
        return self.create_response

    async def retrieve(self, response_id, **options):
        self.retrieve_calls.append({"response_id": response_id, **options})
        return _completed_go_response()

    async def cancel(self, response_id, **options):
        self.cancel_calls.append({"response_id": response_id, **options})
        return _completed_go_response()


class _FakeGoResponsesModels:
    def __init__(self):
        self.list_calls = []

    async def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(id="go-resp")])


class _FakeGoConversations:
    def __init__(self):
        self.create_calls = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(id="conv_go")


def _make_go_responses(overrides: dict | None = None) -> ProviderOpenCodeGoResponses:
    provider_config = {
        "id": "opencode-go-responses",
        "type": "opencode_go_responses",
        "model": "go-model",
        "key": ["test-key"],
    }
    if overrides:
        provider_config.update(overrides)
    provider = ProviderOpenCodeGoResponses(
        provider_config=provider_config,
        provider_settings={},
    )
    fake_responses = _FakeGoResponses()
    fake_models = _FakeGoResponsesModels()
    fake_conversations = _FakeGoConversations()
    provider._client_for = lambda _key: SimpleNamespace(
        responses=fake_responses,
        models=fake_models,
        conversations=fake_conversations,
    )
    provider._fake_responses = fake_responses
    provider._fake_models = fake_models
    provider._fake_conversations = fake_conversations
    return provider


def test_opencode_go_responses_defaults_api_base_and_user_agent():
    provider = _make_go_responses()
    assert issubclass(ProviderOpenCodeGoResponses, ProviderOpenAIResponses)
    assert provider.provider_config["api_base"] == OPENCODE_GO_API_BASE
    assert provider.custom_headers == {"User-Agent": OPENCODE_GO_USER_AGENT}


def test_opencode_go_responses_user_agent_preserved():
    provider = _make_go_responses(
        {"custom_headers": {"User-Agent": "custom-agent/1.0"}},
    )
    assert provider.custom_headers == {"User-Agent": "custom-agent/1.0"}


@pytest.mark.asyncio
async def test_opencode_go_responses_create_extra_headers():
    provider = _make_go_responses()
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        assert provider._fake_responses.create_calls[0]["extra_headers"] == {
            "x-opencode-session": _hashed_session("umo-1"),
        }

        await provider.text_chat(prompt="hello")
        assert provider._fake_responses.create_calls[1]["extra_headers"] == {
            "x-opencode-session": OPENCODE_GO_AUX_SESSION,
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_responses_stream_kwargs_session():
    provider = _make_go_responses()
    try:
        with pytest.raises(
            ProviderResponseError,
            match="without response.completed",
        ):
            async for _ in provider.text_chat_stream(
                prompt="hello",
                session_id="umo-1",
            ):
                pass
        assert provider._fake_responses.create_calls[0]["extra_headers"] == {
            "x-opencode-session": _hashed_session("umo-1"),
        }
        assert provider._fake_responses.create_calls[0]["stream"] is True
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_responses_get_models_extra_headers():
    provider = _make_go_responses()
    try:
        models = await provider.get_models()
        assert models == ["go-resp"]
        assert provider._fake_models.list_calls[0]["extra_headers"] == {
            "x-opencode-session": OPENCODE_GO_AUX_SESSION,
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_responses_conversation_create_extra_headers():
    provider = _make_go_responses(
        {"responses_state_mode": "conversation", "store": True},
    )
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        expected = {"x-opencode-session": _hashed_session("umo-1")}
        assert provider._fake_conversations.create_calls[0]["extra_headers"] == expected
        assert provider._fake_responses.create_calls[0]["extra_headers"] == expected
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_responses_background_retrieve_extra_headers():
    provider = _make_go_responses(
        {
            "responses_state_mode": "previous_response_id",
            "store": True,
            "responses_background": True,
            "responses_background_poll_interval": 0.01,
        },
    )
    provider._fake_responses.create_response = SimpleNamespace(
        id="resp_bg",
        status="queued",
    )
    try:
        await provider.text_chat(prompt="hello", session_id="umo-1")
        assert provider._fake_responses.retrieve_calls[0]["extra_headers"] == {
            "x-opencode-session": _hashed_session("umo-1"),
        }
        assert provider._fake_responses.retrieve_calls[0]["response_id"] == "resp_bg"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_opencode_go_responses_cancel_extra_headers():
    provider = _make_go_responses(
        {
            "responses_state_mode": "previous_response_id",
            "store": True,
            "responses_background": True,
            "responses_background_poll_interval": 60,
            "responses_background_timeout": 60,
        },
    )
    provider._fake_responses.create_response = SimpleNamespace(
        id="resp_bg",
        status="queued",
    )
    entered_poll = asyncio.Event()
    original_poll = provider._poll_background

    async def poll_wrapper(*args, **kwargs):
        entered_poll.set()
        return await original_poll(*args, **kwargs)

    provider._poll_background = poll_wrapper
    signal = asyncio.Event()
    try:
        task = asyncio.create_task(
            provider.text_chat(
                prompt="hello",
                session_id="umo-1",
                abort_signal=signal,
            )
        )
        await entered_poll.wait()
        signal.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider._fake_responses.cancel_calls[0]["extra_headers"] == {
            "x-opencode-session": _hashed_session("umo-1"),
        }
        assert provider._fake_responses.cancel_calls[0]["response_id"] == "resp_bg"
    finally:
        await provider.terminate()
