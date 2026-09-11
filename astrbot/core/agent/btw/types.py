"""Types shared by the BTW conversation and work loops."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


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


def mark_work_run_failed(event) -> None:
    """Record that a run failed, for work runs only.

    Chat runs keep their own error path, so the marker is written only when the
    event belongs to the work loop.

    Args:
        event: The event whose run ended in an error.
    """
    if event.get_extra("btw_loop") == "work":
        event.set_extra(WORK_FAILED_EXTRA, True)


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
