from ..register import register_provider_adapter
from .openai_responses_source import ProviderOpenAIResponses
from .opencode_go_common import (
    OPENCODE_GO_API_BASE,
    OPENCODE_GO_USER_AGENT,
    OpenCodeGoSessionMixin,
    apply_default_user_agent,
)


@register_provider_adapter(
    "opencode_go_responses",
    "OpenCode Go Responses Provider Adapter",
)
class ProviderOpenCodeGoResponses(OpenCodeGoSessionMixin, ProviderOpenAIResponses):
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
