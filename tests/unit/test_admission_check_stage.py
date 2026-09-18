from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from astrbot.core.auth.admission import (
    ADMISSION_LISTED_SESSIONS_KEY,
    SESSION_SERVICE_CONFIG_KEY,
    sender_admission_key_from_event,
    session_admission_key_from_event,
)
from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.pipeline.admission_check.stage import (
    SENDER_BLOCKED_PASSTHROUGH_HANDLERS,
    AdmissionCheckStage,
)
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.command_ids import BUILTIN_COMMANDS_MODULE
from tests.unit.test_waking_check_stage import make_real_event


class _Preferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], Any] = {}
        self.sender_values: dict[tuple[str, str], Any] = {}
        self.global_values: dict[str, Any] = {}

    async def session_get(self, umo: str, key: str, default: Any = None) -> Any:
        return self.values.get((umo, key), default)

    async def sender_get(self, sender_id: str, key: str, default: Any = None) -> Any:
        return self.sender_values.get((sender_id, key), default)

    async def global_get(self, key: str, default: Any = None) -> Any:
        return self.global_values.get(key, default)


async def _stage(
    *,
    unlisted_sessions: str = "allow",
    unlisted_senders: str = "allow",
    preferences: _Preferences | None = None,
    authorization=None,
) -> AdmissionCheckStage:
    stage = AdmissionCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "admission": {
                    "unlisted_sessions": unlisted_sessions,
                    "unlisted_senders": unlisted_senders,
                }
            },
            astrbot_config_id="default",
            preferences=preferences or _Preferences(),
            authorization=authorization,
        )
    )
    return stage


def _with_handlers(event, *names: str):
    event.set_extra(
        "activated_handlers",
        [SimpleNamespace(handler_full_name=name) for name in names],
    )
    return event


@pytest.mark.asyncio
async def test_unlisted_allow_does_not_stop_events_without_overlays():
    stage = await _stage(unlisted_sessions="allow")
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)

    await stage.process(event)

    assert event.is_stopped() is False


@pytest.mark.asyncio
async def test_unlisted_deny_admits_listed_group_despite_unique_session_umo():
    preferences = _Preferences()
    listed = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="user-1_room-a",
    )
    denied = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-b",
        session_id="user-1_room-b",
    )
    preferences.values[
        (session_admission_key_from_event(listed), SESSION_SERVICE_CONFIG_KEY)
    ] = {"session_enabled": True}
    stage = await _stage(unlisted_sessions="deny", preferences=preferences)

    await stage.process(listed)
    await stage.process(denied)

    assert listed.is_stopped() is False
    assert denied.is_stopped() is True


@pytest.mark.asyncio
async def test_notice_and_request_skip_unlisted_deny():
    stage = await _stage(unlisted_sessions="deny")
    notice = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    notice.set_extra("onebot_post_type", "notice")
    request = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    request.set_extra("onebot_post_type", "request")

    await stage.process(notice)
    await stage.process(request)

    assert notice.is_stopped() is False
    assert request.is_stopped() is False


@pytest.mark.asyncio
async def test_webchat_skips_unlisted_deny():
    stage = await _stage(unlisted_sessions="deny")
    event = make_real_event(message_type=MessageType.FRIEND_MESSAGE)
    event.get_platform_name = lambda: "webchat"

    await stage.process(event)

    assert event.is_stopped() is False


@pytest.mark.asyncio
async def test_provider_manage_bypasses_unlisted_deny():
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    session = Resource.session("default", "napcat:GroupMessage:room-a")
    context = AuthContext(
        subject=subject,
        source="im",
        config_id="default",
        origin_session_resource_id=session.id,
        authenticated=True,
    )
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )
    stage = await _stage(unlisted_sessions="deny", authorization=authorization)
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    event.subject = subject
    event.resource = session
    event.auth_context = context

    await stage.process(event)

    assert event.is_stopped() is False
    authorization.authorize.assert_awaited_once_with(
        subject,
        "provider.manage",
        Resource.instance("default"),
        context,
    )


@pytest.mark.asyncio
async def test_sender_overlays_do_not_list_an_unlisted_session():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.sender_values[
        (sender_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"llm_enabled": True, "blocked": False}
    stage = await _stage(unlisted_sessions="deny", preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_disabled_listed_session_is_not_stopped_here():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.values[
        (session_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"session_enabled": False}
    stage = await _stage(unlisted_sessions="deny", preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is False


@pytest.mark.asyncio
async def test_session_blocked_passthrough_stays_with_status_stage():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.values[
        (session_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"session_blocked": True}
    preferences.sender_values[
        (sender_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"llm_enabled": True}
    stage = await _stage(unlisted_sessions="deny", preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is False


@pytest.mark.asyncio
async def test_initialize_requires_preferences():
    stage = AdmissionCheckStage()
    with pytest.raises(RuntimeError, match="shared preferences"):
        await stage.initialize(
            SimpleNamespace(
                astrbot_config={"admission": {"unlisted_sessions": "allow"}},
                astrbot_config_id="default",
                preferences=None,
            )
        )


@pytest.mark.asyncio
async def test_profile_listed_sessions_admit_without_overlays():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.global_values[ADMISSION_LISTED_SESSIONS_KEY] = {
        "default": [session_admission_key_from_event(event)]
    }
    stage = await _stage(unlisted_sessions="deny", preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is False


@pytest.mark.asyncio
async def test_listed_sessions_from_another_profile_do_not_admit():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.global_values[ADMISSION_LISTED_SESSIONS_KEY] = {
        "other": [session_admission_key_from_event(event)]
    }
    stage = await _stage(unlisted_sessions="deny", preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_invalid_unlisted_sessions_defaults_to_allow(caplog):
    caplog.set_level("WARNING", logger="astrbot")
    stage = AdmissionCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={"admission": {"unlisted_sessions": "nope"}},
            astrbot_config_id="default",
            preferences=_Preferences(),
            authorization=None,
        )
    )
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)

    await stage.process(event)

    assert event.is_stopped() is False
    assert "Invalid unlisted_sessions" in caplog.text


@pytest.mark.asyncio
async def test_blocked_sender_is_stopped_in_every_session():
    preferences = _Preferences()
    first = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    second = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-b",
        session_id="room-b",
    )
    sender_key = sender_admission_key_from_event(first)
    assert sender_key == sender_admission_key_from_event(second)
    preferences.sender_values[(sender_key, SESSION_SERVICE_CONFIG_KEY)] = {
        "blocked": True
    }
    stage = await _stage(preferences=preferences)

    await stage.process(first)
    await stage.process(second)

    assert first.is_stopped() is True
    assert second.is_stopped() is True


@pytest.mark.asyncio
async def test_private_chat_sender_block_does_not_read_session_overlay():
    preferences = _Preferences()
    event = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="user-1",
    )
    session_key = session_admission_key_from_event(event)
    sender_key = sender_admission_key_from_event(event)
    assert session_key != sender_key
    preferences.values[(session_key, SESSION_SERVICE_CONFIG_KEY)] = {
        "llm_enabled": True
    }
    preferences.sender_values[(sender_key, SESSION_SERVICE_CONFIG_KEY)] = {
        "blocked": True
    }
    stage = await _stage(preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_private_chat_session_overlay_does_not_list_the_sender():
    preferences = _Preferences()
    event = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="user-1",
    )
    preferences.values[
        (session_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"llm_enabled": True}
    stage = await _stage(unlisted_senders="deny", preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_blocked_sender_passthrough_allows_user_unblock_and_bot_status():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.sender_values[
        (sender_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"blocked": True}
    stage = await _stage(preferences=preferences)

    unblock = _with_handlers(
        make_real_event(message_type=MessageType.GROUP_MESSAGE),
        f"{BUILTIN_COMMANDS_MODULE}_user_unblock",
    )
    status = _with_handlers(
        make_real_event(message_type=MessageType.GROUP_MESSAGE),
        f"{BUILTIN_COMMANDS_MODULE}_bot_status",
    )
    enable = _with_handlers(
        make_real_event(message_type=MessageType.GROUP_MESSAGE),
        f"{BUILTIN_COMMANDS_MODULE}_bot_enable",
    )
    llm_on = _with_handlers(
        make_real_event(message_type=MessageType.GROUP_MESSAGE),
        f"{BUILTIN_COMMANDS_MODULE}_user_llm_on",
    )
    preferences.sender_values[
        (sender_admission_key_from_event(unblock), SESSION_SERVICE_CONFIG_KEY)
    ] = {"blocked": True}
    preferences.sender_values[
        (sender_admission_key_from_event(status), SESSION_SERVICE_CONFIG_KEY)
    ] = {"blocked": True}
    preferences.sender_values[
        (sender_admission_key_from_event(enable), SESSION_SERVICE_CONFIG_KEY)
    ] = {"blocked": True}
    preferences.sender_values[
        (sender_admission_key_from_event(llm_on), SESSION_SERVICE_CONFIG_KEY)
    ] = {"blocked": True}

    await stage.process(event)
    await stage.process(unblock)
    await stage.process(status)
    await stage.process(enable)
    await stage.process(llm_on)

    assert event.is_stopped() is True
    assert unblock.is_stopped() is False
    assert status.is_stopped() is False
    assert enable.is_stopped() is True
    assert llm_on.is_stopped() is True
    assert SENDER_BLOCKED_PASSTHROUGH_HANDLERS == {
        f"{BUILTIN_COMMANDS_MODULE}_user_unblock",
        f"{BUILTIN_COMMANDS_MODULE}_bot_status",
    }


@pytest.mark.asyncio
async def test_sender_llm_off_still_admits_the_event():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.sender_values[
        (sender_admission_key_from_event(event), SESSION_SERVICE_CONFIG_KEY)
    ] = {"llm_enabled": False}
    stage = await _stage(preferences=preferences)

    await stage.process(event)

    assert event.is_stopped() is False


@pytest.mark.asyncio
async def test_unlisted_senders_deny_stops_unwritten_sender():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    listed_llm = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-b",
        session_id="room-b",
    )
    listed_unblocked = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="user-2",
    )
    listed_llm.message_obj.sender.user_id = "vip-1"
    listed_unblocked.message_obj.sender.user_id = "vip-2"
    preferences.sender_values[
        (sender_admission_key_from_event(listed_llm), SESSION_SERVICE_CONFIG_KEY)
    ] = {"llm_enabled": True}
    preferences.sender_values[
        (
            sender_admission_key_from_event(listed_unblocked),
            SESSION_SERVICE_CONFIG_KEY,
        )
    ] = {"blocked": False}
    stage = await _stage(unlisted_senders="deny", preferences=preferences)

    await stage.process(event)
    await stage.process(listed_llm)
    await stage.process(listed_unblocked)

    assert event.is_stopped() is True
    assert listed_llm.is_stopped() is False
    assert listed_unblocked.is_stopped() is False


@pytest.mark.asyncio
async def test_invalid_unlisted_senders_defaults_to_allow(caplog):
    caplog.set_level("WARNING", logger="astrbot")
    stage = AdmissionCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={"admission": {"unlisted_senders": "nope"}},
            astrbot_config_id="default",
            preferences=_Preferences(),
            authorization=None,
        )
    )
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)

    await stage.process(event)

    assert event.is_stopped() is False
    assert "Invalid unlisted_senders" in caplog.text
