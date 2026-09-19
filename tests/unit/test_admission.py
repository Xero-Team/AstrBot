"""Identity keys and overlay composition for session/sender admission."""

from types import SimpleNamespace

import pytest

from astrbot.core.auth.admission import (
    ConversationKind,
    SenderAdmissionOverlay,
    SessionAdmissionOverlay,
    UnlistedPolicy,
    compose_admission,
    composed_llm_enabled,
    conversation_kind_from_event,
    is_webchat_event,
    is_webchat_scope,
    overlay_flag_enabled,
    platform_instance_from_event,
    sender_admission_key_from_event,
    sender_admission_key_from_id,
    sender_overlay_from_config,
    session_admission_key,
    session_admission_key_from_event,
    session_admission_key_from_umo,
    session_overlay_from_config,
    unwritten_service_enabled,
)
from astrbot.core.auth.models import Subject
from astrbot.core.pipeline.waking_check.stage import (
    WakingCheckStage,
    build_unique_session_id,
)
from astrbot.core.platform.message_type import MessageType
from tests.unit.test_waking_check_stage import make_real_event


def test_session_admission_key_normalizes_components():
    assert (
        session_admission_key(
            platform_instance="napcat",
            conversation_kind="group",
            conversation_id="room-a",
        )
        == "session:napcat:group:room-a"
    )
    encoded = session_admission_key(
        platform_instance="napcat",
        conversation_kind=ConversationKind.PRIVATE,
        conversation_id="user with space",
    )
    assert encoded.startswith("session:napcat:private:b64-")


def test_group_session_key_ignores_unique_session_session_id():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    before = session_admission_key_from_event(event)
    event.session_id = build_unique_session_id(event)
    after = session_admission_key_from_event(event)

    assert event.session_id == "user-1_room-a"
    assert before == after == "session:napcat:group:room-a"
    assert "user-1" not in after

    event.session_id = event.get_sender_id()
    assert session_admission_key_from_event(event) == "session:napcat:group:room-a"


def test_unique_session_on_or_off_yields_the_same_group_session_key():
    off_event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    on_event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    off_stage = WakingCheckStage()
    on_stage = WakingCheckStage()
    off_stage.unique_session = False
    on_stage.unique_session = True

    off_stage._apply_unique_session(off_event)
    on_stage._apply_unique_session(on_event)

    assert off_event.session_id == "room-a"
    assert on_event.session_id == "user-1_room-a"
    assert session_admission_key_from_event(
        off_event
    ) == session_admission_key_from_event(on_event)
    assert session_admission_key_from_event(on_event) == "session:napcat:group:room-a"


def test_session_admission_key_from_umo_unwraps_unique_session_and_group_id():
    assert (
        session_admission_key_from_umo("napcat:GroupMessage:user-1_room-a")
        == "session:napcat:group:room-a"
    )
    assert (
        session_admission_key_from_umo(
            "napcat:GroupMessage:user-1_room-a",
            group_id="room-b",
        )
        == "session:napcat:group:room-b"
    )
    assert (
        session_admission_key_from_umo("napcat:FriendMessage:42")
        == "session:napcat:private:42"
    )
    assert session_admission_key_from_umo("session:qq:group:already") == (
        "session:qq:group:already"
    )
    assert session_admission_key_from_umo("not-a-umo") is None


def test_private_session_key_matches_subject_im_peer():
    event = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="user-1",
    )
    session_key = session_admission_key_from_event(event)
    sender_key = sender_admission_key_from_event(event)
    subject = Subject.im(
        platform_instance="napcat",
        bot_account_id="bot",
        sender_id="user-1",
    )

    assert conversation_kind_from_event(event) is ConversationKind.PRIVATE
    assert session_key == "session:napcat:private:user-1"
    assert sender_key == subject.id == "im:napcat:bot:user-1"
    assert session_key.rsplit(":", 1)[-1] == sender_key.rsplit(":", 1)[-1]


def test_sender_admission_key_from_id_requires_full_im_subject():
    assert sender_admission_key_from_id("im:napcat:bot:other") == "im:napcat:bot:other"
    assert sender_admission_key_from_id("IM:napcat:bot:other") == "im:napcat:bot:other"
    assert sender_admission_key_from_id("  im:napcat:bot:other  ") == (
        "im:napcat:bot:other"
    )
    assert sender_admission_key_from_id("99") is None
    assert sender_admission_key_from_id("im:foo") is None
    assert sender_admission_key_from_id("im:napcat:bot:") is None
    assert sender_admission_key_from_id("  ") is None


def test_sender_key_reuses_attached_im_subject():
    event = make_real_event(
        message_type=MessageType.GROUP_MESSAGE,
        group_id="room-a",
        session_id="room-a",
    )
    event.subject = Subject.im(
        platform_instance="napcat-a",
        bot_account_id="bot-2",
        sender_id="user-9",
    )
    assert sender_admission_key_from_event(event) == event.subject.id


def test_platform_instance_prefers_platform_id():
    event = SimpleNamespace(
        get_platform_id=lambda: "instance-1",
        get_platform_name=lambda: "napcat",
        get_message_type=lambda: MessageType.GROUP_MESSAGE,
        get_group_id=lambda: "room-a",
        get_sender_id=lambda: "user-1",
        get_self_id=lambda: "bot",
        get_session_id=lambda: "room-a",
    )
    assert platform_instance_from_event(event) == "instance-1"
    assert session_admission_key_from_event(event) == "session:instance-1:group:room-a"


def test_platform_and_conversation_fallbacks():
    named = SimpleNamespace(
        get_platform_name=lambda: "napcat",
        get_message_type=lambda: MessageType.GROUP_MESSAGE.value,
        get_group_id=lambda: "",
        get_sender_id=lambda: "",
        get_self_id=lambda: "",
        get_session_id=lambda: "",
        subject=Subject.guest("anon"),
    )
    assert platform_instance_from_event(named) == "napcat"
    assert conversation_kind_from_event(named) is ConversationKind.GROUP
    assert session_admission_key_from_event(named) == "session:napcat:group:unknown"
    assert sender_admission_key_from_event(named) == "im:napcat:default:unknown"

    unknown = SimpleNamespace(
        get_platform_id=lambda: "",
        get_platform_name=lambda: "",
        get_message_type=lambda: MessageType.OTHER_MESSAGE,
        get_group_id=lambda: "",
        get_sender_id=lambda: "",
        get_self_id=lambda: "",
        get_session_id=lambda: "peer-9",
    )
    assert platform_instance_from_event(unknown) == "unknown"
    assert conversation_kind_from_event(unknown) is ConversationKind.PRIVATE
    assert session_admission_key_from_event(unknown) == "session:unknown:private:peer-9"


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, SessionAdmissionOverlay()),
        (
            {"llm_enabled": False, "tts_enabled": True},
            SessionAdmissionOverlay(llm_enabled=False, listed=True),
        ),
        (
            {"session_enabled": False, "session_blocked": True, "llm_enabled": True},
            SessionAdmissionOverlay(
                session_enabled=False,
                session_blocked=True,
                llm_enabled=True,
                listed=True,
            ),
        ),
        ("bad", SessionAdmissionOverlay()),
        ({"session_blocked": "yes"}, SessionAdmissionOverlay()),
        ({"session_enabled": None, "tts_enabled": True}, SessionAdmissionOverlay()),
    ],
)
def test_session_overlay_from_config(config, expected):
    assert session_overlay_from_config(config) == expected


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, SenderAdmissionOverlay()),
        (
            {"blocked": True, "llm_enabled": False},
            SenderAdmissionOverlay(blocked=True, llm_enabled=False, listed=True),
        ),
        ({"blocked": "yes"}, SenderAdmissionOverlay()),
        (None, SenderAdmissionOverlay()),
    ],
)
def test_sender_overlay_from_config(config, expected):
    assert sender_overlay_from_config(config) == expected


@pytest.mark.parametrize(
    (
        "label",
        "session_config",
        "sender_config",
        "unlisted_sessions",
        "unlisted_senders",
        "admit_event",
        "admit_llm",
    ),
    [
        (
            "unwritten_umo_and_uid",
            {},
            {},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            True,
            False,
        ),
        (
            "session_open_uid_unwritten",
            {"session_enabled": True},
            {},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            True,
            False,
        ),
        (
            "session_llm_off_uid_unwritten",
            {"llm_enabled": False},
            {},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            True,
            False,
        ),
        (
            "session_open_sender_llm_off",
            {"session_enabled": True},
            {"llm_enabled": False},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            True,
            False,
        ),
        (
            "vip_sender_overrides_session_llm_off",
            {"llm_enabled": False},
            {"llm_enabled": True},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            True,
            True,
        ),
        (
            "sender_blocked_drops_event",
            {"session_enabled": True},
            {"blocked": True},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            False,
            False,
        ),
        (
            "session_blocked_overrides_sender_llm",
            {"session_blocked": True},
            {"llm_enabled": True},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            False,
            False,
        ),
        (
            "unlisted_sessions_deny_without_allow",
            {},
            {"llm_enabled": True},
            UnlistedPolicy.DENY,
            UnlistedPolicy.ALLOW,
            False,
            False,
        ),
        (
            "unlisted_sessions_deny_with_session_overlay",
            {"session_enabled": True},
            {},
            UnlistedPolicy.DENY,
            UnlistedPolicy.ALLOW,
            True,
            False,
        ),
        (
            "unlisted_senders_deny_without_uid_allow",
            {"session_enabled": True},
            {},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.DENY,
            False,
            False,
        ),
        (
            "unlisted_senders_deny_with_uid_allow",
            {},
            {"llm_enabled": True},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.DENY,
            True,
            True,
        ),
        (
            "unlisted_senders_deny_blocked_is_not_allow",
            {},
            {"blocked": True},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.DENY,
            False,
            False,
        ),
        (
            "unlisted_senders_deny_listed_llm_off_still_admits_event",
            {},
            {"llm_enabled": False},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.DENY,
            True,
            False,
        ),
        (
            "session_disabled_still_admits_event",
            {"session_enabled": False},
            {},
            UnlistedPolicy.ALLOW,
            UnlistedPolicy.ALLOW,
            True,
            False,
        ),
        (
            "invalid_overlay_values_are_unlisted",
            {"session_blocked": "yes"},
            {"blocked": "yes"},
            UnlistedPolicy.DENY,
            UnlistedPolicy.DENY,
            False,
            False,
        ),
    ],
)
def test_compose_admission_parent_table(
    label,
    session_config,
    sender_config,
    unlisted_sessions,
    unlisted_senders,
    admit_event,
    admit_llm,
):
    _ = label
    decision = compose_admission(
        session_overlay_from_config(session_config),
        sender_overlay_from_config(sender_config),
        unlisted_sessions=unlisted_sessions,
        unlisted_senders=unlisted_senders,
    )
    assert decision.admit_event is admit_event
    assert decision.admit_llm is admit_llm


def test_composed_llm_enabled_ignores_event_drop_flags():
    session = session_overlay_from_config(
        {"session_blocked": True, "llm_enabled": True}
    )
    sender = sender_overlay_from_config({"llm_enabled": True})
    assert composed_llm_enabled(session, sender) is True
    decision = compose_admission(session, sender)
    assert decision.admit_event is False
    assert decision.admit_llm is False
    assert decision.session_blocked is True


def test_compose_admission_exposes_session_enabled_without_dropping_event():
    decision = compose_admission(
        session_overlay_from_config({"session_enabled": False}),
        sender_overlay_from_config({}),
    )
    assert decision.admit_event is True
    assert decision.session_enabled is False


def test_unwritten_service_defaults_webchat_on_im_off():
    assert unwritten_service_enabled("webchat:FriendMessage:webchat!u!c") is True
    assert unwritten_service_enabled("session:webchat:private:cid") is True
    assert unwritten_service_enabled("napcat:GroupMessage:room-a") is False
    assert unwritten_service_enabled("napcat:FriendMessage:42") is False
    assert unwritten_service_enabled("session:napcat:group:room-a") is False
    assert unwritten_service_enabled("") is False
    assert is_webchat_scope("webchat") is False
    assert is_webchat_scope("webchat:FriendMessage:x") is True
    assert is_webchat_scope("session:webchat:private:x") is True
    assert is_webchat_scope("napcat:FriendMessage:42") is False
    assert overlay_flag_enabled(None, scope_id="napcat:GroupMessage:1") is False
    assert overlay_flag_enabled(True, scope_id="napcat:GroupMessage:1") is True
    assert overlay_flag_enabled("no", scope_id="webchat:FriendMessage:x") is True

    webchat = make_real_event(
        message_type=MessageType.FRIEND_MESSAGE,
        group_id="",
        session_id="webchat!u!c",
        platform_id="webchat",
    )
    assert is_webchat_event(webchat) is True
    assert (
        is_webchat_event(make_real_event(message_type=MessageType.GROUP_MESSAGE))
        is False
    )
    named_webchat = SimpleNamespace(
        get_platform_id=lambda: "napcat",
        get_platform_name=lambda: "webchat",
    )
    assert is_webchat_event(named_webchat) is False
    blank_id = SimpleNamespace(
        get_platform_id=lambda: "  ",
        get_platform_name=lambda: "webchat",
    )
    assert is_webchat_event(blank_id) is True

    unwritten = compose_admission(
        session_overlay_from_config({}),
        sender_overlay_from_config({}),
    )
    assert unwritten.session_enabled is False
    assert unwritten.admit_llm is False
    webchat_decision = compose_admission(
        session_overlay_from_config({}),
        sender_overlay_from_config({}),
        unwritten_enabled=True,
    )
    assert webchat_decision.session_enabled is True
    assert webchat_decision.admit_llm is True
