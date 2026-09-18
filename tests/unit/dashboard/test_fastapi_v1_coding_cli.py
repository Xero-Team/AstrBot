"""Route-level tests for switching a coding CLI's provider.

These go through the real ASGI app and its authorization call, which is what the
helper-only tests could not do: the whole bug was in which action each route
asked for, and nothing that called the functions directly could see it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio

from astrbot.core.auth.models import HIGH_RISK_ACTIONS

# The harness exports its fixtures too, `asgi_app` among them, which this file
# builds on to install the authorizer the routes are checked against.
from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403

PROVIDERS = [
    {
        "id": "gw",
        "name": "Gateway",
        "base_url": "https://gw.example",
        "api_key": "sk-secret",
        "model": "opus",
    },
]

GLOBAL_CONFIG = "/api/v1/coding-cli/global-config"


class _StepUpAuthorization:
    """The Dashboard's rule, reduced to the part these routes depend on.

    A high-risk action is denied until the request carries a step-up token.
    That is what the plain GET could never answer, and what a route asking for
    the wrong action is denied by -- which is the failure these tests exist to
    catch.
    """

    async def authorize(self, subject, action, resource, context):
        if action in HIGH_RISK_ACTIONS:
            stepped_up = bool(context.step_up_token)
            return SimpleNamespace(
                allowed=stepped_up,
                requires_step_up=not stepped_up,
            )
        return SimpleNamespace(allowed=True, requires_step_up=False)


@pytest.fixture
def cli_homes(tmp_path, monkeypatch):
    """Point both CLIs at directories of the test's own."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path


@pytest.fixture
def coding_cli_app(asgi_app, cli_homes, fake_core_lifecycle):  # noqa: F811
    asgi_app.state.runtime.services.authorization = _StepUpAuthorization()
    fake_core_lifecycle.astrbot_config_mgr.confs["default"]["btw"] = {
        "cli_providers": PROVIDERS
    }
    return asgi_app


@pytest_asyncio.fixture
async def coding_cli_client(coding_cli_app):
    transport = httpx.ASGITransport(app=coding_cli_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_the_state_route_answers_without_a_step_up(coding_cli_client):
    """Reading the page's data must not demand a credential it cannot send.

    The route used to ask for `coding_cli.config.write`, which is high-risk, so
    every load was answered with a challenge a plain GET has no way to answer.
    """
    response = await coding_cli_client.get(GLOBAL_CONFIG, headers=_jwt_headers())

    assert response.status_code == 200
    assert [entry["cli"] for entry in response.json()["data"]["clis"]] == [
        "claude_code",
        "codex",
    ]


@pytest.mark.asyncio
async def test_the_state_never_carries_the_stored_key(coding_cli_client):
    response = await coding_cli_client.get(GLOBAL_CONFIG, headers=_jwt_headers())

    assert response.status_code == 200
    body = response.text
    assert "sk-secret" not in body
    providers = response.json()["data"]["clis"][0]["providers"]
    # Present, not named: the operator still has to be able to tell.
    assert providers[0]["has_api_key"] is True


@pytest.mark.asyncio
async def test_switching_a_provider_asks_for_a_step_up(coding_cli_client):
    response = await coding_cli_client.put(
        GLOBAL_CONFIG,
        headers=_jwt_headers(),
        json={"cli": "claude_code", "provider_id": "gw"},
    )

    assert response.status_code == 403
    assert response.json()["data"]["requires_step_up"] is True


@pytest.mark.asyncio
async def test_taking_the_configuration_back_asks_for_a_step_up(coding_cli_client):
    response = await coding_cli_client.delete(
        f"{GLOBAL_CONFIG}/claude_code",
        headers=_jwt_headers(),
    )

    assert response.status_code == 403
    assert response.json()["data"]["requires_step_up"] is True


@pytest.mark.asyncio
async def test_a_switch_with_a_step_up_writes_the_cli_own_file(
    coding_cli_client,
    cli_homes,
):
    response = await coding_cli_client.put(
        GLOBAL_CONFIG,
        headers={**_jwt_headers(), "X-AstrBot-Step-Up": "issued"},
        json={"cli": "claude_code", "provider_id": "gw"},
    )

    assert response.status_code == 200
    settings = json.loads(
        (cli_homes / "claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert settings["env"]["ANTHROPIC_BASE_URL"] == PROVIDERS[0]["base_url"]
    assert settings["env"]["ANTHROPIC_AUTH_TOKEN"] == PROVIDERS[0]["api_key"]
    # The write that replaced the file can be undone, and nothing else about
    # the response names the key it just wrote.
    assert PROVIDERS[0]["api_key"] not in response.text
