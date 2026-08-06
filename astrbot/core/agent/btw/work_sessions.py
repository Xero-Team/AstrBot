"""In-memory runtime ownership for BTW work sessions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from .types import WorkSession, WorkSessionStatus


class WorkSessionManager:
    """Own active and recent work-loop session state for one pipeline."""

    def __init__(self, *, max_age_seconds: int = 3600) -> None:
        self._by_origin: dict[str, WorkSession] = {}
        self._by_id: dict[str, WorkSession] = {}
        self._lock = asyncio.Lock()
        self.set_max_age_seconds(max_age_seconds)

    def set_max_age_seconds(self, value: int) -> None:
        """Set the retention period for terminal sessions.

        Args:
            value: Number of seconds to keep a completed, failed, or cancelled
                session before a later manager operation removes it.
        """
        self._max_age_seconds = max(1, value) if type(value) is int else 3600

    async def create(self, origin: str, request: str) -> WorkSession:
        """Create and register a work session.

        Args:
            origin: The unified message origin that owns the work.
            request: The user request being processed.

        Returns:
            The newly created work session.
        """
        session = WorkSession(origin=origin, request=request)
        async with self._lock:
            self._cleanup_expired_locked()
            self._by_origin[origin] = session
            self._by_id[session.id] = session
        return session

    async def get_for_origin(self, origin: str) -> WorkSession | None:
        """Return the most recent work session for an origin."""
        async with self._lock:
            self._cleanup_expired_locked()
            return self._by_origin.get(origin)

    async def get_by_id(self, session_id: str) -> WorkSession | None:
        """Return a recent work session by its identifier.

        Args:
            session_id: The generated work-session identifier.

        Returns:
            The matching session, or ``None`` after it has expired.
        """
        async with self._lock:
            self._cleanup_expired_locked()
            return self._by_id.get(session_id)

    async def update_status(
        self,
        session_id: str,
        status: WorkSessionStatus,
        *,
        error: str | None = None,
    ) -> WorkSession | None:
        """Transition one known work session.

        Args:
            session_id: The work-session identifier.
            status: The new lifecycle status.
            error: A safe failure message, when applicable.

        Returns:
            The updated session, or ``None`` when it has expired.
        """
        async with self._lock:
            self._cleanup_expired_locked()
            session = self._by_id.get(session_id)
            if session is not None:
                session.update_status(status, error=error)
            return session

    def _cleanup_expired_locked(self) -> None:
        """Remove old terminal sessions while the manager lock is held."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._max_age_seconds)
        expired_ids = [
            session_id
            for session_id, session in self._by_id.items()
            if session.status
            not in {WorkSessionStatus.PENDING, WorkSessionStatus.RUNNING}
            and session.updated_at < cutoff
        ]
        for session_id in expired_ids:
            session = self._by_id.pop(session_id)
            if self._by_origin.get(session.origin) is session:
                self._by_origin.pop(session.origin, None)
