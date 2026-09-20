from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.session import (
    FilterSpec,
    SessionCommands,
    parse_filter_spec,
    parse_pair_spec,
    parse_unlink_spec,
    parse_unpair_spec,
    parse_watch_spec,
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
        pair_id=None,
    )
    link = SimpleNamespace(
        rule_id="abc123def456",
        source_umo="source:FriendMessage:sender",
        target_umo="other:GroupMessage:room",
        remaining_seconds=0,
        expires_at=None,
        pair_id=None,
    )
    pair_left = SimpleNamespace(
        rule_id="aa11bb22cc33",
        source_umo="source:FriendMessage:sender",
        target_umo="peer:GroupMessage:room",
        remaining_seconds=0,
        expires_at=None,
        pair_id="pairidabcdef",
    )

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    manager = SimpleNamespace(
        list_links=AsyncMock(
            return_value=((watch, "watch"), (link, "connect"), (pair_left, "pair"))
        ),
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
        "session.links.ttl_seconds",
        "session.links.ttl_unbounded",
        "session.links.ttl_unbounded",
        "session.links.body",
        "session.unlink.ok",
        "session.unlink.usage",
    ]
    manager.unlink.assert_awaited_once_with(event, "abcdef123456")


def test_parse_pair_spec_rejects_duration():
    assert parse_pair_spec("target:GroupMessage:room") == "target:GroupMessage:room"
    with pytest.raises(ValueError, match="Invalid pair duration"):
        parse_pair_spec("target:GroupMessage:room 60")
    with pytest.raises(ValueError, match="Invalid pair arguments"):
        parse_pair_spec("")
    with pytest.raises(ValueError, match="Invalid pair arguments"):
        parse_pair_spec("a b c")


def test_parse_unpair_spec_allows_omitted_umo():
    assert parse_unpair_spec("") is None
    assert parse_unpair_spec("target:GroupMessage:room") == "target:GroupMessage:room"
    with pytest.raises(ValueError, match="Invalid unpair arguments"):
        parse_unpair_spec("a b")


@pytest.mark.asyncio
async def test_session_commands_pair_unpair_and_unlink_pair():
    replies: list[str] = []
    left = SimpleNamespace(
        rule_id="aa11bb22cc33",
        target_umo="target:GroupMessage:room",
        pair_id="pairidabcdef",
    )
    right = SimpleNamespace(rule_id="dd44ee55ff66")

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    manager = SimpleNamespace(
        pair=AsyncMock(return_value=(left, right)),
        unpair=AsyncMock(
            side_effect=[True, False, ValueError("Multiple pairs require a UMO")]
        ),
        unlink=AsyncMock(side_effect=ValueError("Pair edges cannot be unlinked")),
    )
    context = SimpleNamespace(
        bridges=SimpleNamespace(_manager=manager),
        i18n=SimpleNamespace(t=translate),
    )
    commands = SessionCommands(context)
    event = _event()
    await commands.pair(event, "target:GroupMessage:room")
    await commands.pair(event, "target:GroupMessage:room 30")
    await commands.unpair(event, "target:GroupMessage:room")
    await commands.unpair(event, "missing:GroupMessage:room")
    await commands.unpair(event, "")
    await commands.unlink(event, "aa11bb22cc33")
    assert replies == [
        "session.pair.ok",
        "session.pair.ttl_invalid",
        "session.unpair.ok",
        "session.unpair.missing",
        "session.unpair.ambiguous",
        "session.unlink.pair",
    ]


@pytest.mark.asyncio
async def test_session_commands_watch_connect_report_pair_occupied():
    replies: list[str] = []

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    context = SimpleNamespace(
        bridges=SimpleNamespace(
            watch=AsyncMock(side_effect=ValueError("Direction is occupied by a pair")),
            connect=AsyncMock(
                side_effect=ValueError("Direction is occupied by a pair")
            ),
        ),
        i18n=SimpleNamespace(t=translate),
    )
    commands = SessionCommands(context)
    event = _event()
    await commands.watch(event, "target:GroupMessage:room")
    await commands.connect(event, "target:GroupMessage:room")
    assert replies == ["session.watch.occupied", "session.connect.occupied"]


@pytest.mark.asyncio
async def test_session_commands_report_quota_limits():
    calls: list[tuple[str, dict]] = []

    async def translate(_event, key, **kwargs):
        calls.append((key, kwargs))
        return key

    quotas = {
        "watch": SimpleNamespace(current=16, limit=16),
        "connect": SimpleNamespace(current=16, limit=16),
        "pair": SimpleNamespace(current=8, limit=8),
    }
    manager = SimpleNamespace(
        pair=AsyncMock(side_effect=ValueError("Pair limit exceeded")),
        quota_usage=AsyncMock(return_value=quotas),
    )
    context = SimpleNamespace(
        bridges=SimpleNamespace(
            watch=AsyncMock(side_effect=ValueError("Watch limit exceeded")),
            connect=AsyncMock(side_effect=ValueError("Connect limit exceeded")),
            _manager=manager,
        ),
        i18n=SimpleNamespace(t=translate),
    )
    commands = SessionCommands(context)
    event = _event()
    await commands.watch(event, "target:GroupMessage:room")
    await commands.connect(event, "target:GroupMessage:room")
    await commands.pair(event, "target:GroupMessage:room")
    assert calls == [
        ("session.watch.limit", {"current": 16, "limit": 16}),
        ("session.connect.limit", {"current": 16, "limit": 16}),
        ("session.pair.limit", {"current": 8, "limit": 8}),
    ]


@pytest.mark.asyncio
async def test_session_commands_report_runtime_limit():
    replies: list[str] = []

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    context = SimpleNamespace(
        bridges=SimpleNamespace(
            watch=AsyncMock(side_effect=ValueError("Runtime watch limit exceeded")),
            connect=AsyncMock(side_effect=ValueError("Runtime connect limit exceeded")),
            _manager=SimpleNamespace(
                pair=AsyncMock(side_effect=ValueError("Runtime pair limit exceeded"))
            ),
        ),
        i18n=SimpleNamespace(t=translate),
    )
    commands = SessionCommands(context)
    event = _event()
    await commands.watch(event, "target:GroupMessage:room")
    await commands.connect(event, "target:GroupMessage:room")
    await commands.pair(event, "target:GroupMessage:room")
    assert replies == ["session.bridge.runtime_limit"] * 3


def test_parse_watch_spec_rejects_filter_flags():
    current = "source:FriendMessage:sender"
    with pytest.raises(ValueError, match="Invalid watch arguments"):
        parse_watch_spec("target:GroupMessage:room match text hello", current)


def test_parse_filter_spec_show_append_and_clear():
    assert parse_filter_spec("abcdef123456") == FilterSpec("abcdef123456", "show")
    assert parse_filter_spec("abcdef123456 clear") == FilterSpec(
        "abcdef123456", "clear", "all"
    )
    assert parse_filter_spec("abcdef123456 clear match") == FilterSpec(
        "abcdef123456", "clear", "match"
    )
    assert parse_filter_spec("abcdef123456 match text hello world") == FilterSpec(
        "abcdef123456", "append", "match", "text", "hello world"
    )
    assert parse_filter_spec("abcdef123456 except role member") == FilterSpec(
        "abcdef123456", "append", "except", "roles", "member"
    )
    with pytest.raises(ValueError):
        parse_filter_spec("abcdef123456 match role member extra")
    with pytest.raises(ValueError):
        parse_filter_spec("ABCDEF123456")


@pytest.mark.asyncio
async def test_session_commands_filter_show_append_and_clear():
    replies: list[str] = []

    async def get_filter(_event, rule_id):
        if rule_id == "deadbeef0001":
            return None
        return ({}, {})

    async def append_filter(_event, _rule_id, _side, _dimension, value):
        if value == "admin":
            raise ValueError("Invalid filter role")
        if value == "(":
            raise ValueError("Invalid filter pattern")
        return ({"text": ["hello world"]}, {})

    manager = SimpleNamespace(
        get_filter=AsyncMock(side_effect=get_filter),
        append_filter=AsyncMock(side_effect=append_filter),
        clear_filter=AsyncMock(return_value=({}, {})),
    )

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    context = SimpleNamespace(
        bridges=SimpleNamespace(_manager=manager),
        i18n=SimpleNamespace(t=translate),
    )
    commands = SessionCommands(context)
    event = _event()
    await commands.filter_rule(event, "abcdef123456")
    await commands.filter_rule(event, "abcdef123456 match text hello world")
    await commands.filter_rule(event, "abcdef123456 clear")
    await commands.filter_rule(event, "not-an-id")
    await commands.filter_rule(event, "abcdef123456 match role admin")
    await commands.filter_rule(event, "abcdef123456 match text (")
    await commands.filter_rule(event, "deadbeef0001")
    assert replies == [
        "session.filter.empty",
        "session.filter.empty",
        "session.filter.body",
        "session.filter.empty",
        "session.filter.updated",
        "session.filter.empty",
        "session.filter.empty",
        "session.filter.cleared",
        "session.filter.usage",
        "session.filter.invalid_role",
        "session.filter.invalid_pattern",
        "session.filter.missing",
    ]
    manager.get_filter.assert_any_await(event, "abcdef123456")
    manager.get_filter.assert_any_await(event, "deadbeef0001")
    manager.append_filter.assert_any_await(
        event, "abcdef123456", "match", "text", "hello world"
    )
    manager.clear_filter.assert_awaited_once_with(event, "abcdef123456", "all")
