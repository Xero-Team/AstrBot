"""Runtime-owned Telegram interaction facade for Star plugins."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.contracts.telegram import (
    TELEGRAM_CAPABILITIES,
    TELEGRAM_CAPABILITY_NAME,
    TelegramButton,
    TelegramCallbackEvent,
    TelegramDeliveryReceipt,
)


def _callback_payload(event: AstrMessageEvent) -> TelegramCallbackEvent | None:
    value = event.get_extra("telegram_callback")
    return value if isinstance(value, TelegramCallbackEvent) else None


class TelegramMessages:
    __slots__ = ("_client",)

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    async def send_interactive(
        self,
        *,
        text: str,
        buttons: Sequence[Sequence[TelegramButton | Mapping[str, Any]]],
        allowed_user_ids: Sequence[str | int] | None = None,
        allowed_roles: Sequence[str] | None = None,
        ttl_seconds: float | None = None,
    ) -> TelegramDeliveryReceipt:
        """Send an inline keyboard through the event's immutable Telegram route."""
        if allowed_user_ids is None and self._client.actor_id:
            allowed_user_ids = (self._client.actor_id,)
        return await self._client._invoke(
            "send_interactive",
            text=text,
            buttons=buttons,
            allowed_user_ids=allowed_user_ids,
            allowed_roles=allowed_roles,
            ttl_seconds=ttl_seconds,
        )


class TelegramCallbacks:
    __slots__ = ("_client",)

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    async def answer(self, text: str | None = None) -> bool:
        """Update the callback acknowledgement without touching Telegram internals."""
        callback = _callback_payload(self._client.event)
        if callback is None:
            raise ValueError("The current event is not a Telegram callback")
        return await self._client._invoke(
            "answer_callback",
            callback_id=callback.callback_id,
            text=text,
        )


class TelegramClient:
    """An event-bound Telegram capability client."""

    __slots__ = (
        "_execution",
        "_platform_id",
        "event",
        "messages",
        "callbacks",
        "target",
        "actor_id",
    )

    def __init__(
        self,
        execution: Any,
        platform_id: str,
        event: AstrMessageEvent,
    ) -> None:
        self._execution = execution
        self._platform_id = platform_id
        self.event = event
        self.target = event.route_identity.target_id
        self.actor_id = str(event.get_sender_id() or "")
        self.messages = TelegramMessages(self)
        self.callbacks = TelegramCallbacks(self)

    async def _invoke(self, action: str, **kwargs: Any) -> Any:
        if action == "send_interactive":
            kwargs.setdefault("target", self.target)
        return await self._execution.invoke_platform_capability(
            self._platform_id,
            TELEGRAM_CAPABILITY_NAME,
            action,
            **kwargs,
        )


class TelegramCapability:
    """Expose Telegram-only interaction contracts for Telegram events."""

    __slots__ = ("_execution",)

    def __init__(self, execution: Any) -> None:
        self._execution = execution

    def event(self, event: AstrMessageEvent) -> TelegramCallbackEvent | None:
        return _callback_payload(event)

    def for_event(self, event: AstrMessageEvent) -> TelegramClient | None:
        if event.get_platform_name() != "telegram":
            return None
        return TelegramClient(self._execution, event.get_platform_id(), event)

    def supports(
        self,
        event: AstrMessageEvent,
        capability: str = TELEGRAM_CAPABILITY_NAME,
        action: str | None = None,
    ) -> bool:
        if event.get_platform_name() != "telegram":
            return False
        descriptor = next(
            (item for item in TELEGRAM_CAPABILITIES if item.name == capability),
            None,
        )
        if descriptor is None or (
            action is not None and descriptor.action(action) is None
        ):
            return False
        get_capabilities = getattr(self._execution, "get_platform_capabilities", None)
        if callable(get_capabilities):
            try:
                declared = get_capabilities(event.get_platform_id())
            except Exception:
                return False
            if not isinstance(declared, (tuple, list)):
                return False
            platform_capability = next(
                (item for item in declared if item.name == capability), None
            )
            if platform_capability is None:
                return False
            return action is None or platform_capability.action(action) is not None
        return True


__all__ = ["TelegramCapability", "TelegramClient"]
