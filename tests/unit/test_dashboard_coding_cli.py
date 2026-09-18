"""Tests for the routes that switch a coding CLI's provider."""

import json
from types import SimpleNamespace

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


def test_the_state_action_is_an_ordinary_read():
    """Reading what a switch would do must not need fresh proof.

    A high-risk action is denied on the Dashboard until the operator answers a
    step-up challenge, and the state route has no way to ask for one: gating it
    behind the write action left the page with a load error instead of the list.
    """
    from astrbot.core.auth.models import HIGH_RISK_ACTIONS
    from astrbot.core.auth.registry import ACTION_POLICIES

    assert coding_cli.READ_ACTION == "platform.read"
    assert coding_cli.READ_ACTION not in HIGH_RISK_ACTIONS
    assert ACTION_POLICIES[coding_cli.READ_ACTION].requires_step_up is False


@pytest.mark.asyncio
async def test_the_state_route_reads_through_the_read_action(monkeypatch, homes):
    """The route asks for the read, and reports both CLIs and their providers."""
    called: list[str] = []

    async def read(request, auth):
        called.append(coding_cli.READ_ACTION)

    async def write(request, auth):  # pragma: no cover - failing here is the bug
        raise AssertionError("the state route asked for the high-risk action")

    monkeypatch.setattr(coding_cli, "authorize_coding_cli_read", read)
    monkeypatch.setattr(coding_cli, "authorize_coding_cli_write", write)
    monkeypatch.setattr(coding_cli, "_config_of", lambda request: PROFILE)

    payload = await coding_cli.get_global_config(SimpleNamespace(), None)

    assert called == [coding_cli.READ_ACTION]
    clis = payload["data"]["clis"]
    assert [entry["cli"] for entry in clis] == ["claude_code", "codex"]
    # The scoped preset belongs to Codex alone; the unscoped one to both.
    assert [item["id"] for item in clis[0]["providers"]] == ["gw"]
    assert [item["id"] for item in clis[1]["providers"]] == ["gw", "scoped"]


def _app_state(*, runtime_services, dashboard_services):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                runtime=SimpleNamespace(services=runtime_services),
                services=dashboard_services,
            )
        )
    )


def test_the_running_profile_comes_from_the_dashboard_services():
    """The config profile service is not on the core runtime's services.

    Reading it from there answered "Configuration is unavailable" on every
    request, which is why the page showed a load error instead of its list.
    """
    profiles = SimpleNamespace(acm=SimpleNamespace(confs={"default": PROFILE}))
    request = _app_state(
        # What the core runtime carries: authorization and core pieces only.
        runtime_services=SimpleNamespace(authorization=object()),
        dashboard_services=SimpleNamespace(config_profiles=profiles),
    )

    assert coding_cli._config_of(request) == PROFILE


def test_an_unreadable_configuration_is_reported_rather_than_guessed():
    request = _app_state(
        runtime_services=SimpleNamespace(),
        dashboard_services=SimpleNamespace(),
    )

    with pytest.raises(ApiError) as error:
        coding_cli._config_of(request)

    assert error.value.status_code == 503
