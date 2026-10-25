from astrbot.core.provider.sources.xiaomi_token_plan_source import (
    _normalized_provider_config,
)


def test_xiaomi_config_moves_bearer_token_to_a_copy():
    source_headers = {"X-Custom": "value"}
    source = {
        "id": "xiaomi",
        "key": ["secret-token"],
        "custom_headers": source_headers,
    }

    config = _normalized_provider_config(source)

    assert config is not source
    assert config["api_base"] == ("https://token-plan-cn.xiaomimimo.com/anthropic")
    assert config["custom_headers"] == {
        "X-Custom": "value",
        "Authorization": "Bearer secret-token",
    }
    assert source["custom_headers"] == {"X-Custom": "value"}


def test_xiaomi_config_tolerates_non_dict_custom_headers():
    config = _normalized_provider_config(
        {"id": "xiaomi", "key": ["secret-token"], "custom_headers": "invalid"}
    )

    assert config["custom_headers"] == {"Authorization": "Bearer secret-token"}


def test_xiaomi_config_without_key_keeps_existing_headers():
    headers = {"X-Custom": "value"}
    config = _normalized_provider_config({"id": "xiaomi", "custom_headers": headers})

    assert config["custom_headers"] == {"X-Custom": "value"}
    assert headers == {"X-Custom": "value"}


def test_xiaomi_config_without_key_clears_non_dict_headers():
    config = _normalized_provider_config(
        {"id": "xiaomi", "custom_headers": ["not", "a", "dict"]}
    )

    assert config["custom_headers"] == {}
