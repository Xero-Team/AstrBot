"""Dependency-free Telegram interaction contracts.

The Telegram adapter owns the python-telegram-bot translation.  These DTOs are
the stable boundary used by plugins and the runtime capability registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .onebot import (
    OneBotActionInput,
    PlatformActionDescriptor,
    PlatformCapabilityDescriptor,
)

TELEGRAM_CAPABILITY_NAME = "telegram.interactions"
TELEGRAM_CAPABILITY_VERSION = "1.0"
TELEGRAM_PROTOCOL = "telegram"
TELEGRAM_CALLBACK_PREFIX = "ab1_"
TELEGRAM_CALLBACK_DATA_LIMIT = 64
TELEGRAM_BUTTON_TEXT_LIMIT = 64


def _bounded_text(value: str, *, field_name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Telegram {field_name} must be non-empty text")
    value = value.strip()
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"Telegram {field_name} exceeds {limit} bytes")
    return value


@dataclass(frozen=True, slots=True)
class TelegramButton:
    """One logical button in an inline keyboard row."""

    text: str
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "text",
            _bounded_text(
                self.text,
                field_name="button text",
                limit=TELEGRAM_BUTTON_TEXT_LIMIT,
            ),
        )
        object.__setattr__(
            self,
            "value",
            _bounded_text(
                self.value,
                field_name="button value",
                limit=TELEGRAM_CALLBACK_DATA_LIMIT,
            ),
        )


@dataclass(frozen=True, slots=True)
class TelegramCallbackEvent:
    """Normalized callback identity delivered to plugin handlers."""

    callback_id: str
    data: str
    user_id: str
    bot_id: str
    chat_id: str
    message_id: str
    session_id: str
    message_thread_id: str | None = None
    business_connection_id: str | None = None
    actor_role: str = "member"

    @property
    def value(self) -> str:
        """Alias for the plugin-defined button value."""
        return self.data


TelegramDeliveryStatus = Literal["accepted", "failed"]


@dataclass(frozen=True, slots=True)
class TelegramDeliveryReceipt:
    """Acceptance receipt for an interactive Telegram message."""

    status: TelegramDeliveryStatus
    platform_id: str
    target: str
    message_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "message_ids", tuple(str(item) for item in self.message_ids)
        )

    @property
    def message_id(self) -> str | None:
        return self.message_ids[0] if self.message_ids else None

    @property
    def success(self) -> bool:
        return self.status == "accepted"


_SEND_INTERACTIVE_INPUT = OneBotActionInput(
    fields=(
        ("target", "text"),
        ("text", "text"),
        ("buttons", "message"),
        ("allowed_user_ids", "message"),
        ("allowed_roles", "message"),
        ("ttl_seconds", "number"),
    ),
    required=("target", "text", "buttons"),
)
_ANSWER_CALLBACK_INPUT = OneBotActionInput(
    fields=(("callback_id", "text"), ("text", "text")),
    required=("callback_id",),
)

TELEGRAM_INTERACTION_CAPABILITY = PlatformCapabilityDescriptor(
    name=TELEGRAM_CAPABILITY_NAME,
    version=TELEGRAM_CAPABILITY_VERSION,
    protocol=TELEGRAM_PROTOCOL,
    actions=(
        PlatformActionDescriptor(
            name="send_interactive",
            wire_action="send_interactive",
            input_model=_SEND_INTERACTIVE_INPUT,
            return_model=TelegramDeliveryReceipt,
            retryable=False,
        ),
        PlatformActionDescriptor(
            name="answer_callback",
            wire_action="answer_callback",
            input_model=_ANSWER_CALLBACK_INPUT,
            return_model=bool,
            retryable=True,
        ),
    ),
)

TELEGRAM_CAPABILITIES = (TELEGRAM_INTERACTION_CAPABILITY,)


__all__ = [
    "TELEGRAM_CALLBACK_DATA_LIMIT",
    "TELEGRAM_CALLBACK_PREFIX",
    "TELEGRAM_BUTTON_TEXT_LIMIT",
    "TELEGRAM_CAPABILITIES",
    "TELEGRAM_CAPABILITY_NAME",
    "TELEGRAM_CAPABILITY_VERSION",
    "TELEGRAM_INTERACTION_CAPABILITY",
    "TELEGRAM_PROTOCOL",
    "TelegramButton",
    "TelegramCallbackEvent",
    "TelegramDeliveryReceipt",
]
