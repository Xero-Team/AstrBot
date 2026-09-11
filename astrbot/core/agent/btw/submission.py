"""Submit an explicit task from the conversation loop to the work loop.

The work loop is a tool for the conversation loop: the conversation loop's
model authors the complete task, hands it over here, and keeps answering the
user while the work runs detached in its own conversation.  Because the task
is explicit, the work run needs no history of its own and never reads the
chat's.
"""

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.error_redaction import safe_error

from . import runtime_registry
from .types import WorkSession

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext


def config_id_of(event: AstrMessageEvent) -> str:
    """Return the configuration profile that owns an event.

    Args:
        event: Any event carrying the auth resource of its profile.

    Returns:
        The profile's id, or an empty string when the event has none.
    """
    config_id = getattr(getattr(event, "resource", None), "config_id", "")
    return config_id if isinstance(config_id, str) else ""


async def submit_work_task(
    execution_context: CoreExecutionContext,
    event: AstrMessageEvent,
    prompt: str,
) -> WorkSession | None:
    """Hand one explicit task to the event's profile work loop and return.

    Args:
        execution_context: The runtime the work loop delivers results through.
        event: The conversation-loop event requesting the work.
        prompt: The complete, self-contained task for the work loop.

    Returns:
        The created work session, or ``None`` when the task was empty or this
        profile has no work loop that can run detached work.
    """
    task = prompt.strip()
    if not task:
        return None
    work_loop = runtime_registry.work_loop_for(config_id_of(event))
    if work_loop is None:
        return None
    work_event = work_event_for(execution_context, event, task)
    # The work run is a run of this session: registering it keeps it reachable
    # for stop and reset, and the work loop's finalizer unregisters it.
    registry = getattr(execution_context, "active_event_registry", None)
    if registry is not None:
        registry.register(work_event)
    try:
        return await work_loop.schedule(work_event)
    except Exception as exc:  # noqa: BLE001
        if registry is not None:
            registry.unregister(work_event)
        logger.error("Failed to submit a work task: %s", safe_error("", exc))
        return None


def work_event_for(
    execution_context: CoreExecutionContext,
    event: AstrMessageEvent,
    task: str,
) -> AstrMessageEvent:
    """Build the detached work event that carries one explicit task.

    The synthetic event mirrors the requesting event's identity so the work
    run keeps the same subject, instance role, and auth resource, but it is a
    new run: it carries a fresh request id and no consumed WebChat step-up
    proof, and it stays a separate event so the conversation run's own
    provider request, results, and delivery receipt are untouched.

    Args:
        execution_context: The runtime the work loop delivers results through.
        event: The conversation-loop event requesting the work.
        task: The complete task text for the work loop.

    Returns:
        An event the work loop can run detached and deliver results for.
    """
    from astrbot.core.cron.events import CronMessageEvent

    session = MessageSession.from_str(event.unified_msg_origin)
    work_event = CronMessageEvent(
        context=execution_context,
        session=session,
        message=task,
        extras={"btw_loop": "work"},
        message_type=session.message_type,
    )
    work_event.platform_member_role = getattr(event, "platform_member_role", "unknown")
    work_event.platform_role_source = getattr(event, "platform_role_source", "none")
    work_event.platform_role_expires_at = getattr(
        event, "platform_role_expires_at", None
    )
    work_event.subject = getattr(event, "subject", None)
    work_event.resource = getattr(event, "resource", None)
    auth_context = getattr(event, "auth_context", None)
    if auth_context is not None:
        # A background work run is a new event.  Do not carry a consumed
        # WebChat proof (or its raw token) into it; otherwise the per-run
        # cache would outlive the original AuthContext object.
        metadata = {
            key: value
            for key, value in auth_context.metadata.items()
            if key not in {"webchat_step_up_tokens", "_webchat_step_up_consumed"}
        }
        work_event.auth_context = replace(
            auth_context,
            request_id=str(uuid4()),
            step_up_token=None,
            metadata=metadata,
        )
    return work_event
