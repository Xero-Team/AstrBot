"""Bounded, cancellation-aware pacing for Telegram Bot API delivery."""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import partial
from typing import Any

from telegram.error import RetryAfter

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

COALESCED = object()


class TelegramDeliveryLimiter:
    """Coordinate Telegram delivery across all events owned by one bot.

    Slots are reserved before a request starts, so concurrent chats share the
    bot budget while each chat also receives its own minimum interval. Only
    idempotent operations are retried after ``RetryAfter``; sends and uploads
    remain single attempt because a timeout can leave an ambiguous message.
    """

    def __init__(
        self,
        *,
        global_interval: float = 0.04,
        chat_interval: float = 0.6,
        max_retries: int = 2,
        retry_budget: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.global_interval = max(0.0, float(global_interval))
        self.chat_interval = max(0.0, float(chat_interval))
        self.max_retries = max(0, int(max_retries))
        self.retry_budget = max(0.0, float(retry_budget))
        self._clock = clock
        self._sleep = sleep
        self._state_lock = asyncio.Lock()
        self._next_global = 0.0
        self._next_chat: dict[str, float] = {}
        self._generations: dict[str, int] = {}
        self._stats: Counter[str] = Counter()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> TelegramDeliveryLimiter:
        """Build a limiter from Telegram adapter settings."""

        def number(name: str, default: float, minimum: float = 0.0) -> float:
            raw = config.get(name, default)
            if isinstance(raw, bool):
                return default
            try:
                value = float(raw)
            except TypeError, ValueError:
                return default
            if not math.isfinite(value) or value < minimum:
                return default
            return value

        def integer(name: str, default: int) -> int:
            raw = config.get(name, default)
            if isinstance(raw, bool):
                return default
            try:
                return max(0, int(raw))
            except TypeError, ValueError:
                return default

        return cls(
            global_interval=number("telegram_delivery_global_interval", 0.04),
            chat_interval=number("telegram_delivery_chat_interval", 0.6),
            max_retries=integer("telegram_delivery_max_retries", 2),
            retry_budget=number("telegram_delivery_retry_budget", 10.0),
        )

    @property
    def diagnostics(self) -> dict[str, int]:
        """Return aggregate counters without request contents."""

        return dict(self._stats)

    def supersede(self, key: str) -> None:
        """Mark queued work for *key* stale so it will not consume a slot."""

        self._generations[key] = self._generations.get(key, 0) + 1

    async def _reserve(self, chat_id: str) -> None:
        async with self._state_lock:
            now = self._clock()
            scheduled = max(now, self._next_global, self._next_chat.get(chat_id, 0.0))
            self._next_global = scheduled + self.global_interval
            self._next_chat[chat_id] = scheduled + self.chat_interval
            wait_for = scheduled - now
        if wait_for > 0:
            await self._sleep(wait_for)

    async def call(
        self,
        chat_id: str,
        operation: Callable[[], Any],
        *,
        retryable: bool,
        coalesce_key: str | None = None,
    ) -> Any:
        """Run one Bot API call under pacing and bounded RetryAfter recovery."""

        key_generation = (
            self._generations.get(coalesce_key, 0) if coalesce_key is not None else None
        )
        started = self._clock()
        retries = 0
        while True:
            if (
                coalesce_key is not None
                and self._generations.get(coalesce_key, 0) != key_generation
            ):
                self._stats["coalesced"] += 1
                return COALESCED
            await self._reserve(str(chat_id))
            if (
                coalesce_key is not None
                and self._generations.get(coalesce_key, 0) != key_generation
            ):
                self._stats["coalesced"] += 1
                return COALESCED
            try:
                result = operation()
                if inspect.isawaitable(result):
                    result = await result
                self._stats["sent"] += 1
                return result
            except asyncio.CancelledError:
                self._stats["cancelled"] += 1
                raise
            except RetryAfter as error:
                self._stats["retry_after"] += 1
                if not retryable or retries >= self.max_retries:
                    self._stats["retry_exhausted"] += 1
                    raise
                elapsed = self._clock() - started
                remaining = self.retry_budget - elapsed
                raw_delay = error.retry_after
                if isinstance(raw_delay, timedelta):
                    delay = max(0.0, raw_delay.total_seconds())
                else:
                    delay = max(0.0, float(raw_delay))
                if remaining <= 0 or not math.isfinite(delay) or delay > remaining:
                    self._stats["retry_exhausted"] += 1
                    raise
                retries += 1
                self._stats["retried"] += 1
                logger.warning(
                    "[Telegram] delivery rate limited; waiting %.2fs before retry (%s/%s)",
                    delay,
                    retries,
                    self.max_retries,
                )
                await self._sleep(delay)
            except Exception as error:
                self._stats["failed"] += 1
                logger.debug(
                    "[Telegram] delivery call failed: %s", safe_error("", error)
                )
                raise


class LimitedTelegramClient:
    """Proxy selected Bot API methods through a shared delivery limiter."""

    _METHODS = {
        "send_message",
        "send_message_draft",
        "edit_message_text",
        "send_chat_action",
        "send_photo",
        "send_animation",
        "send_document",
        "send_voice",
        "send_video",
        "set_message_reaction",
    }
    _RETRYABLE = {
        "send_message_draft",
        "edit_message_text",
        "send_chat_action",
        "set_message_reaction",
    }

    def __init__(self, client: Any, limiter: TelegramDeliveryLimiter) -> None:
        self._client = client
        self._limiter = limiter

    def __getattr__(self, name: str) -> Any:
        method = getattr(self._client, name)
        if name not in self._METHODS or not callable(method):
            return method

        async def limited(*args: Any, **kwargs: Any) -> Any:
            chat_id = kwargs.get("chat_id")
            if chat_id is None and args:
                chat_id = args[0]
            chat_key = str(chat_id if chat_id is not None else "unknown")
            coalesce_key = None
            if name == "send_message_draft":
                coalesce_key = f"draft:{chat_key}:{kwargs.get('draft_id', '')}"
            elif name == "edit_message_text":
                coalesce_key = f"edit:{chat_key}:{kwargs.get('message_id', '')}"
            elif name == "send_chat_action":
                coalesce_key = f"action:{chat_key}:{kwargs.get('action', '')}"
            if coalesce_key is not None:
                self._limiter.supersede(coalesce_key)
            return await self._limiter.call(
                chat_key,
                partial(method, *args, **kwargs),
                retryable=name in self._RETRYABLE,
                coalesce_key=coalesce_key,
            )

        return limited
