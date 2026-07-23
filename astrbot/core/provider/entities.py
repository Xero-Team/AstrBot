from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any


class ProviderType(enum.Enum):
    CHAT_COMPLETION = "chat_completion"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass
class ProviderMeta:
    """The basic metadata of a provider instance."""

    id: str
    """the unique id of the provider instance that user configured"""
    model: str | None
    """the model name of the provider instance currently used"""
    type: str
    """the name of the provider adapter, such as openai, ollama"""
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION
    """the capability type of the provider adapter"""


@dataclass
class ProviderMetaData(ProviderMeta):
    """The metadata of a provider adapter for registration."""

    desc: str = ""
    """the short description of the provider adapter"""
    cls_type: Any = None
    """the class type of the provider adapter"""
    default_config_tmpl: dict | None = None
    """the default configuration template of the provider adapter"""
    provider_display_name: str | None = None
    """the display name of the provider shown in the WebUI configuration page; if empty, the type is used"""


@dataclass
class RerankResult:
    index: int
    """The index in the candidate list."""
    relevance_score: float
    """The relevance score."""
