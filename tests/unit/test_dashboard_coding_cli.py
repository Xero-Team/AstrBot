"""Tests for the routes that switch a coding CLI's provider."""

import json

import pytest

from astrbot.dashboard.api import coding_cli
from astrbot.dashboard.responses import ApiError

PROFILE = {
    "btw": {
        "cli_providers": [
            {
                "id": "gw",
                "name": "Gateway",
                "base_url": "https://gw.example",
                "api_key": "sk-secret",
                "model": "opus",
                "note": "primary",
            },
            {"id": "scoped", "name": "Codex only", "cli": "codex"},
            "not a mapping",
            {"id": "", "name": "no id"},
        ]
    }
}


@pytest.fixture
def homes(tmp_path, monkeypatch):
    """Point both CLIs at directories of the test's own."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path


def test_only_usable_entries_are_kept():
    providers = coding_cli.cli_global_config.normalize_cli_providers(
        PROFILE["btw"]["cli_providers"]
    )
    assert [provider["id"] for provider in providers] == ["gw", "scoped"]


def test_a_provider_must_exist(homes):
    with pytest.raises(ApiError):
        coding_cli._provider_for("claude_code", PROFILE, "nope")


def test_a_provider_scoped_to_another_cli_is_refused(homes):
    with pytest.raises(ApiError):
        coding_cli._provider_for("claude_code", PROFILE, "scoped")
    # ...but is usable by the one it names.
    assert coding_cli._provider_for("codex", PROFILE, "scoped")["id"] == "scoped"


def test_an_unscoped_provider_applies_to_every_cli(homes):
    for cli in ("claude_code", "codex"):
        assert coding_cli._provider_for(cli, PROFILE, "gw")["id"] == "gw"


def test_the_list_is_grouped_by_cli(homes):
    raw = PROFILE["btw"]["cli_providers"]
    assert [
        p["id"]
        for p in coding_cli.cli_global_config.providers_for_cli(raw, "claude_code")
    ] == ["gw"]
    assert [
        p["id"] for p in coding_cli.cli_global_config.providers_for_cli(raw, "codex")
    ] == ["gw", "scoped"]


def test_a_state_never_carries_a_credential(homes):
    cli_global_config = coding_cli.cli_global_config
    cli_global_config.apply_provider(
        "claude_code",
        {"id": "gw", "base_url": "https://gw.example", "api_key": "sk-secret"},
    )
    state = coding_cli._state("claude_code")
    assert state["has_credential"] is True
    assert "sk-secret" not in json.dumps(state)


def test_current_is_decided_by_the_endpoint_not_the_key(homes):
    cli_global_config = coding_cli.cli_global_config
    cli_global_config.apply_provider(
        "claude_code", {"id": "gw", "base_url": "https://gw.example", "api_key": "sk"}
    )
    state = cli_global_config.read_state("claude_code")
    assert coding_cli._is_current(
        {"base_url": "https://gw.example", "model": ""}, state
    )
    assert not coding_cli._is_current(
        {"base_url": "https://other.example", "model": ""}, state
    )


def test_the_switch_action_is_high_risk():
    """The whole point of the route: a global CLI write needs step-up."""
    from astrbot.core.auth.models import HIGH_RISK_ACTIONS
    from astrbot.core.auth.registry import ACTION_POLICIES

    assert coding_cli.WRITE_ACTION in HIGH_RISK_ACTIONS
    policy = ACTION_POLICIES[coding_cli.WRITE_ACTION]
    assert policy.risk == "high"
    assert policy.requires_step_up is True
