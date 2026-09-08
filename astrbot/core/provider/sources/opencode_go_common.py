import hashlib
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Any, cast

from astrbot.core.config.default import VERSION

OPENCODE_GO_API_BASE = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_AUX_SESSION = "astrbot-aux"
OPENCODE_GO_USER_AGENT = f"AstrBot/{VERSION}"
OPENCODE_GO_SESSION_HEADER = "x-opencode-session"

_opencode_go_session_id: ContextVar[str | None] = ContextVar(
    "opencode_go_session_id",
    default=None,
)


def opencode_go_session_value(session_id: str | None) -> str:
    if session_id is None or not str(session_id).strip():
        return OPENCODE_GO_AUX_SESSION
    digest = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:32]
    return f"astrbot-{digest}"


def apply_default_user_agent(provider_config: dict, user_agent: str) -> dict:
    merged = dict(provider_config)
    custom_headers = merged.get("custom_headers")
    headers = dict(custom_headers) if isinstance(custom_headers, dict) else {}
    if not str(headers.get("User-Agent", "")).strip():
        headers["User-Agent"] = user_agent
    merged["custom_headers"] = headers
    return merged


def _session_id_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    if "session_id" in kwargs:
        return kwargs["session_id"]
    if len(args) >= 2:
        return args[1]
    return None


class OpenCodeGoSessionMixin:
    def _request_extra_headers(self) -> dict[str, str] | None:
        return {
            OPENCODE_GO_SESSION_HEADER: opencode_go_session_value(
                _opencode_go_session_id.get()
            )
        }

    async def text_chat(self, *args: Any, **kwargs: Any) -> Any:
        token = _opencode_go_session_id.set(_session_id_from_call(args, kwargs))
        try:
            return await cast(Any, super()).text_chat(*args, **kwargs)
        finally:
            _opencode_go_session_id.reset(token)

    async def text_chat_stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        token = _opencode_go_session_id.set(_session_id_from_call(args, kwargs))
        try:
            async for item in cast(Any, super()).text_chat_stream(*args, **kwargs):
                yield item
        finally:
            _opencode_go_session_id.reset(token)
