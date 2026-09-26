from typing import Any

from astrbot.core.provider.headers import build_conversation_headers


def extra_headers_kwargs(
    headers: dict[str, str] | None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Build SDK ``extra_headers`` kwargs, layering in the conversation ID.

    Args:
        headers: Provider-specific request headers, if any.
        conversation_id: AstrBot conversation ID to associate with the request.

    Returns:
        A mapping with an ``extra_headers`` key, or an empty mapping when there
        are no headers to send.
    """
    merged = dict(headers or {})
    merged.update(build_conversation_headers(conversation_id))
    return {"extra_headers": merged} if merged else {}
