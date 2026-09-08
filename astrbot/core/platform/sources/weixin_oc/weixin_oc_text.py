"""Plain-text chunking and tool-progress parsing for Weixin OC."""

from __future__ import annotations

from typing import Any

TEXT_CHUNK_LIMIT = 4000
STREAM_MIN_CHARS = 200
STREAM_IDLE_S = 3.0
TOOL_CALL_START_TYPE = 11
TOOL_CALL_RESULT_TYPE = 12
_CUT_MARKS = "。！？.!?；;\n"


def split_plain_text(plain: str, max_length: int = TEXT_CHUNK_LIMIT) -> list[str]:
    """Split outbound text into chunks at most ``max_length`` characters.

    Prefers punctuation or newline near the limit, matching the official
    OpenClaw ``textChunkLimit`` of 4000.
    """
    if max_length <= 0:
        return [plain] if plain else []
    if len(plain) <= max_length:
        return [plain] if plain else []
    chunks: list[str] = []
    start = 0
    while start < len(plain):
        if start + max_length >= len(plain):
            chunks.append(plain[start:])
            break
        end = start + max_length
        cut = end
        for index in range(end, start, -1):
            if plain[index - 1] in _CUT_MARKS:
                cut = index
                break
        chunks.append(plain[start:cut])
        start = cut
    return [chunk for chunk in chunks if chunk]


def parse_tool_progress(text: str) -> dict[str, Any]:
    """Parse a ``tool_call`` status line into a Weixin progress payload.

    Args:
        text: Status text produced by the agent runner.

    Returns:
        Mapping with ``phase`` (``start`` or ``end``), ``tool_name``, and
        ``status`` for result items.
    """
    normalized = text.strip()
    is_result = "返回结果" in normalized
    tool_name = "tool"
    marker = "调用工具:"
    if marker in normalized:
        rest = normalized.split(marker, 1)[1]
        tool_name = rest.split("\n", 1)[0].strip() or "tool"
    if is_result:
        status = "failed" if "失败" in normalized else "completed"
        return {"phase": "end", "tool_name": tool_name, "status": status}
    return {"phase": "start", "tool_name": tool_name, "status": "unknown"}
