"""Tests for dashboard route utility helpers."""

import pytest
from pydantic import ValidationError

from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.dashboard.schemas import (
    ConfigContentRequest,
    ConfigProfileCreateRequest,
    _reject_removed_config_fields,
)
from astrbot.dashboard.services.config_service import get_schema_item, validate_config


def test_get_schema_item_template_list_file_item():
    schema = {
        "demo_templates": {
            "type": "template_list",
            "templates": {
                "api_provider": {
                    "items": {
                        "tls_certificate_files": {"type": "file"},
                    },
                },
            },
        },
    }

    meta = get_schema_item(
        schema,
        "demo_templates.templates.api_provider.tls_certificate_files",
    )

    assert meta == {"type": "file"}


def test_get_schema_item_nested_template_list_file_item():
    schema = {
        "group": {
            "type": "object",
            "items": {
                "demo_templates": {
                    "type": "template_list",
                    "templates": {
                        "nested_profile": {
                            "items": {
                                "profile": {
                                    "type": "object",
                                    "items": {
                                        "attachments": {"type": "file"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    meta = get_schema_item(
        schema,
        "group.demo_templates.templates.nested_profile.profile.attachments",
    )

    assert meta == {"type": "file"}


def test_validate_config_template_list_file_path_uses_template_schema_path():
    schema = {
        "demo_templates": {
            "type": "template_list",
            "templates": {
                "api_provider": {
                    "items": {
                        "tls_certificate_files": {"type": "file"},
                    },
                },
            },
        },
    }
    data = {
        "demo_templates": [
            {
                "__template_key": "api_provider",
                "tls_certificate_files": [
                    "files/demo_templates/templates/api_provider/tls_certificate_files/cert.pem"
                ],
            }
        ]
    }

    errors, validated = validate_config(data, schema, is_core=False)

    assert errors == []
    assert validated == data


def test_validate_config_dict_defaults_are_independent():
    schema = {
        "first": {"type": "dict"},
        "second": {"type": "dict"},
    }
    data = {"first": None, "second": None}

    errors, validated = validate_config(data, schema, is_core=False)

    assert errors == []
    assert validated["first"] == {}
    assert validated["second"] == {}
    assert validated["first"] is not validated["second"]

    validated["first"]["changed"] = True

    assert validated["second"] == {}


def test_reject_removed_config_fields_walks_nested_dicts_and_lists():
    with pytest.raises(ValueError, match="group_wake_policy"):
        _reject_removed_config_fields(
            {"platform_settings": {"group_wake_policy": "mention"}}
        )
    with pytest.raises(ValueError, match="admins_id"):
        _reject_removed_config_fields({"platform": [{"id": "bot", "admins_id": []}]})
    accepted = {"platform_settings": {"unique_session": False}}
    assert _reject_removed_config_fields(accepted) == accepted


def test_config_content_request_rejects_nested_group_wake_policy():
    with pytest.raises(ValidationError, match="group_wake_policy"):
        ConfigContentRequest.model_validate(
            {"platform_settings": {"group_wake_policy": "mention"}}
        )
    with pytest.raises(ValidationError, match="group_wake_policy"):
        ConfigProfileCreateRequest.model_validate(
            {
                "name": "wake-profile",
                "config": {"platform_settings": {"group_wake_policy": "mention"}},
            }
        )


def test_validate_config_core_keeps_default_keys_and_drops_unknown():
    data = {
        "dashboard": {"enable": True},
        "not_a_real_key": 1,
        "platform_settings": {
            "unique_session": False,
            "group_wake_policy": "mention",
        },
        "agent_runner": {
            "runner_type": "local",
            "config": {"custom_runner_key": 1},
        },
    }

    errors, validated = validate_config(data, CONFIG_METADATA_2, is_core=True)

    assert errors == []
    assert "not_a_real_key" not in validated
    assert validated["dashboard"]["enable"] is True
    assert "group_wake_policy" not in validated["platform_settings"]
    assert validated["platform_settings"]["unique_session"] is False
    assert validated["agent_runner"]["config"]["custom_runner_key"] == 1
