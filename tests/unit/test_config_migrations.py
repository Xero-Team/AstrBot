"""Tests for the forward-only configuration migrations."""

from __future__ import annotations

import copy
import json

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.migrations import (
    CONFIG_SCHEMA_REVISION,
    ConfigMigrationError,
    migrate_config_dict,
)


def test_flat_keys_move_to_groups_without_losing_values():
    conf = {
        "log_level": "DEBUG",
        "log_file_enable": True,
        "t2i": True,
        "t2i_word_threshold": 42,
        "t2i_active_template": "custom",
        "kb_names": ["docs"],
        "kb_fusion_top_k": 3,
        "dashboard": {"host": "127.0.0.1"},
    }

    assert migrate_config_dict(conf) is True

    assert conf["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert conf["log"]["level"] == "DEBUG"
    assert conf["log"]["file_enable"] is True
    assert conf["t2i"]["enable"] is True
    assert conf["t2i"]["word_threshold"] == 42
    assert conf["t2i"]["active_template"] == "custom"
    assert conf["knowledge_base"]["names"] == ["docs"]
    assert conf["knowledge_base"]["fusion_top_k"] == 3
    assert conf["dashboard"] == {"host": "127.0.0.1"}
    assert "log_level" not in conf
    assert "t2i_word_threshold" not in conf
    assert "kb_names" not in conf


def test_grouped_values_win_over_flat_legacy_keys():
    conf = {
        "log_level": "DEBUG",
        "log": {"level": "WARNING"},
    }

    assert migrate_config_dict(conf) is True
    assert conf["log"]["level"] == "WARNING"
    assert "log_level" not in conf


def test_null_grouped_value_keeps_flat_legacy_value():
    conf = {
        "log_level": "DEBUG",
        "log": {"level": None},
    }

    assert migrate_config_dict(conf) is True
    assert conf["log"]["level"] == "DEBUG"
    assert "log_level" not in conf


def test_boolean_schema_revision_is_treated_as_unset():
    conf = {
        "schema_revision": True,
        "log_level": "DEBUG",
    }

    assert migrate_config_dict(conf) is True
    assert conf["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert type(conf["schema_revision"]) is int
    assert conf["log"]["level"] == "DEBUG"
    assert "log_level" not in conf


def test_revision_ahead_of_code_is_refused():
    conf = {"schema_revision": CONFIG_SCHEMA_REVISION + 1}

    with pytest.raises(ConfigMigrationError):
        migrate_config_dict(conf)


def test_migration_is_idempotent():
    conf = {"log_level": "DEBUG"}
    assert migrate_config_dict(conf) is True
    snapshot = json.dumps(conf, sort_keys=True)

    assert migrate_config_dict(conf) is False
    assert json.dumps(conf, sort_keys=True) == snapshot


def test_retired_gemini_embedding_model_is_migrated_without_changing_others():
    conf = {
        "schema_revision": 1,
        "provider": [
            {
                "type": "gemini_embedding",
                "embedding_model": "gemini-embedding-exp-03-07",
            },
            {
                "type": "gemini_embedding",
                "embedding_model": "custom-embedding-model",
            },
            {"type": "openai_embedding", "embedding_model": "text-embedding-3"},
        ],
    }

    assert migrate_config_dict(conf) is True
    assert conf["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert conf["provider"] == [
        {"type": "gemini_embedding", "embedding_model": "gemini-embedding-001"},
        {"type": "gemini_embedding", "embedding_model": "custom-embedding-model"},
        {"type": "openai_embedding", "embedding_model": "text-embedding-3"},
    ]


def _nested_policy(
    *,
    allow_execution: bool,
    filesystem_scope: str,
    mode: str,
    private: bool,
    loopback: bool,
    socket_mode: str,
) -> dict:
    return {
        "allow_execution": allow_execution,
        "filesystem_scope": filesystem_scope,
        "network": {
            "mode": mode,
            "allowed_domains": [],
            "denied_domains": [],
            "allow_private_network": private,
            "allow_loopback": loopback,
        },
        "filesystem": {"deny_read": [], "deny_write": []},
        "unix_sockets": {"mode": socket_mode, "allowed_paths": []},
    }


def test_revision_six_migrates_saved_flat_local_permission_policies():
    permissions = {
        "member": {
            "allow_execution": False,
            "allow_network": False,
            "filesystem_scope": "none",
        },
        "admin": {
            "allow_execution": True,
            "allow_network": True,
            "filesystem_scope": "host",
        },
    }
    conf = {
        "schema_revision": 2,
        "provider_settings": {
            "computer_use_local_permissions": copy.deepcopy(permissions)
        },
    }

    assert migrate_config_dict(conf) is True
    assert conf["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert conf["provider_settings"]["computer_use_local_permissions"] == {
        "member": _nested_policy(
            allow_execution=False,
            filesystem_scope="none",
            mode="off",
            private=False,
            loopback=False,
            socket_mode="deny",
        ),
        "admin": _nested_policy(
            allow_execution=True,
            filesystem_scope="host",
            mode="unrestricted",
            private=True,
            loopback=True,
            socket_mode="allow_all",
        ),
    }
    assert (
        "allow_network"
        not in conf["provider_settings"]["computer_use_local_permissions"]["member"]
    )


def test_local_permission_migration_preserves_partial_roles():
    member = {
        "allow_execution": True,
        "allow_network": False,
        "filesystem_scope": "workspace",
    }
    conf = {
        "schema_revision": 2,
        "provider_settings": {
            "computer_use_local_permissions": {"member": member.copy()}
        },
    }

    assert migrate_config_dict(conf) is True
    migrated = conf["provider_settings"]["computer_use_local_permissions"]["member"]
    assert migrated == _nested_policy(
        allow_execution=True,
        filesystem_scope="workspace",
        mode="off",
        private=False,
        loopback=False,
        socket_mode="deny",
    )


def test_local_permission_migration_handles_missing_flat_value():
    conf = {
        "schema_revision": 2,
        "provider_settings": {
            "computer_use_local_permissions": {
                "member": {"filesystem_scope": "workspace"}
            }
        },
    }

    assert migrate_config_dict(conf) is True
    migrated = conf["provider_settings"]["computer_use_local_permissions"]["member"]
    assert migrated["network"]["mode"] == "off"
    assert migrated["network"]["allow_private_network"] is False
    assert migrated["network"]["allow_loopback"] is False
    assert migrated["unix_sockets"] == {"mode": "deny", "allowed_paths": []}


def test_local_permission_migration_is_idempotent():
    conf = {
        "schema_revision": 5,
        "provider_settings": {
            "computer_use_local_permissions": {
                "admin": {"allow_execution": True, "allow_network": True}
            }
        },
    }
    assert migrate_config_dict(conf) is True
    snapshot = json.dumps(conf, sort_keys=True)
    assert migrate_config_dict(conf) is False
    assert json.dumps(conf, sort_keys=True) == snapshot


def test_local_sandbox_migration_round_trips_through_config_store(tmp_path):
    config_path = tmp_path / "cmd_config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_revision": 5,
                "provider_settings": {
                    "computer_use_local_permissions": {
                        "admin": {
                            "allow_execution": True,
                            "allow_network": True,
                            "filesystem_scope": "host",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    AstrBotConfig(config_path=str(config_path))
    stored = json.loads(config_path.read_text(encoding="utf-8-sig"))
    policy = stored["provider_settings"]["computer_use_local_permissions"]["admin"]
    assert stored["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert "allow_network" not in policy
    assert policy["network"]["mode"] == "unrestricted"
    assert policy["network"]["allow_private_network"] is True
    assert policy["network"]["allow_loopback"] is True
    assert policy["unix_sockets"] == {"mode": "allow_all", "allowed_paths": []}


def test_retired_sandbox_runtime_fails_closed_to_none():
    conf = {
        "schema_revision": 4,
        "provider_settings": {
            "computer_use_runtime": "sandbox",
            "sandbox": {"booter": "shipyard_neo"},
            "computer_use_local_permissions": {},
        },
        "btw": {"work_loop": {"computer_use_runtime": "sandbox"}},
    }

    assert migrate_config_dict(conf) is True
    assert conf["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert conf["provider_settings"]["computer_use_runtime"] == "none"
    assert "sandbox" not in conf["provider_settings"]
    assert conf["btw"]["work_loop"]["computer_use_runtime"] == "none"


def test_retired_sandbox_runtime_preserves_local_and_none():
    conf = {
        "schema_revision": 4,
        "provider_settings": {"computer_use_runtime": "local"},
        "btw": {"work_loop": {"computer_use_runtime": "inherit"}},
    }

    assert migrate_config_dict(conf) is True
    assert conf["provider_settings"]["computer_use_runtime"] == "local"
    assert conf["btw"]["work_loop"]["computer_use_runtime"] == "inherit"


def test_config_load_migrates_and_persists_flat_file(tmp_path):
    config_path = tmp_path / "cmd_config.json"
    config_path.write_text(
        json.dumps(
            {
                "log_level": "DEBUG",
                "t2i_word_threshold": 7,
                "kb_names": ["legacy-kb"],
                "dashboard": {"host": "127.0.0.1"},
            },
        ),
        encoding="utf-8",
    )

    config = AstrBotConfig(config_path=str(config_path))

    assert config["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert config["log"]["level"] == "DEBUG"
    assert config["t2i"]["word_threshold"] == 7
    assert config["knowledge_base"]["names"] == ["legacy-kb"]

    stored = json.loads(config_path.read_text(encoding="utf-8-sig"))
    assert stored["schema_revision"] == CONFIG_SCHEMA_REVISION
    assert stored["log"]["level"] == "DEBUG"
    assert stored["t2i"]["word_threshold"] == 7
    assert "log_level" not in stored
    assert "t2i_word_threshold" not in stored
