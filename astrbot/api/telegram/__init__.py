"""Stable Telegram interaction contracts for Star plugins."""

from astrbot.core.platform.contracts.telegram import (
    TELEGRAM_CAPABILITIES,
    TELEGRAM_CAPABILITY_NAME,
    TELEGRAM_CAPABILITY_VERSION,
    TELEGRAM_INTERACTION_CAPABILITY,
    TelegramButton,
    TelegramCallbackEvent,
    TelegramDeliveryReceipt,
)

__all__ = [
    "TELEGRAM_CAPABILITIES",
    "TELEGRAM_CAPABILITY_NAME",
    "TELEGRAM_CAPABILITY_VERSION",
    "TELEGRAM_INTERACTION_CAPABILITY",
    "TelegramButton",
    "TelegramCallbackEvent",
    "TelegramDeliveryReceipt",
]
