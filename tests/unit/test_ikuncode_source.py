from unittest.mock import patch

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.ikuncode_source import (
    IKUNCODE_API_BASE,
    ProviderIkunCode,
)
from astrbot.core.provider.sources.openai_chat_completions_source import (
    ProviderOpenAIChatCompletions,
)


def test_ikuncode_provider_defaults_blank_api_base_without_network_access():
    provider_config = {"api_base": "  "}

    with patch.object(ProviderOpenAIChatCompletions, "__init__", return_value=None):
        ProviderIkunCode(provider_config, {})

    assert provider_config["api_base"] == IKUNCODE_API_BASE


def test_ikuncode_provider_preserves_custom_api_base_without_network_access():
    custom_api_base = "https://ikuncode.example/v1"
    provider_config = {"api_base": custom_api_base}

    with patch.object(ProviderOpenAIChatCompletions, "__init__", return_value=None):
        ProviderIkunCode(provider_config, {})

    assert provider_config["api_base"] == custom_api_base


def test_ikuncode_provider_template_has_requested_defaults():
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["IkunCode"]

    assert template == {
        "id": "ikuncode",
        "provider": "ikuncode",
        "type": "ikuncode_chat_completion",
        "provider_type": "chat_completion",
        "enable": True,
        "key": [],
        "timeout": 120,
        "api_base": IKUNCODE_API_BASE,
        "proxy_mode": "inherit",
        "proxy_url": "",
        "custom_headers": {},
    }
