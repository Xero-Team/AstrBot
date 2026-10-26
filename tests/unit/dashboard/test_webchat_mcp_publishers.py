from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.mcp_client import MCPInteractionKey
from astrbot.dashboard.services import webchat_service as webchat_module
from astrbot.dashboard.services.webchat_service import WebChatService, WebChatSession


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(
        webchat_module,
        "get_astrbot_data_path",
        lambda: str(tmp_path / "data"),
    )
    coordinator = SimpleNamespace(
        respond=AsyncMock(return_value=True),
        set_publisher=lambda _publisher: None,
    )
    instance = WebChatService(
        db=SimpleNamespace(),
        preferences=SimpleNamespace(),
        config={"dashboard": {}},
        platform_message_history_manager=SimpleNamespace(),
        webchat_run_coordinator=SimpleNamespace(),
        mcp_interaction_coordinator=coordinator,
        token_validator=SimpleNamespace(),
    )
    return instance, coordinator


@pytest.mark.asyncio
async def test_mcp_elicitation_is_published_to_registered_chat_umo(service):
    instance, _coordinator = service
    session = WebChatSession("webchat!alice!connection", "alice")
    sent: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    umo = instance._register_mcp_publisher(session, "thread-1", send_json)
    await instance._publish_mcp_input(
        {"unified_msg_origin": umo, "type": "mcp_input", "request_id": "req-1"}
    )

    assert sent == [
        {
            "ct": "chat",
            "unified_msg_origin": umo,
            "type": "mcp_input",
            "request_id": "req-1",
        }
    ]


@pytest.mark.asyncio
async def test_mcp_input_response_requires_the_owning_umo(service):
    instance, coordinator = service
    session = WebChatSession("webchat!alice!connection", "alice")
    sent: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    umo = instance._register_mcp_publisher(session, "thread-1", send_json)
    message = {
        "request_id": "req-1",
        "run_id": "run-1",
        "server_name": "server",
        "unified_msg_origin": umo,
        "action": "accept",
        "content": {"field": "value"},
    }

    await instance._handle_mcp_input_response(session, message, send_json)

    coordinator.respond.assert_awaited_once_with(
        MCPInteractionKey(umo, "run-1", "req-1", "server"),
        "alice",
        "accept",
        {"field": "value"},
    )
    assert sent[-1]["accepted"] is True

    coordinator.respond.reset_mock()
    message["unified_msg_origin"] = "webchat:FriendMessage:webchat!mallory!thread-1"
    await instance._handle_mcp_input_response(session, message, send_json)

    coordinator.respond.assert_not_awaited()
    assert sent[-1]["accepted"] is False
