import copy
import json

import pytest

from astrbot.core.config.agent_runner import (
    AGENT_RUNNER_CONFIG_DEFAULTS,
    get_agent_runner_config_default,
    get_prompt_id,
    normalize_agent_runner,
    normalize_agent_runner_for_load,
)
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG


@pytest.mark.parametrize(
    "runner_type", ["local", "dify", "coze", "dashscope", "deerflow"]
)
def test_agent_runner_defaults_are_isolated_and_normalized(runner_type: str):
    first = get_agent_runner_config_default(runner_type)
    second = get_agent_runner_config_default(runner_type)

    first["test_mutation"] = True

    assert second == AGENT_RUNNER_CONFIG_DEFAULTS[runner_type]
    assert normalize_agent_runner({"runner_type": runner_type, "config": second}) == {
        "runner_type": runner_type,
        "config": second,
    }
    if runner_type != "local":
        assert second["prompt_id"] == "default"
        assert second["max_steps"] == 128
        assert second["proxy_mode"] == "inherit"
        assert second["proxy_url"] == ""
        assert "proxy" not in second


def test_switching_runner_type_discards_previous_runner_fields():
    normalized = normalize_agent_runner(
        {
            "runner_type": "dify",
            "config": {
                "provider_id": "legacy-provider",
                "prompt_id": "legacy-prompt",
                "model": {"provider_id": "chat-model"},
                "dify_api_key": "secret",
                "unexpected": True,
            },
        }
    )

    assert normalized["config"] == {
        **get_agent_runner_config_default("dify"),
        "dify_api_key": "secret",
        "prompt_id": "legacy-prompt",
    }
    assert "provider_id" not in normalized["config"]
    assert "model" not in normalized["config"]


def test_agent_request_normalizes_incomplete_runner_config():
    normalized = normalize_agent_runner(
        {
            "runner_type": "dify",
            "config": {"dify_api_key": "saved-key"},
        }
    )

    assert normalized == {
        "runner_type": "dify",
        "config": {
            **get_agent_runner_config_default("dify"),
            "dify_api_key": "saved-key",
        },
    }


@pytest.mark.parametrize(
    "runner_type", ["local", "dify", "coze", "dashscope", "deerflow"]
)
def test_each_runner_configuration_round_trips(tmp_path, runner_type: str):
    config = copy.deepcopy(DEFAULT_CONFIG)
    expected = {
        "runner_type": runner_type,
        "config": get_agent_runner_config_default(runner_type),
    }
    config["agent_runner"] = expected
    config_path = tmp_path / f"{runner_type}.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = AstrBotConfig(config_path=str(config_path))
    loaded.save_config()
    reloaded = AstrBotConfig(config_path=str(config_path))

    assert reloaded["agent_runner"] == expected


def test_new_agent_runner_config_is_authoritative_and_opaque_on_reload(tmp_path):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["agent_runner_type"] = "coze"
    config["agent_runner"] = {
        "runner_type": "dify",
        "config": {
            **get_agent_runner_config_default("dify"),
            "dify_api_key": "saved-key",
            "variables": {"nested": {"value": 1}},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = AstrBotConfig(config_path=str(config_path))

    assert loaded["agent_runner"]["runner_type"] == "dify"
    assert loaded["agent_runner"]["config"]["dify_api_key"] == "saved-key"
    assert loaded["agent_runner"]["config"]["variables"] == {"nested": {"value": 1}}
    assert "agent_runner_type" not in loaded["provider_settings"]


def test_string_proxy_is_upgraded_to_three_state():
    custom = normalize_agent_runner(
        {
            "runner_type": "coze",
            "config": {"proxy": "http://proxy.example:8080"},
        }
    )
    inherit = normalize_agent_runner(
        {
            "runner_type": "coze",
            "config": {"proxy": ""},
        }
    )

    assert custom["config"]["proxy_mode"] == "custom"
    assert custom["config"]["proxy_url"] == "http://proxy.example:8080"
    assert "proxy" not in custom["config"]
    assert inherit["config"]["proxy_mode"] == "inherit"
    assert inherit["config"]["proxy_url"] == ""
    assert "proxy" not in inherit["config"]

    overridden = normalize_agent_runner(
        {
            "runner_type": "coze",
            "config": {
                "proxy": "http://legacy.example:8080",
                "proxy_mode": "inherit",
                "proxy_url": "",
            },
        }
    )
    assert overridden["config"]["proxy_mode"] == "custom"
    assert overridden["config"]["proxy_url"] == "http://legacy.example:8080"


def test_normalize_drops_non_string_fallback_ids():
    normalized = normalize_agent_runner(
        {
            "runner_type": "local",
            "config": {
                "model": {
                    "fallback_provider_ids": [
                        "keep-me",
                        {"id": "nope"},
                        12,
                        "",
                        None,
                    ]
                }
            },
        }
    )

    assert normalized["config"]["model"]["fallback_provider_ids"] == ["keep-me"]


def test_unknown_runner_type_on_load_becomes_local(tmp_path):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["agent_runner"] = {"runner_type": "unknown-runner", "config": {}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = AstrBotConfig(config_path=str(config_path))

    assert loaded["agent_runner"] == {
        "runner_type": "local",
        "config": get_agent_runner_config_default("local"),
    }


def test_normalize_for_load_repairs_invalid_runner_without_raising():
    repaired = normalize_agent_runner_for_load({"runner_type": "nope", "config": {}})
    assert repaired["runner_type"] == "local"
    assert repaired["config"] == get_agent_runner_config_default("local")


def test_get_prompt_id_reads_local_and_third_party_fields():
    assert (
        get_prompt_id(
            {
                "runner_type": "local",
                "config": {"prompt_id": "developer"},
            }
        )
        == "developer"
    )
    assert (
        get_prompt_id({"runner_type": "dify", "config": {"prompt_id": "operator"}})
        == "operator"
    )
    assert get_prompt_id({"runner_type": "dify", "config": {}}) == "default"
    assert get_prompt_id({"runner_type": "dify", "config": {"prompt_id": ""}}) == (
        "default"
    )
