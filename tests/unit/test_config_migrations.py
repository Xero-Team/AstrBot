"""Tests for the forward-only configuration migrations."""

from __future__ import annotations

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
