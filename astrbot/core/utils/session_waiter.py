"""Runtime-owned waiting for the next message in an interactive session."""

from __future__ import annotations

import abc
import asyncio
import copy
import time
from collections.abc import Awaitable, Callable
from typing import Any

import astrbot.core.message.components as Comp
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.task_utils import cancel_tracked_tasks, create_tracked_task


class SessionController:
    """Control the lifetime and optional history of one message wait."""

    def __init__(self, background_tasks: set[asyncio.Task]) -> None:
        self._background_tasks = background_tasks
        self.future: asyncio.Future[None] = asyncio.Future()
        self.current_event: asyncio.Event | None = None
        self.ts: float | None = None
        self.timeout: float | int | None = None
        self.history_chains: list[list[Comp.BaseMessageComponent]] = []

    def stop(self, error: Exception | None = None) -> None:
        """Finish the wait, optionally with an error."""
        if self.future.done():
            return
        if error is not None:
            self.future.set_exception(error)
        else:
            self.future.set_result(None)

    def keep(self, timeout: float = 0, *, reset_timeout: bool = False) -> None:
        """Keep the wait active for a fresh or extended timeout."""
        now = time.time()
        if reset_timeout:
            if timeout <= 0:
                self.stop()
                return
        else:
            assert self.timeout is not None
            assert self.ts is not None
            timeout = self.timeout - (now - self.ts) + timeout
            if timeout <= 0:
                self.stop()
                return

        if self.current_event is not None and not self.current_event.is_set():
            self.current_event.set()
        self.current_event = asyncio.Event()
        self.ts = now
        self.timeout = timeout
        create_tracked_task(
            self._background_tasks,
            self._holding(self.current_event, timeout),
            name="session_wait_timeout",
        )

    async def _holding(self, event: asyncio.Event, timeout_seconds: float) -> None:
        try:
            await asyncio.wait_for(event.wait(), timeout_seconds)
        except TimeoutError:
            self.stop(TimeoutError("等待超时"))

    def get_history_chains(self) -> list[list[Comp.BaseMessageComponent]]:
        """Return copied incoming message chains recorded for this wait."""
        return self.history_chains


class SessionFilter:
    """Define the session identity used for an interactive wait."""

    @abc.abstractmethod
    def filter(self, event: AstrMessageEvent) -> str:
        """Return an identity for the supplied event."""


class DefaultSessionFilter(SessionFilter):
    """Use the unified message origin as the wait identity."""

    def filter(self, event: AstrMessageEvent) -> str:
        return event.unified_msg_origin


class _SessionWaiter:
    """One registered wait, private to a SessionWaiterRegistry instance."""

    def __init__(
        self,
        registry: SessionWaiterRegistry,
        session_filter: SessionFilter,
        session_id: str,
        record_history_chains: bool,
    ) -> None:
        self.registry = registry
        self.session_id = session_id
        self.session_filter = session_filter
        self.handler: (
            Callable[[SessionController, AstrMessageEvent], Awaitable[Any]] | None
        ) = None
        self.session_controller = SessionController(registry._background_tasks)
        self.record_history_chains = record_history_chains
        self._lock = asyncio.Lock()

    async def wait(
        self,
        handler: Callable[[SessionController, AstrMessageEvent], Awaitable[Any]],
        timeout_seconds: int,
    ) -> None:
        self.handler = handler
        self.registry._sessions[self.session_id] = self
        self.registry._filters.append(self.session_filter)
        self.session_controller.keep(timeout_seconds, reset_timeout=True)
        try:
            await self.session_controller.future
        finally:
            self.cleanup()

    def cleanup(self, error: Exception | None = None) -> None:
        if self.registry._sessions.get(self.session_id) is self:
            self.registry._sessions.pop(self.session_id, None)
        try:
            self.registry._filters.remove(self.session_filter)
        except ValueError:
            # Value is already absent or invalid; ignore.
            pass
        self.session_controller.stop(error)


class SessionWaiterRegistry:
    """Own interactive wait state for one explicitly constructed runtime."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionWaiter] = {}
        self._filters: list[SessionFilter] = []
        self._background_tasks: set[asyncio.Task] = set()

    async def wait_for(
        self,
        event: AstrMessageEvent,
        handler: Callable[[SessionController, AstrMessageEvent], Awaitable[Any]],
        *,
        timeout_seconds: int = 30,
        record_history_chains: bool = False,
        session_filter: SessionFilter | None = None,
    ) -> None:
        """Wait for a later event matching the supplied session filter."""
        filter_ = session_filter or DefaultSessionFilter()
        session_id = filter_.filter(event)
        waiter = _SessionWaiter(
            self,
            filter_,
            session_id,
            record_history_chains,
        )
        await waiter.wait(handler, timeout_seconds)

    async def dispatch(self, event: AstrMessageEvent) -> bool:
        """Deliver an event to all matching waits and report whether any matched."""
        handled = False
        for session_filter in tuple(self._filters):
            session_id = session_filter.filter(event)
            waiter = self._sessions.get(session_id)
            if waiter is None or waiter.session_controller.future.done():
                continue
            handled = True
            async with waiter._lock:
                if waiter.session_controller.future.done():
                    continue
                if waiter.record_history_chains:
                    waiter.session_controller.history_chains.append(
                        [copy.deepcopy(component) for component in event.get_messages()]
                    )
                try:
                    assert waiter.handler is not None
                    await waiter.handler(waiter.session_controller, event)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    waiter.session_controller.stop(exc)
        return handled

    async def terminate(self) -> None:
        """Stop all pending waits and cancel their timeout tasks."""
        for waiter in tuple(self._sessions.values()):
            waiter.cleanup()
        self._sessions.clear()
        self._filters.clear()
        await cancel_tracked_tasks(self._background_tasks)
