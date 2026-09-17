"""SessionServiceManager admission queries preserve empty-UID behavior."""

from typing import Any

import pytest

from astrbot.core.auth.admission import sender_admission_key_from_event
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.session_llm_manager import SessionServiceManager
from tests.unit.test_waking_check_stage import make_real_event


class _Preferences:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], Any] = {}
        self.gets: list[tuple[str, str, str]] = []

    async def get_async(
        self,
        scope: str,
        scope_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        self.gets.append((scope, scope_id, key))
        return self.values.get((scope, scope_id, key), default)

    async def put_async(
        self,
        scope: str,
        scope_id: str,
        key: str,
        value: Any,
    ) -> None:
        self.values[(scope, scope_id, key)] = value


def _manager(preferences: _Preferences | None = None) -> SessionServiceManager:
    return SessionServiceManager(preferences or _Preferences())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("umo_config", "enabled", "blocked", "llm"),
    [
        ({}, True, False, True),
        ({"session_enabled": True, "llm_enabled": True}, True, False, True),
        ({"session_enabled": False}, False, False, True),
        ({"session_blocked": True}, True, True, True),
        ({"llm_enabled": False}, True, False, False),
        ({"session_blocked": "yes", "llm_enabled": "no"}, True, False, True),
    ],
)
async def test_empty_uid_matches_current_session_switches(
    umo_config, enabled, blocked, llm
):
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    preferences = _Preferences()
    if umo_config:
        preferences.values[
            ("umo", event.unified_msg_origin, "session_service_config")
        ] = umo_config
    manager = _manager(preferences)

    assert await manager.is_session_enabled(event.unified_msg_origin) is enabled
    assert await manager.is_session_blocked(event.unified_msg_origin) is blocked
    assert await manager.should_process_llm_request(event) is llm
    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is llm
    assert await manager.is_sender_blocked(event) is False
    assert (
        "sender",
        sender_admission_key_from_event(event),
        "session_service_config",
    ) in ((scope, scope_id, key) for scope, scope_id, key in preferences.gets)


@pytest.mark.asyncio
async def test_sender_scope_is_readable_and_vip_overrides_session_llm():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    sender_key = sender_admission_key_from_event(event)
    preferences = _Preferences()
    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = {
        "llm_enabled": False
    }
    preferences.values[("sender", sender_key, "session_service_config")] = {
        "llm_enabled": True
    }
    manager = _manager(preferences)

    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is False
    assert await manager.should_process_llm_request(event) is True
    assert await manager.is_sender_blocked(event) is False


@pytest.mark.asyncio
async def test_sender_blocked_overlay_does_not_change_empty_session_llm():
    event = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="user-1",
    )
    preferences = _Preferences()
    preferences.values[
        ("sender", sender_admission_key_from_event(event), "session_service_config")
    ] = {"blocked": True}
    manager = _manager(preferences)

    assert await manager.is_sender_blocked(event) is True
    assert await manager.should_process_llm_request(event) is True
    assert await manager.is_session_enabled(event.unified_msg_origin) is True


@pytest.mark.asyncio
async def test_non_dict_service_config_is_treated_as_empty():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    preferences = _Preferences()
    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = (
        "bad"
    )
    preferences.values[
        ("sender", sender_admission_key_from_event(event), "session_service_config")
    ] = ["blocked"]
    manager = _manager(preferences)

    assert await manager.is_session_enabled(event.unified_msg_origin) is True
    assert await manager.is_session_blocked(event.unified_msg_origin) is False
    assert await manager.should_process_llm_request(event) is True
    assert await manager.is_sender_blocked(event) is False


@pytest.mark.asyncio
async def test_setters_replace_non_dict_service_config():
    preferences = _Preferences()
    preferences.values[("umo", "sid", "session_service_config")] = "bad"
    manager = _manager(preferences)

    await manager.set_llm_status_for_session("sid", False)
    assert preferences.values[("umo", "sid", "session_service_config")] == {
        "llm_enabled": False
    }

    preferences.values[("umo", "sid", "session_service_config")] = ["blocked"]
    await manager.set_session_blocked("sid", True)
    assert preferences.values[("umo", "sid", "session_service_config")] == {
        "session_blocked": True
    }

    preferences.values[("umo", "sid", "session_service_config")] = "bad"
    await manager.set_tts_status_for_session("sid", False)
    assert preferences.values[("umo", "sid", "session_service_config")] == {
        "tts_enabled": False
    }


@pytest.mark.asyncio
async def test_tts_non_dict_and_invalid_values_default_enabled():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    preferences = _Preferences()
    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = (
        "bad"
    )
    manager = _manager(preferences)

    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is True
    assert await manager.should_process_tts_request(event) is True

    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = {
        "tts_enabled": "no",
        "llm_enabled": False,
    }
    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is True
    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is False

    await manager.set_tts_status_for_session(event.unified_msg_origin, False)
    assert preferences.values[
        ("umo", event.unified_msg_origin, "session_service_config")
    ] == {
        "tts_enabled": False,
        "llm_enabled": False,
    }
    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is False
