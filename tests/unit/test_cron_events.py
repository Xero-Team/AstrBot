"""Tests for synthetic cron event send accounting."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.send_result import PlatformSendResult


def _result(success: bool) -> PlatformSendResult:
    return PlatformSendResult(
        platform_id="test",
        success=success,
        target="session-1",
        message_count=1,
    )


@pytest.fixture
def cron_event():
    """Create a real event with controlled transport.

    Returns:
        Event and its transport mock.
    """
    send = AsyncMock(return_value=_result(True))
    event = CronMessageEvent(
        context=SimpleNamespace(send_message=send),
        session=MessageSession.from_str("test:FriendMessage:session-1"),
        message="scheduled task",
    )
    return event, send


@pytest.mark.asyncio
async def test_successful_send_records_send_oper(cron_event):
    event, send = cron_event

    result = await event.send(MessageChain().message("result"))
    await asyncio.sleep(0)

    assert result.success is True
    assert event._has_send_oper is True
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_send_does_not_record_send_oper(cron_event):
    event, send = cron_event
    send.return_value = _result(False)

    result = await event.send(MessageChain().message("result"))
    await asyncio.sleep(0)

    assert result.success is False
    assert event._has_send_oper is False
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_none_message_does_not_send(cron_event):
    event, send = cron_event

    await event.send(None)
    await asyncio.sleep(0)

    assert event._has_send_oper is False
    send.assert_not_awaited()


def test_cron_event_uses_sender_identity_for_the_sender(cron_event):
    event, _send = cron_event

    assert event.get_self_id() == ""
    assert event.get_sender_id() == "astrbot"
