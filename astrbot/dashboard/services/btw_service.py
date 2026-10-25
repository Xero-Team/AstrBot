"""Read the runtime's BTW work sessions for the Dashboard."""

from typing import Any

from astrbot.core.agent.btw import runtime_registry
from astrbot.core.agent.btw.types import WorkSession
from astrbot.core.utils.error_redaction import redact_sensitive_text

MAX_REQUEST_CHARS = 2000
MAX_ORIGIN_CHARS = 500
MAX_ERROR_CHARS = 1000


def _safe_text(value: str, limit: int) -> str:
    return redact_sensitive_text(value)[:limit]


def _session_payload(config_id: str, session: WorkSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "config_id": config_id,
        "origin": _safe_text(session.origin, MAX_ORIGIN_CHARS),
        "request": _safe_text(session.request, MAX_REQUEST_CHARS),
        "task_type": session.task_type.value,
        "status": session.status.value,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "error": _safe_text(session.error, MAX_ERROR_CHARS) if session.error else None,
        "artifacts": list(session.artifacts),
        "delegations": [delegation.as_dict() for delegation in session.delegations],
    }


class BtwService:
    """Expose work-session progress without owning a pipeline's manager."""

    async def list_work_sessions(
        self,
        *,
        config_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return retained work sessions, optionally scoped to one profile."""
        sessions = await runtime_registry.list_work_sessions()
        if config_id is not None:
            sessions = [
                (session_config_id, session)
                for session_config_id, session in sessions
                if session_config_id == config_id
            ]
        return [
            _session_payload(session_config_id, session)
            for session_config_id, session in sessions
        ]
