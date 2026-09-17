"""ID-whitelist config migrates onto unlisted-session overlays."""

from __future__ import annotations

import json
from typing import Any

import pytest

from astrbot.core.auth.admission import SESSION_SERVICE_CONFIG_KEY
from astrbot.core.config.admission_migration import (
    apply_pending_session_allows,
    migrate_admission_on_load,
    pending_session_allows_from_whitelist,
    pending_session_allows_sidecar_path,
)
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG


class _Preferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], Any] = {}

    async def session_get(self, umo: str, key: str, default: Any = None) -> Any:
        return self.values.get((umo, key), default)

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        self.values[(umo, key)] = value


def test_bare_whitelist_ids_expand_to_group_keys_per_platform():
    keys = pending_session_allows_from_whitelist(
        ["room-a", "  ", "room-a"],
        ["napcat", "telegram"],
    )

    assert keys == [
        "session:napcat:group:room-a",
        "session:telegram:group:room-a",
    ]


def test_umo_whitelist_entries_mint_canonical_session_keys():
    keys = pending_session_allows_from_whitelist(
        [
            "napcat:GroupMessage:123",
            "napcat:FriendMessage:42",
            "session:qq:group:already",
        ],
        ["unused"],
    )

    assert keys == [
        "session:napcat:group:123",
        "session:napcat:private:42",
        "session:qq:group:already",
    ]


def test_unique_session_umo_entries_are_not_rewritten_to_group_id():
    keys = pending_session_allows_from_whitelist(
        ["napcat:GroupMessage:user-1_room-a"],
        ["napcat"],
    )

    assert keys == ["session:napcat:group:user-1_room-a"]


def test_bare_ids_are_skipped_when_the_profile_has_no_platforms():
    keys = pending_session_allows_from_whitelist(["room-a"], [])

    assert keys == []


def test_empty_or_disabled_whitelist_becomes_unlisted_allow(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.core.config.admission_migration.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    config = {
        "platform_settings": {
            "enable_id_white_list": False,
            "id_whitelist": ["room-a"],
        },
        "platform": [{"id": "napcat"}],
    }

    assert migrate_admission_on_load(config, tmp_path / "cmd_config.json") is True
    assert config["admission"]["unlisted_sessions"] == "allow"
    assert "id_whitelist" not in config["platform_settings"]
    assert not pending_session_allows_sidecar_path().exists()


def test_enabled_nonempty_whitelist_becomes_deny_and_pending_keys(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.core.config.admission_migration.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    config = {
        "platform_settings": {
            "enable_id_white_list": True,
            "id_whitelist": ["room-a", "napcat:FriendMessage:42"],
            "id_whitelist_log": True,
            "wl_ignore_admin_on_group": True,
            "wl_ignore_admin_on_friend": True,
        },
        "platform": [{"id": "napcat"}, {"id": "telegram"}],
    }

    assert migrate_admission_on_load(config, tmp_path / "cmd_config.json") is True
    assert config["admission"]["unlisted_sessions"] == "deny"
    for key in (
        "enable_id_white_list",
        "id_whitelist",
        "id_whitelist_log",
        "wl_ignore_admin_on_group",
        "wl_ignore_admin_on_friend",
    ):
        assert key not in config["platform_settings"]
    pending = json.loads(pending_session_allows_sidecar_path().read_text())
    assert pending == [
        "session:napcat:group:room-a",
        "session:telegram:group:room-a",
        "session:napcat:private:42",
    ]


def test_missing_whitelist_fields_do_not_rewrite_admission(tmp_path):
    config = {"platform_settings": {"unique_session": False}}

    assert migrate_admission_on_load(config, tmp_path / "unused.json") is False
    assert "admission" not in config


@pytest.mark.asyncio
async def test_apply_pending_session_allows_merges_and_clears_sidecar(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.core.config.admission_migration.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    sidecar = pending_session_allows_sidecar_path()
    sidecar.write_text(
        json.dumps(
            [
                "session:napcat:group:room-a",
                "session:napcat:private:42",
            ]
        ),
        encoding="utf-8",
    )
    preferences = _Preferences()
    preferences.values[("session:napcat:private:42", SESSION_SERVICE_CONFIG_KEY)] = {
        "llm_enabled": False,
        "tts_enabled": True,
        "persona_id": "cool",
    }

    applied = await apply_pending_session_allows(preferences)

    assert applied == 2
    assert preferences.values[
        ("session:napcat:group:room-a", SESSION_SERVICE_CONFIG_KEY)
    ] == {"session_enabled": True}
    assert preferences.values[
        ("session:napcat:private:42", SESSION_SERVICE_CONFIG_KEY)
    ] == {
        "llm_enabled": False,
        "tts_enabled": True,
        "persona_id": "cool",
        "session_enabled": True,
    }
    assert not sidecar.exists()


@pytest.mark.asyncio
async def test_apply_pending_keeps_existing_session_enabled_bool(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.core.config.admission_migration.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    sidecar = pending_session_allows_sidecar_path()
    sidecar.write_text(
        json.dumps(["session:napcat:group:room-a"]),
        encoding="utf-8",
    )
    preferences = _Preferences()
    preferences.values[("session:napcat:group:room-a", SESSION_SERVICE_CONFIG_KEY)] = {
        "session_enabled": False,
        "llm_enabled": False,
    }

    applied = await apply_pending_session_allows(preferences)

    assert applied == 1
    assert preferences.values[
        ("session:napcat:group:room-a", SESSION_SERVICE_CONFIG_KEY)
    ] == {
        "session_enabled": False,
        "llm_enabled": False,
    }
    assert not sidecar.exists()


def test_astrbot_config_load_migrates_whitelist_before_integrity_strip(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "astrbot.core.config.admission_migration.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    config_path = tmp_path / "cmd_config.json"
    config_path.write_text(
        json.dumps(
            {
                "config_version": 3,
                "platform": [{"id": "napcat", "type": "aiocqhttp", "enable": True}],
                "platform_settings": {
                    "enable_id_white_list": True,
                    "id_whitelist": ["room-a"],
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = AstrBotConfig(config_path=str(config_path), default_config=DEFAULT_CONFIG)

    assert loaded["admission"]["unlisted_sessions"] == "deny"
    assert "id_whitelist" not in loaded["platform_settings"]
    pending = json.loads(pending_session_allows_sidecar_path().read_text())
    assert "session:napcat:group:room-a" in pending
