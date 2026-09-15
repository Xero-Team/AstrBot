from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.session import (
    SessionCommands,
    parse_unlink_spec,
)
from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.platform.route_identity import PlatformRouteIdentity


def _event(umo="source:FriendMessage:sender", *, sender="actor"):
    from astrbot.core.platform.message_session import MessageSession

    subject = Subject.im(
        platform_instance="source", bot_account_id="bot", sender_id=sender
    )
    session = MessageSession.from_str(umo)
    return SimpleNamespace(
        unified_msg_origin=umo,
        subject=subject,
        auth_context=AuthContext(
            subject=subject,
            source="im",
            config_id="default",
            authenticated=True,
            origin_session_resource_id=Resource.session("default", umo).id,
        ),
        route_identity=PlatformRouteIdentity(
            session.platform_id, session.message_type, session.session_id
        ),
        get_messages=lambda: [],
        get_platform_name=lambda: "telegram",
        get_sender_id=lambda: sender,
        get_sender_name=lambda: sender,
        get_self_id=lambda: "bot",
        message_obj=SimpleNamespace(message_id="inbound"),
        created_at=0.0,
        set_result=lambda _result: None,
    )


def test_parse_unlink_spec_requires_twelve_hex():
    assert parse_unlink_spec("abcdef123456") == "abcdef123456"
    with pytest.raises(ValueError):
        parse_unlink_spec("ABCDEF123456")
    with pytest.raises(ValueError):
        parse_unlink_spec("short")
    with pytest.raises(ValueError):
        parse_unlink_spec("abcdef123456 extra")


@pytest.mark.asyncio
async def test_session_commands_connect_rejects_duration_token():
    replies: list[str] = []

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    context = SimpleNamespace(
        bridges=SimpleNamespace(connect=AsyncMock()),
        i18n=SimpleNamespace(t=translate),
    )
    await SessionCommands(context).connect(_event(), "target:GroupMessage:room 60")
    assert replies == ["session.connect.usage"]
    context.bridges.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_commands_links_and_unlink():
    replies: list[str] = []
    watch = SimpleNamespace(
        rule_id="abcdef123456",
        source_umo="source:FriendMessage:sender",
        target_umo="target:GroupMessage:room",
        remaining_seconds=12,
        expires_at=1.0,
    )

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    manager = SimpleNamespace(
        list_links=AsyncMock(return_value=((watch, "watch"),)),
        unlink=AsyncMock(return_value=True),
    )
    context = SimpleNamespace(
        bridges=SimpleNamespace(_manager=manager),
        i18n=SimpleNamespace(t=translate),
    )
    commands = SessionCommands(context)
    event = _event()
    await commands.links(event)
    await commands.unlink(event, "abcdef123456")
    await commands.unlink(event, "not-an-id")
    assert replies == [
        "session.links.body",
        "session.unlink.ok",
        "session.unlink.usage",
    ]
    manager.unlink.assert_awaited_once_with(event, "abcdef123456")
