"""Provider-facing projection of consumed tool results."""

from copy import deepcopy
from typing import Any

DEFAULT_TOOL_HISTORY_PLACEHOLDER = "[stale tool result omitted, re-invoke tool if needed]"


def compact_consumed_tool_history(
    messages: list[dict[str, Any]],
    placeholder: str = DEFAULT_TOOL_HISTORY_PLACEHOLDER,
) -> list[dict[str, Any]]:
    """Replace tool-result bodies only for transactions known to be consumed."""
    projected = deepcopy(messages)
    index = 0
    while index < len(projected):
        assistant = projected[index]
        tool_calls = (
            assistant.get("tool_calls") if isinstance(assistant, dict) else None
        )
        if (
            not isinstance(assistant, dict)
            or assistant.get("role") != "assistant"
            or not isinstance(tool_calls, list)
            or not tool_calls
            or assistant.get("provider_state") is not None
        ):
            index += 1
            continue

        expected_ids = {
            call.get("id")
            for call in tool_calls
            if isinstance(call, dict) and isinstance(call.get("id"), str)
        }
        if not expected_ids:
            index += 1
            continue

        tools_start = index + 1
        tools_end = tools_start
        while (
            tools_end < len(projected)
            and isinstance(projected[tools_end], dict)
            and projected[tools_end].get("role") == "tool"
        ):
            tools_end += 1
        tools = projected[tools_start:tools_end]
        result_ids = {
            message.get("tool_call_id")
            for message in tools
            if isinstance(message, dict)
        }
        next_message = projected[tools_end] if tools_end < len(projected) else None
        followed_by_assistant = (
            isinstance(next_message, dict)
            and next_message.get("role") == "assistant"
            and (
                bool(next_message.get("content"))
                or bool(next_message.get("tool_calls"))
            )
        )
        if (
            expected_ids.issubset(result_ids)
            and followed_by_assistant
            and not any(message.get("provider_state") is not None for message in tools)
        ):
            for tool in tools:
                tool["content"] = placeholder
        index = max(tools_end, index + 1)
    return projected
