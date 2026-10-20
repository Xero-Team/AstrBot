from typing import TYPE_CHECKING

from astrbot.core.conversation_mgr import (
    DIALOGUE_LOOP_SCOPE,
    WORK_LOOP_SCOPE,
    load_sanitized_history,
)
from astrbot.core.conversation_models import Conversation
from astrbot.core.platform.astr_message_event import AstrMessageEvent

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext


_LOOP_HANDOFF_TURNS = 4


async def _get_session_conv(
    event: AstrMessageEvent,
    plugin_context: CoreExecutionContext,
    scope: str = DIALOGUE_LOOP_SCOPE,
) -> Conversation:
    """Resolve the conversation a loop owns, creating it on first use.

    Args:
        event: The message event being processed.
        plugin_context: Runtime services providing the conversation manager.
        scope: The owning loop. The dialogue loop uses its session's current
            conversation; the work loop owns a separate conversation so the
            two loops never write one history.

    Returns:
        The conversation this loop reads and writes.

    Raises:
        RuntimeError: The conversation could not be created.
    """
    conv_mgr = plugin_context.conversation_manager
    umo = event.unified_msg_origin
    cid = await conv_mgr.get_curr_conversation_id(umo, scope)
    if not cid:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id(), scope=scope)
    conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id(), scope=scope)
        conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        raise RuntimeError("无法创建新的对话。")
    return conversation


async def _prepare_loop_contexts(
    event: AstrMessageEvent,
    plugin_context: CoreExecutionContext,
    conversation: Conversation,
    *,
    is_work_run: bool,
    dual_loop_enabled: bool,
) -> list[dict]:
    """Return the provider contexts for one loop's run.

    The two loops keep separate histories.  A work run starts from none: the
    conversation loop hands it the task through the work tool, so its stored
    history never feeds back into later work.  A conversation run keeps its
    own history and additionally receives the work loop's recent complete
    turns as provider-only context, so the chat can refer to what the work
    loop produced.  Handed over turns carry ``_no_save`` and are never written
    into either history; they are reduced to their text roles, because tool
    calls would otherwise arrive without the results their provider requires.

    Args:
        event: The message event being processed.
        plugin_context: Runtime services providing the conversation manager.
        conversation: The conversation this loop owns.
        is_work_run: Whether this run belongs to the BTW work loop.
        dual_loop_enabled: Whether this profile enables BTW and its work loop.

    Returns:
        Provider contexts, oldest first.
    """
    if is_work_run:
        return []
    contexts = load_sanitized_history(conversation.history)
    if not dual_loop_enabled:
        return contexts
    conv_mgr = plugin_context.conversation_manager
    work_cid = await conv_mgr.get_curr_conversation_id(
        event.unified_msg_origin, WORK_LOOP_SCOPE
    )
    if not work_cid:
        return contexts
    work_conversation = await conv_mgr.get_conversation(
        event.unified_msg_origin, work_cid
    )
    if work_conversation is None:
        return contexts
    return contexts + _provider_only_turns(
        load_sanitized_history(work_conversation.history)
    )


def _provider_only_turns(history: list[dict]) -> list[dict]:
    """Return the trailing complete turns of ``history``, marked provider-only."""
    turns = [
        {"role": message["role"], "content": message["content"], "_no_save": True}
        for message in history
        if message.get("role") in {"user", "assistant"} and message.get("content")
    ]
    if turns and turns[-1]["role"] == "user":
        # Hand over whole turns so the block never ends on an unanswered request.
        turns.pop()
    return turns[-2 * _LOOP_HANDOFF_TURNS :]
