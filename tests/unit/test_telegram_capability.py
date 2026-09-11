from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.contracts.onebot import get_capability_descriptor
from astrbot.core.platform.contracts.telegram import (
    TELEGRAM_CAPABILITIES,
    TELEGRAM_CAPABILITY_NAME,
    TelegramButton,
    TelegramCallbackEvent,
    TelegramDeliveryReceipt,
)
from astrbot.core.platform.telegram_capability import TelegramCapability
from astrbot.core.star.filter.telegram_callback import TelegramCallbackFilter


def _event(*, platform: str = "telegram", callback=None):
    event = MagicMock()
    event.get_platform_name.return_value = platform
    event.get_platform_id.return_value = "telegram-main"
    event.get_sender_id.return_value = "42"
    event.route_identity = SimpleNamespace(target_id="-100#7")
    event.get_extra.return_value = callback
    return event


def test_telegram_contracts_validate_button_size_and_capability_registry():
    assert TelegramButton("Yes", "confirm").value == "confirm"
    with pytest.raises(ValueError):
        TelegramButton("", "confirm")
    with pytest.raises(ValueError):
        TelegramButton("Yes", "x" * 65)
    descriptor = get_capability_descriptor(TELEGRAM_CAPABILITY_NAME)
    assert descriptor in TELEGRAM_CAPABILITIES
    assert descriptor is not None
    assert descriptor.action("send_interactive") is not None


@pytest.mark.asyncio
async def test_telegram_facade_is_event_bound_and_passes_route_to_runtime():
    execution = MagicMock()
    execution.get_platform_capabilities.return_value = TELEGRAM_CAPABILITIES
    receipt = TelegramDeliveryReceipt(
        status="accepted",
        platform_id="telegram-main",
        target="-100#7",
        message_ids=("12",),
    )
    execution.invoke_platform_capability = AsyncMock(return_value=receipt)
    event = _event()
    facade = TelegramCapability(execution)
    client = facade.for_event(event)

    assert client is not None
    assert facade.supports(event, action="send_interactive")
    result = await client.messages.send_interactive(
        text="Continue?",
        buttons=[[{"text": "Yes", "value": "confirm"}]],
    )

    assert result is receipt
    execution.invoke_platform_capability.assert_awaited_once_with(
        "telegram-main",
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        text="Continue?",
        buttons=[[{"text": "Yes", "value": "confirm"}]],
        allowed_user_ids=("42",),
        allowed_roles=None,
        ttl_seconds=None,
        target="-100#7",
    )
    assert facade.for_event(_event(platform="discord")) is None


def test_telegram_callback_filter_matches_only_normalized_events():
    callback = TelegramCallbackEvent(
        callback_id="q",
        data="confirm",
        user_id="42",
        bot_id="7",
        chat_id="-100",
        message_id="12",
        session_id="-100",
    )
    assert TelegramCallbackFilter("confirm").filter(
        _event(callback=callback), AstrBotConfig()
    )
    assert not TelegramCallbackFilter("cancel").filter(
        _event(callback=callback), AstrBotConfig()
    )
    assert not TelegramCallbackFilter().filter(_event(), AstrBotConfig())
