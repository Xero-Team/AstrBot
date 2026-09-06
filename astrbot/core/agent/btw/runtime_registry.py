"""Per-profile registry exposing BTW work-session state to commands.

The built-in ``work`` command group queries the newest work session for an
origin without owning the pipeline.  The pipeline's ``ConversationLoop``
registers its work-session manager under the owning profile's ``config_id``
at initialization; the command group resolves the event's config and reads
through this registry.
"""

import asyncio

from astrbot.core.agent.btw.types import WorkSessionStatus
from astrbot.core.agent.btw.work_sessions import WorkSessionManager

_lock = asyncio.Lock()
_managers: dict[str, WorkSessionManager] = {}


def register(config_id: str, manager: WorkSessionManager) -> None:
    """Bind one profile's work-session manager for command queries.

    Args:
        config_id: The configuration profile that owns the pipeline.
        manager: The profile's work-session manager.
    """
    _managers[config_id] = manager


def unregister(config_id: str) -> None:
    """Drop one profile's registration (pipeline shutdown)."""
    _managers.pop(config_id, None)


def manager_for(config_id: str) -> WorkSessionManager | None:
    """Return the profile's registered work-session manager."""
    return _managers.get(config_id)


async def latest_status(
    config_id: str, origin: str
) -> tuple[str, WorkSessionStatus] | None:
    """Return the newest work session ``(request, status)`` for an origin.

    Args:
        config_id: The configuration profile to query.
        origin: The unified message origin.

    Returns:
        The newest session's request text and status, or ``None`` when the
        profile has no live work sessions for the origin.
    """
    async with _lock:
        manager = _managers.get(config_id)
    if manager is None:
        return None
    session = await manager.get_for_origin(origin)
    if session is None:
        return None
    return (session.request, session.status)
