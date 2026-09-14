import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from telegram.error import RetryAfter

from astrbot.core.platform.sources.telegram.rate_limit import (
    LimitedTelegramClient,
    TelegramDeliveryLimiter,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.now += delay
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_limiter_reserves_global_and_chat_slots_for_concurrent_chats():
    clock = FakeClock()
    limiter = TelegramDeliveryLimiter(
        global_interval=1.0,
        chat_interval=0.0,
        clock=clock.time,
        sleep=clock.sleep,
    )
    calls: list[tuple[str, float]] = []

    async def deliver(chat: str) -> None:
        await limiter.call(
            chat, lambda: _record(calls, chat, clock.now), retryable=False
        )

    async def _run() -> None:
        await asyncio.gather(deliver("one"), deliver("two"))

    async def _record(target: list[tuple[str, float]], chat: str, now: float) -> None:
        target.append((chat, now))

    await _run()
    assert calls == [("one", 0.0), ("two", 1.0)]


@pytest.mark.asyncio
async def test_limiter_retries_retry_after_within_budget():
    clock = FakeClock()
    limiter = TelegramDeliveryLimiter(
        global_interval=0.0,
        chat_interval=0.0,
        max_retries=2,
        retry_budget=5.0,
        clock=clock.time,
        sleep=clock.sleep,
    )
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryAfter(2)
        return "ok"

    assert await limiter.call("chat", operation, retryable=True) == "ok"
    assert attempts == 2
    assert clock.now == 2
    assert limiter.diagnostics["retried"] == 1


@pytest.mark.asyncio
async def test_limiter_retries_timedelta_retry_after():
    clock = FakeClock()
    limiter = TelegramDeliveryLimiter(
        global_interval=0.0,
        chat_interval=0.0,
        max_retries=1,
        retry_budget=5.0,
        clock=clock.time,
        sleep=clock.sleep,
    )
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryAfter(timedelta(seconds=2))
        return "ok"

    assert await limiter.call("chat", operation, retryable=True) == "ok"
    assert attempts == 2
    assert clock.now == 2


@pytest.mark.asyncio
async def test_limiter_does_not_retry_ambiguous_send():
    clock = FakeClock()
    limiter = TelegramDeliveryLimiter(
        global_interval=0.0,
        chat_interval=0.0,
        clock=clock.time,
        sleep=clock.sleep,
    )
    operation = 0

    async def send() -> None:
        nonlocal operation
        operation += 1
        raise RetryAfter(1)

    with pytest.raises(RetryAfter):
        await limiter.call("chat", send, retryable=False)
    assert operation == 1
    assert clock.now == 0


@pytest.mark.asyncio
async def test_limiter_wait_is_cancellation_aware():
    started = asyncio.Event()
    release = asyncio.Event()

    async def sleep(_: float) -> None:
        started.set()
        await release.wait()

    limiter = TelegramDeliveryLimiter(
        global_interval=1.0,
        chat_interval=0.0,
        sleep=sleep,
    )
    await limiter.call("chat", _noop, retryable=False)
    task = asyncio.create_task(limiter.call("chat", _noop, retryable=False))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.gather(task)


@pytest.mark.asyncio
async def test_limited_client_routes_media_groups_through_limiter():
    clock = FakeClock()
    limiter = TelegramDeliveryLimiter(
        global_interval=0.0,
        chat_interval=0.0,
        clock=clock.time,
        sleep=clock.sleep,
    )
    client = type("FakeTelegramClient", (), {})()
    client.send_media_group = AsyncMock(return_value=["sent"])
    limited_client = LimitedTelegramClient(client, limiter)

    result = await limited_client.send_media_group(
        chat_id="chat",
        media=["media-1", "media-2"],
    )

    assert result == ["sent"]
    client.send_media_group.assert_awaited_once_with(
        chat_id="chat",
        media=["media-1", "media-2"],
    )
    assert limiter.diagnostics["sent"] == 1


async def _noop() -> None:
    return None
