"""Small target-platform rendering policies for bridged messages."""

from __future__ import annotations

from collections.abc import Callable

from .message_i18n import (
    DEFAULT_LOCALE,
    chat_type_label,
    localize,
)
from .message_protocol import MessageEnvelope

SourceHeaderRenderer = Callable[[MessageEnvelope, str], str]


def _sender_name(envelope: MessageEnvelope, locale: str) -> str:
    sender = envelope.sender
    if sender is None:
        return localize(locale, "astrbot.msg.unknown_sender")
    return sender.name or sender.id or localize(locale, "astrbot.msg.unknown_sender")


def _compact(envelope: MessageEnvelope, locale: str) -> str:
    return localize(
        locale,
        "astrbot.msg.header.compact",
        platform=envelope.source_route.platform_id,
        name=_sender_name(envelope, locale),
    )


def _napcat(envelope: MessageEnvelope, locale: str) -> str:
    return localize(
        locale,
        "astrbot.msg.header.napcat",
        chat_type=chat_type_label(locale, envelope.source_route.message_type),
        name=_sender_name(envelope, locale),
    )


def _telegram(envelope: MessageEnvelope, locale: str) -> str:
    return localize(
        locale,
        "astrbot.msg.header.named",
        name=_sender_name(envelope, locale),
        platform=envelope.source_route.platform_id,
    )


def _discord(envelope: MessageEnvelope, locale: str) -> str:
    return localize(
        locale,
        "astrbot.msg.header.named_md",
        name=_sender_name(envelope, locale),
        platform=envelope.source_route.platform_id,
    )


def _slack(envelope: MessageEnvelope, locale: str) -> str:
    return localize(
        locale,
        "astrbot.msg.header.named",
        name=_sender_name(envelope, locale),
        platform=envelope.source_route.platform_id,
    )


def _line(envelope: MessageEnvelope, locale: str) -> str:
    return localize(
        locale,
        "astrbot.msg.header.named_bracket",
        name=_sender_name(envelope, locale),
        platform=envelope.source_route.platform_id,
    )


_RENDERERS: dict[str, SourceHeaderRenderer] = {
    "napcat": _napcat,
    "telegram": _telegram,
    "discord": _discord,
    "slack": _slack,
    "line": _line,
}


def render_source_header(
    envelope: MessageEnvelope,
    target_platform: str,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render a readable source header for a target platform and locale."""
    renderer = _RENDERERS.get(target_platform, _compact)
    return renderer(envelope, locale)


__all__ = ["render_source_header"]
