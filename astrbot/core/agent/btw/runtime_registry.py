"""Expose each pipeline's work-loop state to commands and built-in tools.

The pipeline's ``ConversationLoop`` registers its work-session manager and its
work loop under the owning profile's ``config_id`` at initialization.  The
built-in ``work`` command group reads the newest session through here, and the
work-submission tool hands a task to the work loop through the same registry.
"""

from typing import TYPE_CHECKING

from .types import WorkDelegation, WorkSession, WorkSessionStatus, WorkStatusSnapshot
from .work_sessions import WorkSessionManager

if TYPE_CHECKING:
    from .work_loop import WorkLoop

_managers: dict[str, WorkSessionManager] = {}
_work_loops: dict[str, WorkLoop] = {}


def register(config_id: str, manager: WorkSessionManager) -> None:
    """Bind a successfully initialized pipeline's work-session manager."""
    _managers[config_id] = manager


def unregister(config_id: str, manager: WorkSessionManager) -> None:
    """Remove only the closing pipeline's registration."""
    if _managers.get(config_id) is manager:
        _managers.pop(config_id)


def register_work_loop(config_id: str, work_loop: WorkLoop) -> None:
    """Bind a successfully initialized pipeline's work loop for task hand-off."""
    _work_loops[config_id] = work_loop


def unregister_work_loop(config_id: str, work_loop: WorkLoop) -> None:
    """Remove only the closing pipeline's work-loop registration."""
    if _work_loops.get(config_id) is work_loop:
        _work_loops.pop(config_id)


def work_loop_for(config_id: str) -> WorkLoop | None:
    """Return the profile's registered work loop, if any.

    Args:
        config_id: The configuration profile that owns the pipeline.

    Returns:
        The profile's work loop, or ``None`` when the profile has no pipeline
        with an enabled work loop.
    """
    return _work_loops.get(config_id)


def config_id_of(event) -> str:
    """Return the configuration profile that owns an event.

    Args:
        event: Any event carrying the auth resource of its profile.

    Returns:
        The profile's id, or an empty string when the event has none.
    """
    config_id = getattr(getattr(event, "resource", None), "config_id", "")
    return config_id if isinstance(config_id, str) else ""


async def cancel_pending_work(event) -> bool:
    """Cancel work whose submission never reached its background run.

    A work submission acknowledges the request before the work loop registers
    the background run, and the generator that owns the queued session is
    abandoned when the event stops in between.  The scheduler calls this as an
    event finishes, so the queue entry cannot outlive its request.

    Args:
        event: The event that may still be waiting for a background hand-off.

    Returns:
        Whether a queued work session was cancelled.
    """
    if event.get_extra("btw_detached_work"):
        return False
    session_id = event.get_extra("btw_work_session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    manager = _managers.get(config_id_of(event))
    if manager is None:
        return False
    return await manager.cancel_if_pending(session_id)


async def record_work_artifacts(event, paths: list[str]) -> bool:
    """Attach the paths a delegated run produced to the event's work session.

    The tool that delegates a task is the only owner that knows what the coding
    agent produced, and the manager that holds the session lives here, so the
    tool records through this function rather than reaching for a session.

    Args:
        event: The work event the delegation ran under.
        paths: Root-relative artifact paths the delegated run reported.

    Returns:
        Whether a work session was found and the paths were recorded.
    """
    session_id = event.get_extra("btw_work_session_id")
    if not paths or not isinstance(session_id, str) or not session_id:
        return False
    manager = _managers.get(config_id_of(event))
    if manager is None:
        return False
    return await manager.record_artifacts(session_id, paths)


async def latest_session(config_id: str, origin: str) -> WorkSession | None:
    """Return the newest retained session for one profile and origin."""
    manager = _managers.get(config_id)
    if manager is None:
        return None
    return await manager.get_for_origin(origin)


async def latest_status(
    config_id: str, origin: str
) -> tuple[str, WorkSessionStatus] | None:
    """Read the newest work task within the specified profile and origin.

    Args:
        config_id: The profile that owns the admitted command event.
        origin: The event's unified message origin.

    Returns:
        The task text and status, or ``None`` when no retained task exists.
    """
    session = await latest_session(config_id, origin)
    if session is None:
        return None
    return session.request, session.status


async def latest_status_snapshot(
    config_id: str, origin: str
) -> WorkStatusSnapshot | None:
    """Return the task, lifecycle status, and latest delegation progress."""
    session = await latest_session(config_id, origin)
    if session is None:
        return None
    delegation = session.delegations[-1] if session.delegations else None
    return WorkStatusSnapshot(
        request=session.request,
        status=session.status,
        delegation=delegation,
    )


async def list_work_sessions() -> list[tuple[str, WorkSession]]:
    """Return a stable snapshot of every registered profile's sessions.

    The Dashboard reads this without taking ownership of a pipeline's manager.
    Each manager applies its own expiry cleanup and lock; this function copies
    the registry first so a concurrent profile reload cannot change the
    dictionary while it is being iterated.
    """
    sessions: list[tuple[str, WorkSession]] = []
    for config_id, manager in list(_managers.items()):
        sessions.extend(
            (config_id, session) for session in await manager.list_sessions()
        )
    sessions.sort(key=lambda item: item[1].created_at, reverse=True)
    return sessions


async def start_work_delegation(event, delegation: WorkDelegation) -> bool:
    """Attach one coding-agent delegation to the event's work session."""
    session_id = event.get_extra("btw_work_session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    manager = _managers.get(config_id_of(event))
    if manager is None:
        return False
    return await manager.start_delegation(session_id, delegation)


async def record_work_delegation_event(event, run_id: str, item) -> bool:
    """Record one normalized coding event on the event's work session."""
    session_id = event.get_extra("btw_work_session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    manager = _managers.get(config_id_of(event))
    if manager is None:
        return False
    return await manager.record_delegation_event(
        session_id,
        run_id,
        event_type=item.type,
        summary=item.summary,
        tool=item.tool,
        call_id=item.call_id,
        status=item.status,
        usage=item.usage,
    )


async def finish_work_delegation(
    event,
    run_id: str,
    *,
    status: str,
    exit_code: int | None,
    artifacts: list[str],
    detail: str = "",
    latest_action: str = "",
    usage: dict[str, int | float] | None = None,
) -> bool:
    """Mark one coding-agent delegation terminal on the event's session."""
    session_id = event.get_extra("btw_work_session_id")
    if not isinstance(session_id, str) or not session_id:
        return False
    manager = _managers.get(config_id_of(event))
    if manager is None:
        return False
    return await manager.finish_delegation(
        session_id,
        run_id,
        status=status,
        exit_code=exit_code,
        artifacts=artifacts,
        detail=detail,
        latest_action=latest_action,
        usage=usage,
    )
