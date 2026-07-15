from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.core.pipeline.waking_check.stage as waking
from astrbot.core.message.components import At, AtAll, Plain, Reply
from astrbot.core.platform.message_type import MessageType


class FakeEvent:
    def __init__(
        self,
        messages,
        *,
        private=False,
        message_text="hello",
        platform="aiocqhttp",
        sender_id="user",
        group_id="group",
        extras=None,
    ):
        self.message_obj = SimpleNamespace(
            type=MessageType.FRIEND_MESSAGE if private else MessageType.GROUP_MESSAGE
        )
        self.message_str = message_text
        self.session_id = group_id
        self.role = "member"
        self.is_wake = False
        self.is_at_or_wake_command = False
        self.plugins_name = None
        self._messages = messages
        self._private = private
        self._platform = platform
        self._sender_id = sender_id
        self._group_id = group_id
        self._extras = extras or {}
        self.stopped = False
        self.sent = []

    def get_extra(self, key=None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_messages(self):
        return self._messages

    def is_private_chat(self):
        return self._private

    def get_platform_name(self):
        return self._platform

    def get_self_id(self):
        return "bot"

    def get_sender_id(self):
        return self._sender_id

    def get_group_id(self):
        return self._group_id

    def get_session_id(self):
        return self.session_id

    def stop_event(self):
        self.stopped = True

    def is_admin(self):
        return self.role == "admin"

    async def send(self, payload):
        self.sent.append(payload)


async def make_stage(**settings):
    config = {
        "admins_id": ["admin"],
        "wake_prefix": ["/"],
        "plugin_set": ["*"],
        "disable_builtin_commands": False,
        "platform_settings": {
            "no_permission_reply": True,
            "friend_message_needs_wake_prefix": False,
            "ignore_bot_self_message": False,
            "ignore_at_all": False,
            "unique_session": False,
            **settings,
        },
    }
    stage = waking.WakingCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config,
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
        )
    )
    stage.session_plugins.filter_handlers_by_session = AsyncMock(
        side_effect=lambda _, h: h
    )
    return stage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "event", "expected"),
    [
        ({}, FakeEvent([Plain("hello")], private=True), True),
        (
            {"friend_message_needs_wake_prefix": True},
            FakeEvent([Plain("hello")], private=True),
            False,
        ),
        (
            {"friend_message_needs_wake_prefix": True},
            FakeEvent([Plain("/hello")], private=True, message_text="/hello"),
            True,
        ),
        (
            {},
            FakeEvent(
                [Plain("hello")], private=True, extras={"skip_private_wake": True}
            ),
            False,
        ),
        ({}, FakeEvent([Plain("/hello")], message_text="/hello"), True),
        ({}, FakeEvent([At(qq="bot"), Plain("hello")]), True),
        ({}, FakeEvent([At(qq="other"), Plain("hello")]), False),
        ({}, FakeEvent([AtAll(), Plain("hello")]), True),
        ({"ignore_at_all": True}, FakeEvent([AtAll(), Plain("hello")]), False),
    ],
)
async def test_detect_wake_behavior_matrix(settings, event, expected):
    stage = await make_stage(**settings)

    assert await stage._detect_wake(event) is expected
    assert event.is_wake is expected


@pytest.mark.asyncio
async def test_detect_wake_resolves_unknown_reply_sender(monkeypatch):
    event = FakeEvent([Reply(id="reply-1"), Plain("hello")])
    stage = await make_stage()
    client = SimpleNamespace(get_msg_sender_id=AsyncMock(return_value="bot"))
    monkeypatch.setattr(waking, "OneBotClient", lambda _: client)

    assert await stage._detect_wake(event) is True
    assert event.get_messages()[0].sender_id == "bot"
    client.get_msg_sender_id.assert_awaited_once_with("reply-1")


@pytest.mark.asyncio
async def test_process_applies_admin_self_message_and_unique_session_rules(monkeypatch):
    stage = await make_stage(unique_session=True, ignore_bot_self_message=True)
    monkeypatch.setattr(
        waking.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_: [],
    )

    self_event = FakeEvent([Plain("hello")], sender_id="bot")
    await stage.process(self_event)
    assert self_event.stopped is True

    admin_event = FakeEvent([Plain("/hello")], message_text="/hello", sender_id="admin")
    await stage.process(admin_event)
    assert admin_event.role == "admin"
    assert admin_event.session_id == "admin_group"

    notice_event = FakeEvent(
        [Plain("hello")], extras={"onebot_post_type": "notice"}, sender_id="admin"
    )
    await stage.process(notice_event)
    assert notice_event.session_id == "group"


@pytest.mark.asyncio
async def test_process_filters_handlers_by_session(monkeypatch):
    stage = await make_stage()
    handler = SimpleNamespace(
        handler_module_path="test.plugin",
        handler_full_name="test.handler",
        event_filters=[SimpleNamespace(filter=lambda *_: True)],
    )
    monkeypatch.setattr(
        waking.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_: [handler],
    )
    stage.session_plugins.filter_handlers_by_session = AsyncMock(return_value=[])
    event = FakeEvent([Plain("hello")])

    await stage.process(event)

    assert event.is_wake is True
    assert event.get_extra("activated_handlers") == []
    stage.session_plugins.filter_handlers_by_session.assert_awaited_once_with(
        event, [handler]
    )
