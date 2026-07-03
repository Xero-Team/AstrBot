import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from tests.fixtures.helpers import make_platform_config


def _build_adapter(**overrides) -> SlackAdapter:
    config = {
        "id": "test_slack",
        "bot_token": "xoxb-test",
        "app_token": "xapp-test",
        "signing_secret": "secret",
        "slack_connection_mode": "socket",
    }
    config.update(overrides)
    return SlackAdapter(
        make_platform_config("slack", **config),
        {},
        asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_slack_convert_message_falls_back_when_slack_lookups_fail():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter.web_client.users_info = AsyncMock(side_effect=RuntimeError("lookup failed"))
    adapter.web_client.conversations_info = AsyncMock(
        side_effect=RuntimeError("channel failed")
    )

    with patch(
        "astrbot.core.platform.sources.slack.slack_adapter.uuid.uuid4",
        return_value=SimpleNamespace(hex="generated-id"),
    ):
        result = await adapter.convert_message(
            {
                "user": "U1",
                "channel": "C1",
                "text": "hello slack",
                "ts": "1700000000.123",
            }
        )

    assert result.self_id == "B1"
    assert result.sender.user_id == "U1"
    assert result.sender.nickname == "U1"
    assert result.type is MessageType.GROUP_MESSAGE
    assert result.group_id == "C1"
    assert result.session_id == "C1"
    assert result.message_id == "generated-id"
    assert result.timestamp == 1_700_000_000
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Plain)
    assert result.message[0].text == "hello slack"


@pytest.mark.asyncio
async def test_slack_convert_message_uses_blocks_and_attachment_parsing():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Sender Name"}}
    )
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": True}}
    )
    adapter._parse_blocks = MagicMock(
        return_value=[
            Comp.Plain("Hello "),
            Comp.At(qq="U2", name="Alice"),
            Comp.Plain("world"),
        ]
    )
    adapter.get_file_base64 = AsyncMock(return_value="base64-image")

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "D1",
            "text": "ignored because blocks exist",
            "blocks": [{"type": "rich_text"}],
            "files": [
                {
                    "name": "image.png",
                    "url_private": "https://files.example.com/image",
                    "mimetype": "image/png",
                },
                {
                    "name": "notes.pdf",
                    "url_private": "https://files.example.com/notes",
                    "mimetype": "application/pdf",
                },
            ],
        }
    )

    assert result.type is MessageType.FRIEND_MESSAGE
    assert result.session_id == "U1"
    assert result.sender.nickname == "Sender Name"
    assert result.message_str == "Hello world"
    assert isinstance(result.message[0], Comp.Plain)
    assert isinstance(result.message[1], Comp.At)
    assert isinstance(result.message[2], Comp.Plain)
    assert isinstance(result.message[3], Comp.Image)
    assert isinstance(result.message[4], Comp.File)
    adapter._parse_blocks.assert_called_once_with([{"type": "rich_text"}])
    adapter.get_file_base64.assert_awaited_once_with(
        "https://files.example.com/image"
    )


@pytest.mark.asyncio
async def test_slack_convert_message_parses_mentions_and_mention_lookup_failures():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"

    async def users_info(*, user: str):
        if user == "U1":
            return {"user": {"real_name": "Sender Name"}}
        raise RuntimeError("mention lookup failed")

    adapter.web_client.users_info = AsyncMock(side_effect=users_info)
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": False}}
    )

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "C2",
            "text": "<@U2> hi there",
            "client_msg_id": "msg-1",
        }
    )

    assert result.type is MessageType.GROUP_MESSAGE
    assert result.group_id == "C2"
    assert result.message_str == "<@U2> hi there"
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "U2"
    assert result.message[0].name == ""
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message[1].text == "hi there"


def test_slack_parse_blocks_handles_rich_text_lists_and_markdown_sections():
    adapter = _build_adapter()

    components = adapter._parse_blocks(
        [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "text", "text": "Hello "},
                            {"type": "user", "user_id": "U2"},
                            {"type": "channel", "channel_id": "C1"},
                            {
                                "type": "link",
                                "url": "https://example.com",
                                "text": "doc",
                            },
                            {"type": "emoji", "name": "wave"},
                        ],
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "first"}],
                            },
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "second"}],
                            },
                        ],
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*bold*"},
            },
        ]
    )

    assert len(components) == 5
    assert isinstance(components[0], Comp.Plain)
    assert components[0].text == "Hello "
    assert isinstance(components[1], Comp.At)
    assert components[1].qq == "U2"
    assert isinstance(components[2], Comp.Plain)
    assert components[2].text == "#C1[doc](https://example.com):wave:"
    assert isinstance(components[3], Comp.Plain)
    assert components[3].text == "• first\n• second"
    assert isinstance(components[4], Comp.Plain)
    assert components[4].text == "*bold*"


@pytest.mark.asyncio
async def test_slack_handle_socket_event_filters_noise_and_forwards_valid_message():
    adapter = _build_adapter()
    converted = object()
    adapter.convert_message = AsyncMock(return_value=converted)
    adapter.handle_msg = AsyncMock()

    ignored_requests = [
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "message", "subtype": "bot_message"}},
        ),
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "message_changed"}},
        ),
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "message", "bot_id": "B2"}},
        ),
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "reaction_added"}},
        ),
        SimpleNamespace(type="disconnect", payload={"event": {"type": "message"}}),
    ]

    for request in ignored_requests:
        await adapter._handle_socket_event(request)

    valid_request = SimpleNamespace(
        type="events_api",
        payload={"event": {"type": "app_mention", "text": "hello", "user": "U1"}},
    )
    await adapter._handle_socket_event(valid_request)

    adapter.convert_message.assert_awaited_once_with(valid_request.payload["event"])
    adapter.handle_msg.assert_awaited_once_with(converted)


@pytest.mark.asyncio
async def test_slack_send_by_session_uses_group_channel_suffix_and_blocks():
    adapter = _build_adapter()
    adapter.web_client.chat_postMessage = AsyncMock()

    with patch(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackMessageEvent._parse_slack_blocks",
        AsyncMock(return_value=([{"type": "section"}], "")),
    ):
        await adapter.send_by_session(
            SimpleNamespace(
                message_type=MessageType.GROUP_MESSAGE,
                session_id="slack_C123",
            ),
            MessageChain().message("hello"),
        )

    adapter.web_client.chat_postMessage.assert_awaited_once_with(
        channel="C123",
        text="",
        blocks=[{"type": "section"}],
    )


@pytest.mark.asyncio
async def test_slack_send_by_session_uses_dm_session_id_directly():
    adapter = _build_adapter()
    adapter.web_client.chat_postMessage = AsyncMock()

    with patch(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackMessageEvent._parse_slack_blocks",
        AsyncMock(return_value=([], "hello direct")),
    ):
        await adapter.send_by_session(
            SimpleNamespace(
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="U123",
            ),
            MessageChain().message("hello"),
        )

    adapter.web_client.chat_postMessage.assert_awaited_once_with(
        channel="U123",
        text="hello direct",
        blocks=None,
    )


@pytest.mark.asyncio
async def test_slack_convert_message_uses_group_fallback_when_conversation_lookup_fails():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Sender Name"}}
    )
    adapter.web_client.conversations_info = AsyncMock(side_effect=RuntimeError("boom"))

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "C-fallback",
            "text": "fallback group",
            "client_msg_id": "msg-1",
        }
    )

    assert result.type is MessageType.GROUP_MESSAGE
    assert result.group_id == "C-fallback"
    assert result.session_id == "C-fallback"
    assert result.message[0].text == "fallback group"


@pytest.mark.asyncio
async def test_slack_convert_message_keeps_whitespace_only_text_out_of_components():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Sender Name"}}
    )
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": False}}
    )

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "C2",
            "text": "<@U2>   ",
            "client_msg_id": "msg-2",
        }
    )

    assert result.message_str == "<@U2>   "
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "U2"


@pytest.mark.asyncio
async def test_slack_handle_webhook_event_ignores_noise_and_forwards_message():
    adapter = _build_adapter(slack_connection_mode="webhook")
    adapter.convert_message = AsyncMock(return_value="converted")
    adapter.handle_msg = AsyncMock()

    ignored_events = [
        {"event": {"type": "message", "subtype": "bot_message"}},
        {"event": {"type": "message_changed"}},
        {"event": {"type": "message", "bot_id": "B2"}},
        {"event": {"type": "reaction_added"}},
    ]

    for payload in ignored_events:
        await adapter._handle_webhook_event(payload)

    valid_payload = {"event": {"type": "message", "text": "hello", "user": "U1"}}
    await adapter._handle_webhook_event(valid_payload)

    adapter.convert_message.assert_awaited_once_with(valid_payload["event"])
    adapter.handle_msg.assert_awaited_once_with("converted")


@pytest.mark.asyncio
async def test_slack_webhook_callback_rejects_non_webhook_mode():
    adapter = _build_adapter(slack_connection_mode="socket")

    result = await adapter.webhook_callback(SimpleNamespace())

    assert result == ({"error": "Slack adapter is not in webhook mode"}, 400)


@pytest.mark.asyncio
async def test_slack_webhook_callback_delegates_to_webhook_client():
    adapter = _build_adapter(slack_connection_mode="webhook")
    adapter.webhook_client = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"ok": True})
    )

    result = await adapter.webhook_callback(SimpleNamespace(method="POST"))

    assert result == {"ok": True}
    adapter.webhook_client.handle_callback.assert_awaited_once()


def test_slack_unified_webhook_requires_webhook_mode_and_uuid():
    webhook_adapter = _build_adapter(
        slack_connection_mode="webhook",
        unified_webhook_mode=True,
        webhook_uuid="uuid-1",
    )
    socket_adapter = _build_adapter(
        slack_connection_mode="socket",
        unified_webhook_mode=True,
        webhook_uuid="uuid-1",
    )
    missing_uuid_adapter = _build_adapter(
        slack_connection_mode="webhook",
        unified_webhook_mode=True,
        webhook_uuid=None,
    )

    assert webhook_adapter.unified_webhook() is True
    assert socket_adapter.unified_webhook() is False
    assert missing_uuid_adapter.unified_webhook() is False
