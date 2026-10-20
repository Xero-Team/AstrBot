from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field
from typing import Any

from astrbot.core.agent.chat_model import ChatModel
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.astr_agent_run_util import AgentRunner
from astrbot.core.config.agent_runner import coerce_provider_ids
from astrbot.core.utils.config_number import coerce_int_config


@dataclass(slots=True)
class MainAgentBuildConfig:
    """The main agent build configuration.
    Most of the configs can be found in the cmd_config.json"""

    tool_call_timeout: int
    """The timeout (in seconds) for a tool call.
    When the tool call exceeds this time,
    a timeout error as a tool result will be returned.
    """
    tool_schema_mode: str = "full"
    """The tool schema mode, can be 'full' or 'skills-like'."""
    streaming_response: bool = True
    """Whether to use streaming response."""
    sanitize_context_by_modalities: bool = False
    """Whether to sanitize the context based on the provider's supported modalities.
    This will remove unsupported message types(e.g. image) from the context to prevent issues."""
    kb_agentic_mode: bool = False
    """Whether to use agentic mode for knowledge base retrieval.
    This will inject the knowledge base query tool into the main agent's toolset to allow dynamic querying."""
    context_limit_reached_strategy: str = "llm_compress"
    """The strategy to handle context length limit reached."""
    llm_compress_instruction: str = ""
    """The instruction for compression in llm_compress strategy."""
    llm_compress_keep_recent_ratio: float = 0.15
    """Percent of current context tokens to keep as exact recent context during llm_compress strategy."""
    llm_compress_provider_id: str = ""
    """The provider ID for the LLM used in context compression."""
    max_context_length: int = 50
    """The maximum number of turns to keep in context. -1 means no limit.
    This enforce max turns before compression"""
    dequeue_context_length: int = 10
    """The number of oldest turns to remove when context length limit is reached."""
    fallback_max_context_tokens: int = 128000
    """Fallback context limit when the runtime metadata catalog has no model entry."""
    llm_safety_mode: bool = True
    """This will inject healthy and safe system prompt into the main agent,
    to prevent LLM output harmful information"""
    safety_mode_strategy: str = "system_prompt"
    computer_use_runtime: str = "none"
    """The runtime for agent computer use: none, local, or sandbox."""
    allow_computer_tools: bool = True
    """Whether request tools may include computer capabilities."""
    sandbox_cfg: dict = field(default_factory=dict)
    add_cron_tools: bool = True
    """This will add cron job management tools to the main agent for proactive cron job execution."""
    provider_settings: dict = field(default_factory=dict)
    provider_id_override: str = ""
    """Preferred chat provider for this request, read from persisted config.

    A preference, not a requirement: an id that no longer resolves to a chat
    model is skipped with a warning, and selection continues with the request's
    own provider choice and then the session/profile default. This is set by
    the BTW loop models. A provider chosen for the request itself arrives as
    ``selected_provider`` instead, and that one fails loudly.
    """
    fallback_provider_ids: list[str] = field(default_factory=list)
    request_max_retries: int = 5
    subagent_orchestrator: dict = field(default_factory=dict)
    timezone: str | None = None
    max_quoted_fallback_images: int = 20
    """Maximum number of images injected from quoted-message fallback extraction."""


@dataclass(slots=True)
class MainAgentBuildResult:
    agent_runner: AgentRunner
    provider_request: ProviderRequest
    provider: ChatModel
    reset_coro: Coroutine | None = None


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def local_agent_runtime_from_profile(
    profile_config: Mapping[str, Any] | None,
    **overrides: Any,
) -> tuple[MainAgentBuildConfig, int]:
    """Assemble local-agent build config and step bound from a profile.

    Reads ``agent_runner.config`` for model fallback/retries, prompt,
    compression, and misc fields. Callers may override individual
    ``MainAgentBuildConfig`` fields.

    Args:
        profile_config: Profile configuration containing ``agent_runner``.
        **overrides: Fields forwarded to ``MainAgentBuildConfig``.

    Returns:
        The build config and the ``max_steps`` bound for ``step_until_done``.
    """
    profile = _mapping(profile_config)
    agent_runner = _mapping(profile.get("agent_runner"))
    runner_config = _mapping(agent_runner.get("config"))
    model_config = _mapping(runner_config.get("model"))
    compression_config = _mapping(runner_config.get("compression"))
    misc_config = _mapping(runner_config.get("misc"))
    settings = _mapping(profile.get("provider_settings"))
    proactive_cfg = _mapping(settings.get("proactive_capability"))

    max_context_length = compression_config.get("max_turns", -1)
    if not isinstance(max_context_length, int) or isinstance(max_context_length, bool):
        max_context_length = -1
    configured_trim = coerce_int_config(
        compression_config.get("trim_turns", 1),
        default=1,
        min_value=1,
        field_name="agent_runner.config.compression.trim_turns",
        warn=False,
    )
    if max_context_length == -1:
        dequeue_context_length = configured_trim
    else:
        dequeue_context_length = min(configured_trim, max_context_length - 1)
    if dequeue_context_length <= 0:
        dequeue_context_length = 1

    tool_schema_mode = misc_config.get("tool_schema_mode", "full")
    if tool_schema_mode not in ("skills_like", "full"):
        tool_schema_mode = "full"

    max_steps = coerce_int_config(
        misc_config.get("max_steps", 128),
        default=128,
        min_value=1,
        field_name="agent_runner.config.misc.max_steps",
    )
    kwargs: dict[str, Any] = {
        "tool_call_timeout": coerce_int_config(
            misc_config.get("tool_call_timeout", 120),
            default=120,
            min_value=1,
            field_name="agent_runner.config.misc.tool_call_timeout",
            warn=False,
        ),
        "tool_schema_mode": tool_schema_mode,
        "sanitize_context_by_modalities": bool(
            misc_config.get("sanitize_context_by_modalities", False)
        ),
        "kb_agentic_mode": bool(
            (profile.get("knowledge_base") or {}).get("agentic_mode", False)
        ),
        "context_limit_reached_strategy": compression_config.get(
            "overflow_strategy", "llm_compress"
        ),
        "llm_compress_instruction": compression_config.get("instruction", "") or "",
        "llm_compress_keep_recent_ratio": compression_config.get(
            "keep_recent_ratio", 0.15
        ),
        "llm_compress_provider_id": compression_config.get("provider_id", "") or "",
        "max_context_length": max_context_length,
        "dequeue_context_length": dequeue_context_length,
        "fallback_max_context_tokens": compression_config.get(
            "fallback_max_tokens", 128000
        ),
        "llm_safety_mode": runner_config.get("safety_mode", True),
        "safety_mode_strategy": runner_config.get(
            "safety_mode_strategy", "system_prompt"
        ),
        "computer_use_runtime": settings.get("computer_use_runtime", "none"),
        "sandbox_cfg": _mapping(settings.get("sandbox")),
        "add_cron_tools": proactive_cfg.get("add_cron_tools", True),
        "provider_settings": settings,
        "fallback_provider_ids": coerce_provider_ids(
            model_config.get("fallback_provider_ids", [])
        ),
        "request_max_retries": coerce_int_config(
            model_config.get("request_max_retries", 5),
            default=5,
            min_value=1,
            field_name="agent_runner.config.model.request_max_retries",
            warn=False,
        ),
        "subagent_orchestrator": _mapping(profile.get("subagent_orchestrator")),
        "timezone": profile.get("timezone"),
        "max_quoted_fallback_images": settings.get("max_quoted_fallback_images", 20),
    }
    kwargs.update(overrides)
    return MainAgentBuildConfig(**kwargs), max_steps
