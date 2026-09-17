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
from astrbot.core.pipeline.admission_check.stage import AdmissionCheckStage
from astrbot.core.platform.message_type import MessageType
from tests.unit.test_waking_check_stage import make_real_event


class _Preferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], Any] = {}
        self.global_values: dict[str, Any] = {}

    async def session_get(self, umo: str, key: str, default: Any = None) -> Any:
        return self.values.get((umo, key), default)

    async def global_get(self, key: str, default: Any = None) -> Any:
        return self.global_values.get(key, default)


async def _stage(
    *,
    unlisted_sessions: str = "allow",
    preferences: _Preferences | None = None,
    authorization=None,
) -> AdmissionCheckStage:
    stage = AdmissionCheckStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={"admission": {"unlisted_sessions": unlisted_sessions}},
            astrbot_config_id="default",
            preferences=preferences or _Preferences(),
            authorization=authorization,
        )
    )
    return stage


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
async def test_sender_overlays_are_ignored_while_unlisted_senders_allow():
    preferences = _Preferences()
    event = make_real_event(message_type=MessageType.GROUP_MESSAGE)
    preferences.values[
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
