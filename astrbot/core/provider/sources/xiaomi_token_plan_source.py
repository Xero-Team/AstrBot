from astrbot import logger
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter


def _normalized_provider_config(provider_config: dict) -> dict:
    config = dict(provider_config)
    config["api_base"] = "https://token-plan-cn.xiaomimimo.com/anthropic"

    keys = config.get("key", [])
    actual_key = keys[0] if isinstance(keys, list) and keys else keys
    existing_headers = config.get("custom_headers")
    headers = dict(existing_headers) if isinstance(existing_headers, dict) else {}
    if actual_key:
        headers["Authorization"] = f"Bearer {actual_key}"
    config["custom_headers"] = headers
    return config


XIAOMI_TOKEN_PLAN_MODELS = [
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "mimo-v2-flash",
]


@register_provider_adapter("xiaomi_token_plan", "Xiaomi Token Plan 提供商适配器")
class ProviderXiaomiTokenPlan(ProviderAnthropic):
    """Xiaomi Token Plan provider.

    The Token Plan API uses Anthropic-compatible endpoint with Bearer token auth.
    See https://platform.xiaomimimo.com/docs/tokenplan/quick-access
    """

    def __init__(
        self,
        provider_config,
        provider_settings,
    ) -> None:
        provider_config = _normalized_provider_config(provider_config)

        super().__init__(
            provider_config,
            provider_settings,
        )

        configured_model = provider_config.get("model", "mimo-v2.5")
        if configured_model not in XIAOMI_TOKEN_PLAN_MODELS:
            logger.warning(
                f"Configured model {configured_model!r} is not in the known "
                f"Token Plan model list "
                f"({', '.join(XIAOMI_TOKEN_PLAN_MODELS)}). "
                f"The model may still work if your plan supports it. "
                f"If you encounter errors, please check your plan's "
                f"model availability."
            )

        self.set_model(configured_model)

    async def get_models(self) -> list[str]:
        """Return the hard-coded known model list because Token Plan cannot fetch it dynamically."""
        return XIAOMI_TOKEN_PLAN_MODELS.copy()
