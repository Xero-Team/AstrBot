from dataclasses import dataclass

from ..chat_model import ChatModel


@dataclass
class ContextConfig:
    """Context configuration class."""

    max_context_tokens: int = 0
    """Maximum number of context tokens. <= 0 means no limit."""
    enforce_max_turns: int = -1  # -1 means no limit
    """Maximum number of conversation turns to keep. -1 means no limit. Executed before compression."""
    truncate_turns: int = 1
    """Number of conversation turns to discard at once when truncation is triggered.
    Two processes will use this value:

    1. Enforce max turns truncation.
    2. Truncation by turns compression strategy.
    """
    llm_compress_instruction: str | None = None
    """Instruction prompt for LLM-based compression."""
    llm_compress_keep_recent_ratio: float = 0.15
    """Percent of current context tokens to keep as exact recent context during LLM-based compression."""
    llm_compress_provider: ChatModel | None = None
    """Chat model used for compression tasks. If None, truncation is used."""
