from collections.abc import Mapping
from typing import Any

PROMPT_CUSTOM_ERROR_MESSAGE_EXTRA_KEY = "prompt_custom_error_message"
DEFAULT_AGENT_ERROR_MESSAGE = "Error occurred during AI execution."


def normalize_prompt_custom_error_message(value: object) -> str | None:
    """Normalize prompt custom error reply text."""
    if not isinstance(value, str):
        return None
    message = value.strip()
    return message or None


def extract_prompt_custom_error_message_from_prompt(
    prompt: Mapping[str, Any] | None,
) -> str | None:
    """Extract normalized custom error reply text from prompt mapping."""
    if prompt is None:
        return None
    return normalize_prompt_custom_error_message(prompt.get("custom_error_message"))


def extract_prompt_custom_error_message_from_event(event: Any) -> str | None:
    """Extract normalized custom error reply text from event extras."""
    try:
        if event is None or not hasattr(event, "get_extra"):
            return None
        raw_message = event.get_extra(PROMPT_CUSTOM_ERROR_MESSAGE_EXTRA_KEY)
        return normalize_prompt_custom_error_message(raw_message)
    except Exception:
        return None


def get_agent_error_message(event: Any) -> str:
    """Return a prompt override or the stable user-safe fallback."""
    return (
        extract_prompt_custom_error_message_from_event(event)
        or DEFAULT_AGENT_ERROR_MESSAGE
    )


def set_prompt_custom_error_message_on_event(event: Any, message: object) -> str | None:
    """Normalize and store prompt custom error reply text into event extras."""
    normalized = normalize_prompt_custom_error_message(message)
    try:
        if event is not None and hasattr(event, "set_extra"):
            event.set_extra(PROMPT_CUSTOM_ERROR_MESSAGE_EXTRA_KEY, normalized)
    except Exception:
        pass
    return normalized


async def resolve_prompt_custom_error_message(
    *,
    event: Any,
    prompt_manager: Any,
    conversation_prompt_id: str | None = None,
) -> str | None:
    """Resolve normalized custom error reply text for the selected prompt."""
    (
        _prompt_id,
        prompt,
        _force_applied_prompt_id,
        _use_webchat_special_default,
    ) = await prompt_manager.resolve_selected_prompt(
        umo=event.unified_msg_origin,
        conversation_prompt_id=conversation_prompt_id,
        platform_name=event.get_platform_name(),
    )
    return extract_prompt_custom_error_message_from_prompt(prompt)


async def resolve_event_conversation_prompt_id(
    event: Any, conversation_manager: Any
) -> str | None:
    """Resolve current conversation prompt_id from event and conversation manager."""
    curr_cid = await conversation_manager.get_curr_conversation_id(
        event.unified_msg_origin
    )
    if not curr_cid:
        return None
    conversation = await conversation_manager.get_conversation(
        event.unified_msg_origin, curr_cid
    )
    if not conversation:
        return None
    return conversation.prompt_id
