from ..register import register_provider_adapter
from .openai_chat_completions_source import ProviderOpenAIChatCompletions

IKUNCODE_API_BASE = "https://api.ikuncode.cc/v1"


@register_provider_adapter(
    "ikuncode_chat_completion",
    "IkunCode Chat Completion Provider Adapter",
)
class ProviderIkunCode(ProviderOpenAIChatCompletions):
    """IkunCode provider using its OpenAI-compatible Chat Completions API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        api_base = provider_config.get("api_base")
        if not isinstance(api_base, str) or not api_base.strip():
            provider_config["api_base"] = IKUNCODE_API_BASE
        super().__init__(provider_config, provider_settings)
