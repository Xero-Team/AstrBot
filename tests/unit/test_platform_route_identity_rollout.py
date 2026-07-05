from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.discord.discord_platform_adapter import (
    DiscordPlatformAdapter,
)
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent


def _telegram_message(
    *,
    session_id: str,
    sender_id: str = "user-1",
    group_id: str | None = None,
    message_type: MessageType = MessageType.FRIEND_MESSAGE,
) -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = message_type
    message.self_id = "bot-1"
    message.session_id = session_id
    message.message_id = "msg-1"
    message.sender = MessageMember(sender_id, "sender")
    message.group_id = group_id
    message.message = [Plain("hello")]
    message.message_str = "hello"
    message.raw_message = None
    return message


@pytest.mark.asyncio
async def test_telegram_event_send_uses_route_identity_target() -> None:
    client = AsyncMock()
    event = TelegramPlatformEvent(
        message_str="hello",
        message_obj=_telegram_message(
            session_id="topic-user_100",
            group_id="chat-42#7",
            message_type=MessageType.GROUP_MESSAGE,
        ),
        platform_meta=SimpleNamespace(name="telegram", id="telegram-test"),
        session_id="topic-user_100",
        client=client,
    )
    event.session_id = "mutated-session"

    await event.send(MessageChain([Plain("reply")]))

    client.send_message.assert_awaited_once()
    assert client.send_message.await_args.kwargs["chat_id"] == "chat-42"
    assert client.send_message.await_args.kwargs["message_thread_id"] == "7"
    assert event.route_identity.target_id == "chat-42#7"
    assert event.session.session_id == "mutated-session"


@pytest.mark.asyncio
async def test_discord_send_by_session_does_not_mutate_input_session() -> None:
    adapter = DiscordPlatformAdapter(
        {
            "id": "discord-test",
            "discord_token": "token",
        },
        {},
        __import__("asyncio").Queue(),
    )
    adapter.client = SimpleNamespace(
        user=SimpleNamespace(display_name="bot"),
        get_channel=lambda channel_id: None,
    )
    adapter.bot_self_id = "bot-1"
    original_session = MessageSession(
        platform_name="discord-test",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="sender_987654321",
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        send_mock = AsyncMock()
        monkeypatch.setattr(
            "astrbot.core.platform.sources.discord.discord_platform_event.DiscordPlatformEvent.send",
            send_mock,
        )

        await adapter.send_by_session(
            original_session,
            MessageChain([Plain("reply")]),
        )

    assert original_session.session_id == "sender_987654321"
    send_mock.assert_awaited_once()
