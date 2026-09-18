"""Canonical admission identity keys and overlay composition.

Session keys ignore unique-session rewrites of ``session_id``. Sender keys reuse
``Subject.im``. Composition is pure; persistence owners still choose the
preference scope they read.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from astrbot.core.auth.models import Subject, normalize_subject_component
from astrbot.core.platform.message_type import MessageType

SESSION_SERVICE_CONFIG_KEY = "session_service_config"
ADMISSION_LISTED_SESSIONS_KEY = "admission_listed_sessions"
_SESSION_LISTED_FIELDS = ("session_enabled", "session_blocked", "llm_enabled")
_UNIQUE_SESSION_GROUP_SEPARATORS = ("%", "_")


class UnlistedPolicy(StrEnum):
    """Default for identities that have no explicit overlay."""

    ALLOW = "allow"
    DENY = "deny"


class ConversationKind(StrEnum):
    """Admission conversation axis. Group vs private, not unique-session."""

    GROUP = "group"
    PRIVATE = "private"


class AdmissionEvent(Protocol):
    """Inbound facts needed to mint admission keys without importing events."""

    def get_platform_name(self) -> str:
        raise NotImplementedError

    def get_sender_id(self) -> str:
        raise NotImplementedError

    def get_self_id(self) -> str:
        raise NotImplementedError

    def get_group_id(self) -> str:
        raise NotImplementedError

    def get_session_id(self) -> str:
        raise NotImplementedError

    def get_message_type(self) -> MessageType | str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SessionAdmissionOverlay:
    """UMO-scoped admission fields. ``None`` means unwritten."""

    session_enabled: bool | None = None
    session_blocked: bool = False
    llm_enabled: bool | None = None
    listed: bool = False


@dataclass(frozen=True, slots=True)
class SenderAdmissionOverlay:
    """UID-scoped admission fields. ``None`` means follow the session."""

    blocked: bool = False
    llm_enabled: bool | None = None
    listed: bool = False


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Event and built-in LLM admission after overlay composition."""

    admit_event: bool
    admit_llm: bool
    session_enabled: bool
    session_blocked: bool
    sender_blocked: bool


def platform_instance_from_event(event: AdmissionEvent) -> str:
    """Return the platform instance id used in identity keys.

    Args:
        event: Inbound event exposing platform accessors.

    Returns:
        ``get_platform_id()`` when it is a non-empty string, otherwise the
        platform name, otherwise ``unknown``.
    """

    get_platform_id = getattr(event, "get_platform_id", None)
    platform_id = get_platform_id() if callable(get_platform_id) else None
    if isinstance(platform_id, str) and platform_id.strip():
        return platform_id
    name = event.get_platform_name()
    if isinstance(name, str) and name.strip():
        return name
    return "unknown"


def conversation_kind_from_event(event: AdmissionEvent) -> ConversationKind:
    """Return group vs private from the inbound message type.

    Args:
        event: Inbound event.

    Returns:
        ``group`` only for ``MessageType.GROUP_MESSAGE``; every other type is
        ``private``.
    """

    message_type = event.get_message_type()
    if message_type is MessageType.GROUP_MESSAGE:
        return ConversationKind.GROUP
    if message_type == MessageType.GROUP_MESSAGE.value:
        return ConversationKind.GROUP
    return ConversationKind.PRIVATE


def session_admission_key(
    *,
    platform_instance: str,
    conversation_kind: ConversationKind | str,
    conversation_id: str,
) -> str:
    """Build ``session:{platform_instance}:{group|private}:{id}``.

    Args:
        platform_instance: Adapter instance id, not a display name when both
            exist.
        conversation_kind: ``group`` or ``private``.
        conversation_id: Group id or private peer id.

    Returns:
        Canonical session admission key with normalized components.
    """

    kind = ConversationKind(conversation_kind)
    return (
        "session:"
        f"{normalize_subject_component(platform_instance, 'platform instance')}:"
        f"{kind.value}:"
        f"{normalize_subject_component(conversation_id, 'conversation id')}"
    )


def session_admission_key_from_event(event: AdmissionEvent) -> str:
    """Mint a session key that ignores unique-session ``session_id`` rewrites.

    Group messages always use ``get_group_id()``. Private messages use the
    peer ``sender_id`` (falling back to ``session_id``).

    Args:
        event: Inbound event. ``session_id`` may already be unique-session
            rewritten.

    Returns:
        Canonical session admission key.
    """

    kind = conversation_kind_from_event(event)
    if kind is ConversationKind.GROUP:
        conversation_id = str(event.get_group_id() or "").strip() or "unknown"
    else:
        conversation_id = (
            str(event.get_sender_id() or event.get_session_id() or "").strip()
            or "unknown"
        )
    return session_admission_key(
        platform_instance=platform_instance_from_event(event),
        conversation_kind=kind,
        conversation_id=conversation_id,
    )


def group_conversation_id_from_session_id(session_id: str) -> str:
    """Return the group id encoded in a unique-session ``session_id``.

    Unique-session builders use ``sender_id_group_id`` or ``sender_id%group_id``.
    An explicit group id is preferred by callers; this helper only unwraps the
    stored session fragment.

    Args:
        session_id: UMO session fragment, possibly unique-session rewritten.

    Returns:
        Suffix after the last unique-session separator, or ``session_id``.
    """

    value = str(session_id or "").strip()
    if not value:
        return value
    for separator in _UNIQUE_SESSION_GROUP_SEPARATORS:
        if separator not in value:
            continue
        suffix = value.rsplit(separator, 1)[-1].strip()
        if suffix:
            return suffix
    return value


def session_admission_key_from_umo(
    umo: str,
    *,
    group_id: str | None = None,
) -> str | None:
    """Mint a canonical session key from a UMO or existing session key.

    Group UMOs use ``group_id`` when provided, otherwise unwrap a
    unique-session ``session_id``. Private UMOs use the peer session id.

    Args:
        umo: Unified message origin or canonical ``session:`` key.
        group_id: Explicit group id from Dashboard or an inbound event.

    Returns:
        Canonical session key, or ``None`` when ``umo`` cannot be parsed.
    """

    entry = str(umo or "").strip()
    if not entry:
        return None
    if entry.startswith("session:"):
        return entry
    parts = entry.split(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
        return None
    platform_id, message_type, session_id = parts
    try:
        parsed_type = MessageType(message_type)
    except ValueError:
        return None
    if parsed_type is MessageType.GROUP_MESSAGE:
        conversation_id = str(
            group_id or ""
        ).strip() or group_conversation_id_from_session_id(session_id)
        kind = ConversationKind.GROUP
    else:
        conversation_id = session_id
        kind = ConversationKind.PRIVATE
    if not str(conversation_id or "").strip():
        return None
    return session_admission_key(
        platform_instance=platform_id,
        conversation_kind=kind,
        conversation_id=conversation_id,
    )


def sender_admission_key_from_event(event: AdmissionEvent) -> str:
    """Return the sender key, reusing ``Subject.im`` when possible.

    Args:
        event: Inbound event. An attached IM ``subject`` is preferred.

    Returns:
        ``im:{platform_instance}:{bot_account_id}:{sender_id}``.
    """

    subject = getattr(event, "subject", None)
    if isinstance(subject, Subject) and subject.kind == "im":
        return subject.id
    return Subject.im(
        platform_instance=platform_instance_from_event(event),
        bot_account_id=str(event.get_self_id() or "").strip() or "default",
        sender_id=str(event.get_sender_id() or "").strip() or "unknown",
    ).id


def sender_admission_key_from_id(token: str) -> str | None:
    """Mint a sender overlay key from a full ``im:`` subject id.

    Args:
        token: Full ``im:{platform}:{bot}:{sender}`` subject id.

    Returns:
        The normalized sender preference scope id, or None when the token
        is empty or cannot be minted.
    """
    sender_id = token.strip()
    if not sender_id.lower().startswith("im:"):
        return None
    parts = sender_id.split(":", 3)
    if len(parts) != 4 or not all(part.strip() for part in parts):
        return None
    try:
        return Subject.im(
            platform_instance=parts[1].strip(),
            bot_account_id=parts[2].strip(),
            sender_id=parts[3].strip(),
        ).id
    except ValueError:
        return None


def session_overlay_from_config(config: object) -> SessionAdmissionOverlay:
    """Parse a ``session_service_config`` mapping into a session overlay.

    Args:
        config: Preference value, typically a dict.

    Returns:
        Overlay with unwritten fields left as defaults.
    """

    if not isinstance(config, dict):
        return SessionAdmissionOverlay()
    session_enabled = config.get("session_enabled")
    session_blocked = config.get("session_blocked")
    llm_enabled = config.get("llm_enabled")
    listed = any(isinstance(config.get(key), bool) for key in _SESSION_LISTED_FIELDS)
    return SessionAdmissionOverlay(
        session_enabled=session_enabled if isinstance(session_enabled, bool) else None,
        session_blocked=session_blocked if isinstance(session_blocked, bool) else False,
        llm_enabled=llm_enabled if isinstance(llm_enabled, bool) else None,
        listed=listed,
    )


def sender_overlay_from_config(config: object) -> SenderAdmissionOverlay:
    """Parse a sender-scoped ``session_service_config`` mapping.

    Args:
        config: Preference value, typically a dict.

    Returns:
        Overlay with unwritten fields left as defaults.
    """

    if not isinstance(config, dict):
        return SenderAdmissionOverlay()
    blocked = config.get("blocked")
    llm_enabled = config.get("llm_enabled")
    listed = any(
        isinstance(config.get(key), bool) for key in ("blocked", "llm_enabled")
    )
    return SenderAdmissionOverlay(
        blocked=blocked if isinstance(blocked, bool) else False,
        llm_enabled=llm_enabled if isinstance(llm_enabled, bool) else None,
        listed=listed,
    )


def composed_llm_enabled(
    session: SessionAdmissionOverlay,
    sender: SenderAdmissionOverlay,
) -> bool:
    """Return the LLM overlay after sender specificity, ignoring event drops.

    Unwritten session LLM defaults to enabled. An unwritten sender follows the
    session. A written sender value wins, including VIP enable over a disabled
    session.

    Args:
        session: UMO overlay.
        sender: UID overlay.

    Returns:
        Whether built-in LLM is enabled by overlays alone.
    """

    session_llm = True if session.llm_enabled is None else session.llm_enabled
    if sender.llm_enabled is None:
        return session_llm
    return sender.llm_enabled


def compose_admission(
    session: SessionAdmissionOverlay,
    sender: SenderAdmissionOverlay,
    *,
    unlisted_sessions: UnlistedPolicy | str = UnlistedPolicy.ALLOW,
    unlisted_senders: UnlistedPolicy | str = UnlistedPolicy.ALLOW,
) -> AdmissionDecision:
    """Compose session and sender overlays into one admission decision.

    Refusal wins over allow. Sender LLM overlays are more specific than
    session LLM overlays. ``session_blocked`` and sender ``blocked`` drop the
    event and therefore the built-in LLM; a personal LLM exception cannot
    revive a blocked session.

    Args:
        session: UMO overlay.
        sender: UID overlay.
        unlisted_sessions: Policy when the session has no overlay.
        unlisted_senders: Policy when the sender has no allow overlay.

    Returns:
        Event and LLM admission plus the resolved session/sender flags.
    """

    session_policy = UnlistedPolicy(unlisted_sessions)
    sender_policy = UnlistedPolicy(unlisted_senders)
    session_enabled = (
        True if session.session_enabled is None else session.session_enabled
    )
    session_blocked = session.session_blocked
    sender_blocked = sender.blocked
    session_denied = session_policy is UnlistedPolicy.DENY and not session.listed
    sender_denied = sender_policy is UnlistedPolicy.DENY and not (
        sender.listed and not sender.blocked
    )
    refused = session_blocked or sender_blocked or session_denied or sender_denied
    return AdmissionDecision(
        admit_event=not refused,
        admit_llm=not refused and composed_llm_enabled(session, sender),
        session_enabled=session_enabled,
        session_blocked=session_blocked,
        sender_blocked=sender_blocked,
    )
