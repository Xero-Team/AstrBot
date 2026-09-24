"""SessionServiceManager admission queries preserve empty-UID behavior."""

from typing import Any

import pytest

from astrbot.core.auth.admission import (
    sender_admission_key_from_event,
    session_admission_key_from_event,
)
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.session_llm_manager import (
    SessionServiceManager,
    sender_service_config,
)
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
        ({}, False, False, False),
        ({"session_enabled": True, "llm_enabled": True}, True, False, True),
        ({"session_enabled": False}, False, False, False),
        ({"session_blocked": True}, False, True, False),
        ({"llm_enabled": False}, False, False, False),
        ({"session_blocked": "yes", "llm_enabled": "no"}, False, False, False),
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
        preferences.values[
            (
                "umo",
                session_admission_key_from_event(event),
                "session_service_config",
            )
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
    session_key = session_admission_key_from_event(event)
    preferences = _Preferences()
    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = {
        "llm_enabled": False
    }
    preferences.values[("umo", session_key, "session_service_config")] = {
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
    assert await manager.should_process_llm_request(event) is False
    assert await manager.is_session_enabled(event.unified_msg_origin) is False


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

    assert await manager.is_session_enabled(event.unified_msg_origin) is False
    assert await manager.is_session_blocked(event.unified_msg_origin) is False
    assert await manager.should_process_llm_request(event) is False
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
async def test_tts_non_dict_and_invalid_values_default_disabled():
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

    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is False
    assert await manager.should_process_tts_request(event) is False

    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = {
        "tts_enabled": "no",
        "llm_enabled": False,
    }
    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is False
    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is False

    await manager.set_tts_status_for_session(event.unified_msg_origin, False)
    assert preferences.values[
        ("umo", event.unified_msg_origin, "session_service_config")
    ] == {
        "tts_enabled": False,
        "llm_enabled": False,
    }
    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is False


@pytest.mark.asyncio
async def test_umo_llm_overlay_is_inert_for_event_admission():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="user-1_room-a",
    )
    preferences = _Preferences()
    preferences.values[("umo", event.unified_msg_origin, "session_service_config")] = {
        "llm_enabled": False
    }
    preferences.values[
        (
            "umo",
            session_admission_key_from_event(event),
            "session_service_config",
        )
    ] = {"llm_enabled": True}
    manager = _manager(preferences)

    assert await manager.should_process_llm_request(event) is True
    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is True


@pytest.mark.asyncio
async def test_canonical_session_llm_disable_applies_to_unique_session_members():
    first = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="user-1_room-a",
    )
    second = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="user-2_room-a",
    )
    preferences = _Preferences()
    preferences.values[
        (
            "umo",
            session_admission_key_from_event(first),
            "session_service_config",
        )
    ] = {"llm_enabled": False}
    manager = _manager(preferences)

    assert session_admission_key_from_event(first) == session_admission_key_from_event(
        second
    )
    assert await manager.should_process_llm_request(first) is False
    assert await manager.should_process_llm_request(second) is False


@pytest.mark.asyncio
async def test_llm_session_setters_write_canonical_key():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="user-1_room-a",
    )
    preferences = _Preferences()
    manager = _manager(preferences)

    await manager.set_llm_status_for_session(event.unified_msg_origin, False)

    canonical = session_admission_key_from_event(event)
    assert preferences.values[("umo", canonical, "session_service_config")] == {
        "llm_enabled": False
    }
    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is False
    assert await manager.should_process_llm_request(event) is False


@pytest.mark.asyncio
async def test_sender_setters_write_subject_im_key_and_preserve_llm():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    sender_key = sender_admission_key_from_event(event)
    preferences = _Preferences()
    preferences.values[("sender", sender_key, "session_service_config")] = {
        "llm_enabled": True
    }
    manager = _manager(preferences)

    await manager.set_sender_blocked(event, True)

    assert preferences.values[("sender", sender_key, "session_service_config")] == {
        "blocked": True,
        "llm_enabled": True,
    }
    assert await manager.is_sender_blocked(event) is True
    assert await manager.should_process_llm_request(event) is True

    await manager.set_sender_blocked(sender_key, False)
    await manager.set_sender_llm_enabled(event, False)
    assert preferences.values[("sender", sender_key, "session_service_config")] == {
        "blocked": False,
        "llm_enabled": False,
    }
    assert await manager.should_process_llm_request(event) is False


@pytest.mark.asyncio
async def test_sender_setters_replace_non_dict_and_drop_extra_keys():
    sender_key = "im:napcat:bot:user-1"
    preferences = _Preferences()
    preferences.values[("sender", sender_key, "session_service_config")] = "bad"
    manager = _manager(preferences)

    await manager.set_sender_blocked(sender_key, True)
    assert preferences.values[("sender", sender_key, "session_service_config")] == {
        "blocked": True
    }

    preferences.values[("sender", sender_key, "session_service_config")] = {
        "blocked": True,
        "llm_enabled": True,
        "session_enabled": False,
        "tts_enabled": False,
        "prompt_id": "p1",
        "kb_ids": ["kb-1"],
        "provider_id": "openai",
    }
    await manager.set_sender_llm_enabled(sender_key, False)
    assert preferences.values[("sender", sender_key, "session_service_config")] == {
        "blocked": True,
        "llm_enabled": False,
    }


def test_sender_service_config_clears_none_fields():
    existing = {"blocked": True, "llm_enabled": False, "prompt_id": "p1"}

    assert sender_service_config(existing, llm_enabled=None) == {"blocked": True}
    assert sender_service_config(existing, blocked=None, llm_enabled=None) == {}
    assert sender_service_config(existing, llm_enabled=True) == {
        "blocked": True,
        "llm_enabled": True,
    }


@pytest.mark.asyncio
async def test_webchat_unwritten_service_flags_default_enabled():
    event = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="webchat!user!cid",
        platform_id="webchat",
    )
    manager = _manager()

    assert await manager.is_session_enabled(event.unified_msg_origin) is True
    assert await manager.is_tts_enabled_for_session(event.unified_msg_origin) is True
    assert await manager.is_llm_enabled_for_session(event.unified_msg_origin) is True
    assert await manager.should_process_llm_request(event) is True
    assert await manager.should_process_tts_request(event) is True


@pytest.mark.asyncio
async def test_sender_llm_setter_follows_composition_table():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    session_key = session_admission_key_from_event(event)
    preferences = _Preferences()
    preferences.values[("umo", session_key, "session_service_config")] = {
        "llm_enabled": False
    }
    manager = _manager(preferences)

    assert await manager.should_process_llm_request(event) is False

    await manager.set_sender_llm_enabled(event, True)
    assert await manager.should_process_llm_request(event) is True

    await manager.set_sender_llm_enabled(event, False)
    preferences.values[("umo", session_key, "session_service_config")] = {
        "llm_enabled": True
    }
    assert await manager.should_process_llm_request(event) is False


@pytest.mark.asyncio
async def test_private_chat_session_and_sender_keys_stay_distinct():
    event = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="user-1",
    )
    session_key = session_admission_key_from_event(event)
    sender_key = sender_admission_key_from_event(event)
    assert session_key != sender_key
    assert session_key.startswith("session:")
    assert sender_key.startswith("im:")

    preferences = _Preferences()
    preferences.values[("umo", session_key, "session_service_config")] = {
        "llm_enabled": False
    }
    manager = _manager(preferences)

    assert await manager.should_process_llm_request(event) is False
    assert await manager.is_sender_blocked(event) is False

    await manager.set_sender_llm_enabled(event, True)
    assert await manager.should_process_llm_request(event) is True
    assert preferences.values[("umo", session_key, "session_service_config")] == {
        "llm_enabled": False
    }

    await manager.set_sender_blocked(event, True)
    assert await manager.is_sender_blocked(event) is True
    assert await manager.is_session_blocked(event.unified_msg_origin) is False
    assert preferences.values[("sender", sender_key, "session_service_config")] == {
        "blocked": True,
        "llm_enabled": True,
    }
