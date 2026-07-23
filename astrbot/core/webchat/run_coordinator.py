"""Runtime-owned coordination for request-scoped WebChat runs.

This module deliberately owns only transport-neutral run lifetime.  Each
Dashboard transport remains responsible for its wire encoding and durable
history representation, while sharing one authoritative request/session index
and queue lifecycle.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .queue_manager import WebChatQueueManager


class DuplicateWebChatRunError(RuntimeError):
    """Raised when a request identifier is already active in this runtime."""


@dataclass(slots=True)
class WebChatRun:
    """One request-scoped WebChat run owned by a coordinator.

    The coordinator keeps this object strongly reachable until cleanup so a
    request task, its back queue, and its session index always move together.
    """

    request_id: str
    session_id: str
    username: str
    back_queue: asyncio.Queue[Any]
    kind: str = "request"
    task: asyncio.Task[None] | None = None
    status: str = "running"
    started: bool = False
    completion_seen: bool = False
    interrupt_requested: asyncio.Event = field(default_factory=asyncio.Event)
    follow_up_capture: dict[str, Any] | None = None
    agent_stats: list[dict[str, Any]] = field(default_factory=list)


class WebChatRunCoordinator:
    """Coordinate WebChat request queues, tasks, and session ownership.

    It does not format SSE or WebSocket messages and does not persist history.
    Those are transport concerns.  It does guarantee that every generated
    request has a back queue before dispatch, that concurrent request IDs are
    isolated, and that queue/task cleanup is idempotent.
    """

    def __init__(self, queue_manager: WebChatQueueManager) -> None:
        self._queue_manager = queue_manager
        self._runs: dict[str, WebChatRun] = {}
        self._run_ids_by_session: dict[str, dict[str, None]] = {}

    @property
    def queue_manager(self) -> WebChatQueueManager:
        """Return the runtime-owned queue manager used by this coordinator."""
        return self._queue_manager

    def create_run(
        self,
        *,
        session_id: str,
        username: str,
        request_id: str | None = None,
        kind: str = "request",
    ) -> WebChatRun:
        """Create and index a run before input can reach the platform adapter.

        Args:
            session_id: WebChat conversation or session identifier.
            username: Request owner passed to the adapter.
            request_id: Optional transport-provided request identifier.
            kind: Human-readable request category used for diagnostics.

        Returns:
            The newly active request-scoped run.

        Raises:
            DuplicateWebChatRunError: If the identifier is already active.
        """
        resolved_request_id = str(request_id or uuid4())
        if resolved_request_id in self._runs:
            raise DuplicateWebChatRunError(resolved_request_id)

        back_queue = self._queue_manager.get_or_create_back_queue(
            resolved_request_id,
            session_id,
        )
        run = WebChatRun(
            request_id=resolved_request_id,
            session_id=session_id,
            username=username,
            back_queue=back_queue,
            kind=kind,
        )
        self._runs[resolved_request_id] = run
        self._run_ids_by_session.setdefault(session_id, {})[resolved_request_id] = None
        return run

    async def dispatch(self, run: WebChatRun, payload: dict[str, Any]) -> None:
        """Dispatch one run's input after its response queue is registered.

        Args:
            run: Active request to dispatch.
            payload: Adapter payload excluding (or agreeing with) ``message_id``.

        Raises:
            RuntimeError: If the run was already closed.
        """
        self._require_active(run)
        queued_payload = dict(payload)
        queued_payload["message_id"] = run.request_id
        input_queue = self._queue_manager.get_or_create_queue(run.session_id)
        await input_queue.put((run.username, run.session_id, queued_payload))

    def start_task(
        self,
        run: WebChatRun,
        worker: Awaitable[None],
        *,
        name: str,
    ) -> asyncio.Task[None]:
        """Start a request task and bind its cleanup to the run lifecycle.

        Args:
            run: Active run to supervise.
            worker: Transport-specific consumer coroutine.
            name: Task name used for diagnostics.

        Returns:
            The strong-referenced worker task.

        Raises:
            RuntimeError: If the run already has a task or is closed.
        """
        self._require_active(run)
        if run.task is not None:
            raise RuntimeError(f"WebChat run {run.request_id} already has a task")

        worker_started = False

        async def supervise() -> None:
            nonlocal worker_started
            worker_started = True
            try:
                await worker
            finally:
                await self.close_run(run)

        supervise_coroutine = supervise()
        try:
            task = asyncio.create_task(supervise_coroutine, name=name)
        except BaseException:
            supervise_coroutine.close()
            if inspect.iscoroutine(worker):
                worker.close()
            raise
        task.add_done_callback(
            lambda _task: (
                worker.close()
                if not worker_started and inspect.iscoroutine(worker)
                else None
            )
        )
        run.task = task
        return task

    def bind_task(
        self,
        run: WebChatRun,
        task: asyncio.Task[None] | None = None,
    ) -> asyncio.Task[None]:
        """Bind a caller-created task to a run owned by this coordinator.

        WebSocket transports may need to create a task before enough parsed
        input exists to open its run.  This keeps that task in the same
        request-scoped owner without introducing a second registry.
        """
        self._require_active(run)
        resolved_task = task or asyncio.current_task()
        if resolved_task is None:
            raise RuntimeError("WebChat run tasks require an active event loop task")
        if run.task is not None and run.task is not resolved_task:
            raise RuntimeError(f"WebChat run {run.request_id} already has a task")
        run.task = resolved_task
        return resolved_task

    @asynccontextmanager
    async def open_run(
        self,
        *,
        session_id: str,
        username: str,
        request_id: str | None = None,
        kind: str = "request",
    ):
        """Open a run for a caller-owned asynchronous request lifecycle."""
        run = self.create_run(
            session_id=session_id,
            username=username,
            request_id=request_id,
            kind=kind,
        )
        try:
            yield run
        finally:
            await self.close_run(run)

    async def next_result(
        self,
        run: WebChatRun,
        *,
        wait_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        """Receive the next result belonging to one request.

        Results incorrectly addressed to another request are ignored without
        affecting that other run.  ``None`` is returned for a timeout or an
        empty/non-dict queue item.
        """
        self._require_active(run)
        try:
            if wait_seconds is None:
                item = await run.back_queue.get()
            else:
                item = await asyncio.wait_for(
                    run.back_queue.get(), timeout=wait_seconds
                )
        except TimeoutError:
            return None

        if not isinstance(item, dict):
            return None
        message_id = item.get("message_id")
        if message_id is not None and str(message_id) != run.request_id:
            return None
        self.observe_result(run, item)
        return item

    def observe_result(self, run: WebChatRun, result: dict[str, Any]) -> None:
        """Record transport-neutral protocol state without changing payloads."""
        self._require_active(run)
        result_type = result.get("type")
        chain_type = result.get("chain_type")

        if result_type == "run_started":
            run.started = True
        elif result_type == "follow_up_captured":
            data = result.get("data")
            run.follow_up_capture = data if isinstance(data, dict) else None

        if result_type == "agent_stats" or chain_type == "agent_stats":
            try:
                parsed = json.loads(result.get("data", ""))
            except TypeError, json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                run.agent_stats.append(parsed)

        if result_type == "complete":
            run.completion_seen = True
        elif result_type == "end":
            run.completion_seen = True
            run.status = "completed"
        elif result_type == "error":
            run.status = "failed"

    def request_interrupt(self, request_id: str) -> bool:
        """Mark one active request as interrupted without a session-wide lock."""
        run = self._runs.get(request_id)
        if run is None:
            return False
        run.interrupt_requested.set()
        if run.status == "running":
            run.status = "interrupt_requested"
        return True

    def request_session_interrupt(self, session_id: str) -> set[str]:
        """Mark all active runs for one session as interrupted."""
        request_ids = set(self._run_ids_by_session.get(session_id, {}))
        return {
            request_id
            for request_id in request_ids
            if self.request_interrupt(request_id)
        }

    def get_run(self, request_id: str) -> WebChatRun | None:
        """Return one active run, if present."""
        return self._runs.get(request_id)

    def get_session_runs(self, session_id: str) -> list[WebChatRun]:
        """Return active runs for one session in insertion order."""
        return [
            self._runs[request_id]
            for request_id in self._run_ids_by_session.get(session_id, {})
            if request_id in self._runs
        ]

    async def close_run(self, run: WebChatRun) -> None:
        """Remove one run's queue and indexes exactly once."""
        if self._runs.get(run.request_id) is not run:
            return

        self._runs.pop(run.request_id, None)
        run_ids = self._run_ids_by_session.get(run.session_id)
        if run_ids is not None:
            run_ids.pop(run.request_id, None)
            if not run_ids:
                self._run_ids_by_session.pop(run.session_id, None)
        self._queue_manager.remove_back_queue(run.request_id)

    async def close_session(
        self,
        session_id: str,
        *,
        cancel_tasks: bool = True,
        remove_input_queue: bool = False,
    ) -> None:
        """Close session-owned runs and optionally remove its input queue.

        Args:
            session_id: Session whose run state should be removed.
            cancel_tasks: Whether unfinished transport workers are cancelled.
            remove_input_queue: Whether the adapter input queue/listener is also
                removed.  Use this only when the conversation itself is deleted.
        """
        runs = self.get_session_runs(session_id)
        tasks = [
            run.task
            for run in runs
            if cancel_tasks
            and run.task is not None
            and not run.task.done()
            and run.task is not asyncio.current_task()
        ]
        for run in runs:
            self.request_interrupt(run.request_id)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for run in runs:
            await self.close_run(run)
        if remove_input_queue:
            self._queue_manager.remove_queues(session_id)

    async def terminate(self) -> None:
        """Stop every active WebChat run during runtime shutdown."""
        for session_id in list(self._run_ids_by_session):
            await self.close_session(
                session_id,
                cancel_tasks=True,
                remove_input_queue=True,
            )

    def _require_active(self, run: WebChatRun) -> None:
        if self._runs.get(run.request_id) is not run:
            raise RuntimeError(f"WebChat run {run.request_id} is not active")
