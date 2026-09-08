from ..register import register_provider_adapter
from .openai_chat_completions_source import ProviderOpenAIChatCompletions
from .opencode_go_common import (
    OPENCODE_GO_API_BASE,
    OPENCODE_GO_USER_AGENT,
    OpenCodeGoSessionMixin,
    apply_default_user_agent,
)


@register_provider_adapter(
    "opencode_go_chat_completion",
    "OpenCode Go Chat Completions Provider Adapter",
)
class ProviderOpenCodeGoChat(OpenCodeGoSessionMixin, ProviderOpenAIChatCompletions):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        merged_provider_config = dict(provider_config)
        merged_provider_config.setdefault("api_base", OPENCODE_GO_API_BASE)
        merged_provider_config = apply_default_user_agent(
            merged_provider_config,
            OPENCODE_GO_USER_AGENT,
        )
        super().__init__(merged_provider_config, provider_settings)
