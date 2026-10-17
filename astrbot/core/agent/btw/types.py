"""Types shared by the BTW conversation and work loops."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from astrbot.core.utils.error_redaction import redact_sensitive_text


def is_work_loop_enabled(config: object) -> bool:
    """Return whether the profile explicitly enables BTW and work."""
    if not isinstance(config, Mapping):
        return False
    btw = config.get("btw", {})
    if not isinstance(btw, Mapping) or not btw.get("enabled", False):
        return False
    work = btw.get("work_loop", {})
    return isinstance(work, Mapping) and bool(work.get("enabled", False))


# How a run tells the work loop that it did not succeed.  The writers are the
# agent stages and the Agent runner; the work loop is the only reader.  They
# live here so a writer and its reader cannot drift apart: a run that fails
# without setting one of these is reported as completed.
WORK_FAILED_EXTRA = "btw_work_failed"
THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY = "_third_party_runner_error"
# Set once the completion report has been folded into a run's final result, so
# a result delivered more than once carries the report exactly once.
WORK_REPORT_EXTRA = "btw_work_report_composed"


def mark_work_run_failed(event) -> None:
    """Record that a run failed, for work runs only.

    Chat runs keep their own error path, so the marker is written only when the
    event belongs to the work loop.

    Args:
        event: The event whose run ended in an error.
    """
    if event.get_extra("btw_loop") == "work":
        event.set_extra(WORK_FAILED_EXTRA, True)


def stop_requested(event) -> bool:
    """Return whether an event's run was asked to stop.

    Three signals mean the same thing, and no one of them covers every path:
    ``/task stop`` sets the event's own flag for a third-party runner and the
    agent stop request for a local one, and ``run_agent`` *clears* the stop
    request when it reports a user abort.  A reader that looks at only one of
    them reports a stopped run as completed.  They live here so every reader
    -- the work loop's status and the third-party stream -- cannot drift apart.

    Args:
        event: The event whose run may have been stopped.

    Returns:
        Whether the run was stopped by any of the three signals.
    """
    return (
        event.is_stopped()
        or bool(event.get_extra("agent_stop_requested"))
        or bool(event.get_extra("agent_user_aborted"))
    )


def resolve_run_status(event, *, produced: bool) -> WorkSessionStatus:
    """Return the status one work run ends in.

    Two owners need this answer: the work loop, which records it, and the
    conversation loop, which reports it before the record exists.  Reading the
    same markers through one function keeps a reported status and a recorded
    one from disagreeing.

    Args:
        event: The finished work event.
        produced: Whether the executor emitted anything at all.  A run that
            emitted nothing never reached an Agent, so it did not complete.

    Returns:
        The status the run ends in.
    """
    failed = bool(event.get_extra(WORK_FAILED_EXTRA)) or bool(
        event.get_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY)
    )
    cancelled = stop_requested(event)
    if failed or (not produced and not cancelled):
        return WorkSessionStatus.FAILED
    return WorkSessionStatus.CANCELLED if cancelled else WorkSessionStatus.COMPLETED


class TaskType(StrEnum):
    """The execution loop selected for a user request."""

    CONVERSATION = "conversation"
    WORK = "work"


class WorkSessionStatus(StrEnum):
    """Lifecycle states for one work-loop request."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # The run produced a result, but the platform's acceptance of it is unknown,
    # so neither the result nor its absence can be reported.  Kept apart from
    # ``FAILED``: an unknown outcome does not prove the user missed nothing.
    UNCONFIRMED = "unconfirmed"


@dataclass(slots=True)
class WorkDelegation:
    """Live progress for one coding-agent delegation inside a work session."""

    run_id: str
    agent_id: str
    agent_name: str
    agent_type: str
    workspace: str
    status: str = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    latest_action: str = "starting"
    event_count: int = 0
    tool_call_count: int = 0
    exit_code: int | None = None
    detail: str = ""
    usage: dict[str, int | float] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    tool_call_ids: set[str] = field(default_factory=set, repr=False)

    def record_event(
        self,
        *,
        event_type: str,
        summary: str,
        tool: str = "",
        call_id: str = "",
        status: str = "",
        usage: dict[str, int | float] | None = None,
    ) -> None:
        """Fold one normalized event into the live progress record."""
        now = datetime.now(UTC)
        self.event_count += 1
        if event_type in {"tool_call", "tool_result"}:
            if call_id:
                if call_id not in self.tool_call_ids:
                    self.tool_call_ids.add(call_id)
                    self.tool_call_count += 1
            elif event_type == "tool_call":
                self.tool_call_count += 1
        if usage:
            self.usage.update(usage)
        safe_summary = redact_sensitive_text(summary)[:500]
        if safe_summary:
            self.latest_action = safe_summary
        self.recent_events.append(
            {
                "type": event_type,
                "timestamp": now.isoformat(),
                "summary": safe_summary,
                "tool": redact_sensitive_text(tool)[:120],
                "status": status,
            }
        )
        del self.recent_events[:-50]
        self.updated_at = now

    def finish(
        self,
        *,
        status: str,
        exit_code: int | None,
        artifacts: list[str],
        detail: str = "",
        latest_action: str = "",
        usage: dict[str, int | float] | None = None,
    ) -> None:
        """Mark the delegation terminal and attach its final result."""
        self.status = status
        self.exit_code = exit_code
        self.artifacts = list(artifacts)
        self.detail = redact_sensitive_text(detail)[:1000]
        if latest_action:
            self.latest_action = redact_sensitive_text(latest_action)[:500]
        if usage:
            self.usage.update(usage)
        self.finished_at = datetime.now(UTC)
        self.updated_at = self.finished_at

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("tool_call_ids", None)
        for key in ("started_at", "updated_at", "finished_at"):
            value = payload.get(key)
            payload[key] = value.isoformat() if value is not None else None
        for key in ("agent_id", "agent_name", "agent_type", "workspace", "detail"):
            payload[key] = redact_sensitive_text(str(payload.get(key, "")))
        return payload


@dataclass(slots=True)
class WorkStatusSnapshot:
    """The status command's view of one work session and its delegation."""

    request: str
    status: WorkSessionStatus
    delegation: WorkDelegation | None = None


@dataclass(slots=True)
class WorkSession:
    """Runtime state shared by the conversation and work loops."""

    origin: str
    request: str
    task_type: TaskType = TaskType.WORK
    id: str = field(default_factory=lambda: uuid4().hex)
    status: WorkSessionStatus = WorkSessionStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    # What the run produced outside the Agent's own answer: the task folders a
    # delegated coding agent worked in and the paths it reported changing.
    artifacts: list[str] = field(default_factory=list)
    delegations: list[WorkDelegation] = field(default_factory=list)

    def update_status(
        self,
        status: WorkSessionStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Record a status transition.

        Args:
            status: The new work-session status.
            error: A safe diagnostic for failed work, when available.
        """
        self.status = status
        self.error = error
        self.updated_at = datetime.now(UTC)
