"""The BTW work-loop prototype backed by the existing Agent tool loop."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from typing import Protocol

from astrbot import logger
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.task_utils import create_tracked_task

from . import i18n as work_i18n
from .types import (
    THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY,
    WORK_FAILED_EXTRA,
    WorkSession,
    WorkSessionStatus,
)
from .work_sessions import WorkSessionManager


class AgentRequestExecutor(Protocol):
    """The existing Agent request path required by the work loop."""

    def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Yield pipeline progress markers for one event.

        Protocol stub; concrete implementations are the pipeline's Agent
        request sub-stage.  The body raises so the statement is effectful
        (CodeQL py/ineffectual-statement); the unreachable ``yield`` keeps
        the declared ``AsyncGenerator`` return type type-checkable.
        """
        raise NotImplementedError
        yield  # noqa: B901 -- unreachable marker for the type checker


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
        self._tasks: dict[asyncio.Task, tuple[AstrMessageEvent, str]] = {}
        self._closed = False

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
        session = await self.sessions.create(
            event.unified_msg_origin, event.message_str
        )
        self._prepare_event(event, session.id)
        async for progress in self._execute(event, session.id):
            yield progress

    async def submit(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Acknowledge work, then run it without retaining the request pipeline.

        Falls back to inline execution when no runtime task registry is
        attached, which keeps the primitive usable in isolated tests.
        """
        if self._closed:
            event.set_result(
                MessageEventResult().message(
                    work_i18n.text(
                        work_i18n.resolve_event_locale(event),
                        "btw.work.status.cancelled",
                    )
                )
            )
            yield
            return
        if (
            self._background_tasks is None
            or self._result_dispatcher is None
            or self._event_finalizer is None
        ):
            async for progress in self.process(event):
                yield progress
            return

        session = await self.sessions.create(
            event.unified_msg_origin, event.message_str
        )
        self._prepare_event(event, session.id)
        event.set_result(
            MessageEventResult().message(
                work_i18n.text(
                    work_i18n.resolve_event_locale(event), "btw.work.started"
                )
            )
        )
        yield

        if self._closed:
            await self.sessions.update_status(session.id, WorkSessionStatus.CANCELLED)
            return

        # The first yield returns only after the normal response stages deliver
        # the acknowledgement.  Marking it here prevents the scheduler from
        # releasing event-owned temporary files before the worker needs them.
        # Losing this race to a concurrent close() only skips the work.
        self._schedule_detached(event, session.id)

    async def schedule(self, event: AstrMessageEvent) -> WorkSession:
        """Run one work task detached, without delivering its result here.

        This is how the work loop acts as a tool for the conversation loop: the
        caller has already put the complete task in ``event.message_str``, the
        work run executes in the background, and its result is delivered
        through the normal response stages when it finishes.

        Args:
            event: The prepared work event carrying the task to run.

        Returns:
            The created work session.

        Raises:
            RuntimeError: The loop is closed or has no runtime services
                attached, so it cannot run work in the background.
        """
        if not self._detached_ready():
            raise RuntimeError("Work loop cannot run detached work")
        session = await self.sessions.create(
            event.unified_msg_origin, event.message_str
        )
        self._prepare_event(event, session.id)
        if not self._schedule_detached(event, session.id):
            await self.sessions.update_status(session.id, WorkSessionStatus.CANCELLED)
            raise RuntimeError("Work loop cannot run detached work")
        return session

    def _detached_ready(self) -> bool:
        """Return whether this loop owns the services detached work needs."""
        return (
            not self._closed
            and self._background_tasks is not None
            and self._result_dispatcher is not None
            and self._event_finalizer is not None
        )

    def _schedule_detached(self, event: AstrMessageEvent, session_id: str) -> bool:
        """Hand one prepared work event to the runtime's background registry.

        Returns:
            Whether the work run was registered; ``False`` when the loop has no
            services to run it, which happens only while shutting down.
        """
        if not self._detached_ready():
            return False
        assert self._background_tasks is not None
        event.set_extra("btw_detached_work", True)
        task = create_tracked_task(
            self._background_tasks,
            self._run_detached(event, session_id),
            name=f"btw_work:{session_id}",
        )
        self._tasks[task] = (event, session_id)
        task.add_done_callback(lambda done: self._tasks.pop(done, None))
        return True

    async def close(self) -> None:
        """Cancel and finalize this profile's work, including unstarted tasks."""
        self._closed = True
        tasks = dict(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        finalizers = []
        if self._event_finalizer is not None:
            for event, session_id in tasks.values():
                if not event.get_extra("btw_detached_work_finished"):
                    await self.sessions.update_status(
                        session_id, WorkSessionStatus.CANCELLED
                    )
                    finalizers.append(self._event_finalizer(event))
        if finalizers:
            results = await asyncio.gather(*finalizers, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result

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
        produced = False
        try:
            async with self._semaphore:
                await self.sessions.update_status(
                    session_id,
                    WorkSessionStatus.RUNNING,
                )
                async for progress in self.executor.process(event):
                    produced = True
                    yield progress
        except asyncio.CancelledError:
            await self.sessions.update_status(
                session_id,
                WorkSessionStatus.CANCELLED,
            )
            raise
        except Exception:
            await self.sessions.update_status(
                session_id,
                WorkSessionStatus.FAILED,
                error="Work task failed.",
            )
            raise
        else:
            failed = bool(event.get_extra(WORK_FAILED_EXTRA)) or bool(
                event.get_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY)
            )
            # An admitted stop request and a run that reported its own abort are
            # both cancellations.  ``run_agent`` clears ``agent_stop_requested``
            # when it reports the abort, so the stop flag alone misses that case.
            cancelled = bool(event.get_extra("agent_stop_requested")) or bool(
                event.get_extra("agent_user_aborted")
            )
            # An executor that produced nothing never reached an Agent: a run
            # the session turned away is the reported case.  The generator
            # ending only proves the task ran when something actually ran.
            failed = failed or (not produced and not cancelled)
            await self.sessions.update_status(
                session_id,
                WorkSessionStatus.FAILED
                if failed
                else (
                    WorkSessionStatus.CANCELLED
                    if cancelled
                    else WorkSessionStatus.COMPLETED
                ),
                error="Work task failed." if failed else None,
            )

    async def _run_detached(self, event: AstrMessageEvent, session_id: str) -> None:
        """Run work in the runtime task registry and deliver each result."""
        assert self._result_dispatcher is not None
        assert self._event_finalizer is not None
        try:
            async with aclosing(self._execute(event, session_id)) as execution:
                async for _ in execution:
                    await self._result_dispatcher(event)
        except asyncio.CancelledError:
            await self.sessions.update_status(session_id, WorkSessionStatus.CANCELLED)
            raise
        except Exception as exc:
            await self.sessions.update_status(
                session_id, WorkSessionStatus.FAILED, error="Work task failed."
            )
            # The task registry logs unhandled exceptions with their traceback.
            # Consume executor failures here so provider details never reach it.
            logger.error("BTW work task failed: %s", safe_error("", exc))
        finally:
            await self._event_finalizer(event)
