"""Compose the completion report a finished work task ends with.

The work loop hands its result to the conversation loop, and the conversation
loop is what the user actually hears from.  This module is the one place that
decides what that report says, so the status a report shows and the status the
work loop records come from the same reading of the same run.
"""

from collections.abc import Sequence

from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)

from . import i18n as work_i18n
from .types import (
    WORK_REPORT_EXTRA,
    WorkSession,
    WorkSessionStatus,
    resolve_run_status,
)


def report_text(
    locale: str,
    status: WorkSessionStatus,
    artifacts: Sequence[str],
) -> str:
    """Return the report line for one finished task.

    Args:
        locale: The locale the report is written in.
        status: The status the run ended in.
        artifacts: The paths the run produced, when it produced any.

    Returns:
        The status line, followed by the artifact paths when there are any.
    """
    lines = [work_i18n.text(locale, f"btw.work.report.{status}")]
    if artifacts:
        lines.append(work_i18n.text(locale, "btw.work.report.artifacts"))
        lines.extend(f"- {path}" for path in artifacts)
    return "\n".join(lines)


def compose_work_report(
    event,
    session: WorkSession | None,
    locale: str,
) -> bool:
    """Append this run's completion report to its final result.

    A streamed result is left alone: its chunks are already on their way out.
    A result delivered more than once carries the report exactly once.

    Args:
        event: The work event whose result is about to be delivered.
        session: The work session the run belongs to, while it is still known.
        locale: The locale the report is written in.

    Returns:
        Whether the report was added to the event's result.
    """
    if event.get_extra(WORK_REPORT_EXTRA):
        return False
    result = event.get_result()
    if result is None:
        return False
    if result.result_content_type is ResultContentType.STREAMING_RESULT:
        return False
    # The run is still marked running here: the work loop records the terminal
    # status after its last delivery.  Reading the run's own markers answers
    # the same question the record will answer a moment later.
    status = resolve_run_status(event, produced=True)
    artifacts = list(session.artifacts) if session is not None else []
    marker = MessageChain().message(f"\n\n{report_text(locale, status, artifacts)}")
    event.set_extra(WORK_REPORT_EXTRA, True)
    event.set_result(
        MessageEventResult(
            chain=[*(result.chain or []), *(marker.chain or [])],
            result_content_type=result.result_content_type,
        )
    )
    return True
