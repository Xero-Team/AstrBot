"""Expose each pipeline's work-loop state to commands and built-in tools.

The pipeline's ``ConversationLoop`` registers its work-session manager and its
work loop under the owning profile's ``config_id`` at initialization.  The
built-in ``work`` command group reads the newest session through here, and the
work-submission tool hands a task to the work loop through the same registry.
"""

from typing import TYPE_CHECKING

from .types import WorkSessionStatus
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
    manager = _managers.get(config_id)
    if manager is None:
        return None
    session = await manager.get_for_origin(origin)
    if session is None:
        return None
    return session.request, session.status
