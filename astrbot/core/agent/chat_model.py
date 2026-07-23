"""Minimal chat-model contract consumed by the local agent runtime."""

from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable

from .llm_types import LLMResponse


class ChatModelMetadata(Protocol):
    """Read-only model metadata used by Agent telemetry."""

    @property
    def id(self) -> str:
        """Return the configured provider identifier."""
        ...

    @property
    def type(self) -> str:
        """Return the provider adapter type."""
        ...


@runtime_checkable
class ChatModel(Protocol):
    """The provider-neutral chat capabilities required by Agent code."""

    provider_config: dict[str, Any]

    def get_model(self) -> str:
        """Return the active model identifier."""
        ...

    def meta(self) -> ChatModelMetadata:
        """Return metadata used by Agent telemetry."""
        ...

    async def text_chat(self, **kwargs: Any) -> LLMResponse:
        """Complete one non-streaming chat request."""
        ...

    def text_chat_stream(self, **kwargs: Any) -> AsyncGenerator[LLMResponse]:
        """Stream one chat request as LLM response chunks."""
        ...
