"""Expose each pipeline's most recent work status to built-in commands."""

from .types import WorkSessionStatus
from .work_sessions import WorkSessionManager

_managers: dict[str, WorkSessionManager] = {}


def register(config_id: str, manager: WorkSessionManager) -> None:
    """Bind a successfully initialized pipeline's work-session manager."""
    _managers[config_id] = manager


def unregister(config_id: str, manager: WorkSessionManager) -> None:
    """Remove only the closing pipeline's registration."""
    if _managers.get(config_id) is manager:
        _managers.pop(config_id)


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
