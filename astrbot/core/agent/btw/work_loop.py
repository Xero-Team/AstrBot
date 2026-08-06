"""The BTW work-loop prototype backed by the existing Agent tool loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Protocol

from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.task_utils import create_tracked_task

from .types import WorkSessionStatus
from .work_sessions import WorkSessionManager


class AgentRequestExecutor(Protocol):
    """The existing Agent request path required by the work loop."""

    def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]: ...


ResultDispatcher = Callable[[AstrMessageEvent], Awaitable[None]]
EventFinalizer = Callable[[AstrMessageEvent], Awaitable[None]]


class WorkLoop:
    """Run classified work with the current Agent and tool infrastructure."""

    def __init__(
        self,
        executor: AgentRequestExecutor,
        sessions: WorkSessionManager,
        *,
        max_concurrent: int = 2,
    ) -> None:
        self.executor = executor
        self.sessions = sessions
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))
        self._background_tasks: set[asyncio.Task] | None = None
        self._result_dispatcher: ResultDispatcher | None = None
        self._event_finalizer: EventFinalizer | None = None

    def configure_detached_execution(
        self,
        *,
        background_tasks: set[asyncio.Task],
        result_dispatcher: ResultDispatcher,
        event_finalizer: EventFinalizer,
    ) -> None:
        """Attach runtime-owned background execution services.

        Args:
            background_tasks: Runtime task registry cancelled during shutdown.
            result_dispatcher: Delivers a generated work result through the
                configured result-decorate and response stages.
            event_finalizer: Releases the event after detached work finishes.
        """
        self._background_tasks = background_tasks
        self._result_dispatcher = result_dispatcher
        self._event_finalizer = event_finalizer

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Execute one work-loop request inline.

        Args:
            event: The classified message event.

        Yields:
            Pipeline progress markers emitted by the existing Agent executor.
        """
        session = await self.sessions.create(event.unified_msg_origin, event.message_str)
        self._prepare_event(event, session.id)
        async for progress in self._execute(event, session.id):
            yield progress

    async def submit(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Acknowledge work, then run it without retaining the request pipeline.

        Falls back to inline execution when no runtime task registry is
        attached, which keeps the primitive usable in isolated tests.
        """
        if (
            self._background_tasks is None
            or self._result_dispatcher is None
            or self._event_finalizer is None
        ):
            async for progress in self.process(event):
                yield progress
            return

        session = await self.sessions.create(event.unified_msg_origin, event.message_str)
        self._prepare_event(event, session.id)
        event.set_result(MessageEventResult().message("🔧 工作任务已开始处理。"))
        yield

        # The first yield returns only after the normal response stages deliver
        # the acknowledgement.  Marking it here prevents the scheduler from
        # releasing event-owned temporary files before the worker needs them.
        event.set_extra("btw_detached_work", True)
        create_tracked_task(
            self._background_tasks,
            self._run_detached(event, session.id),
            name=f"btw_work:{session.id}",
        )

    @staticmethod
    def _prepare_event(event: AstrMessageEvent, session_id: str) -> None:
        """Mark an event so Agent assembly uses the work-loop policy."""
        event.set_extra("btw_work_session_id", session_id)
        event.set_extra("btw_loop", "work")
        event.set_extra("btw_agent_lock_key", f"{event.unified_msg_origin}:work")

    async def _execute(
        self,
        event: AstrMessageEvent,
        session_id: str,
    ) -> AsyncGenerator[None]:
        """Run one already-created work session and update its lifecycle."""
        try:
            async with self._semaphore:
                await self.sessions.update_status(
                    session_id,
                    WorkSessionStatus.RUNNING,
                )
                async for progress in self.executor.process(event):
                    yield progress
        except asyncio.CancelledError:
            await self.sessions.update_status(
                session_id,
                WorkSessionStatus.CANCELLED,
            )
            raise
        except Exception as exc:
            await self.sessions.update_status(
                session_id,
                WorkSessionStatus.FAILED,
                error=safe_error("", exc),
            )
            raise
        else:
            await self.sessions.update_status(
                session_id,
                WorkSessionStatus.COMPLETED,
            )

    async def _run_detached(self, event: AstrMessageEvent, session_id: str) -> None:
        """Run work in the runtime task registry and deliver each result."""
        assert self._result_dispatcher is not None
        assert self._event_finalizer is not None
        try:
            async for _ in self._execute(event, session_id):
                await self._result_dispatcher(event)
        finally:
            await self._event_finalizer(event)
