"""Route tests for BTW work-session visibility."""

from __future__ import annotations

import pytest

from astrbot.core.agent.btw import runtime_registry
from astrbot.core.agent.btw.types import WorkDelegation, WorkSessionStatus
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403


@pytest.fixture
def isolated_registry(monkeypatch):
    monkeypatch.setattr(runtime_registry, "_managers", {})
    return runtime_registry


@pytest.mark.asyncio
async def test_the_route_lists_sessions_and_delegation_timelines(
    asgi_client, isolated_registry
):
    manager = WorkSessionManager()
    session = await manager.create(
        "webchat:FriendMessage:user",
        "x" * 2500 + " https://private.example/path?api_key=sk-abcdefghijklmnop",
    )
    await manager.update_status(session.id, WorkSessionStatus.RUNNING)
    delegation = WorkDelegation(
        run_id="run-1",
        agent_id="codex",
        agent_name="Codex",
        agent_type="codex",
        workspace="run-1",
    )
    await manager.start_delegation(session.id, delegation)
    await manager.record_delegation_event(
        session.id,
        "run-1",
        event_type="tool_call",
        summary="shell: pytest -q",
        tool="shell",
        status="running",
    )
    isolated_registry.register("default", manager)

    response = await asgi_client.get(
        "/api/v1/btw/work-sessions", headers=_jwt_headers()
    )

    assert response.status_code == 200
    payload = response.json()["data"]["sessions"]
    assert len(payload) == 1
    assert payload[0]["id"] == session.id
    assert payload[0]["config_id"] == "default"
    assert payload[0]["status"] == "running"
    assert len(payload[0]["request"]) == 2000
    assert payload[0]["delegations"][0]["agent_name"] == "Codex"
    assert payload[0]["delegations"][0]["recent_events"][0]["summary"] == (
        "shell: pytest -q"
    )
    assert "sk-abcdefghijklmnop" not in response.text
    assert "private.example" not in response.text


@pytest.mark.asyncio
async def test_the_route_returns_an_empty_list_without_runtime_sessions(
    asgi_client, isolated_registry
):
    del isolated_registry
    response = await asgi_client.get(
        "/api/v1/btw/work-sessions", headers=_jwt_headers()
    )

    assert response.status_code == 200
    assert response.json()["data"]["sessions"] == []


@pytest.mark.asyncio
async def test_a_chat_scope_api_key_cannot_read_internal_work_sessions(
    asgi_client, fake_db, isolated_registry
):
    manager = WorkSessionManager()
    await manager.create(
        "telegram:GroupMessage:private-user",
        "SECRET USER TASK",
    )
    isolated_registry.register("profile-a", manager)
    raw_key = "abk_btw_work_sessions_chat_only"
    fake_db.add_api_key(raw_key, scopes=["chat"])

    response = await asgi_client.get(
        "/api/v1/btw/work-sessions", headers={"X-API-Key": raw_key}
    )

    assert response.status_code == 403
    assert "SECRET USER TASK" not in response.text
