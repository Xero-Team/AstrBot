from astrbot.api import Subject, star
from astrbot.api.event import AstrMessageEvent
from astrbot.core.star.session_llm_manager import sender_service_config

from .reply import reply_i18n

_SESSION_SERVICE_CONFIG_KEY = "session_service_config"


def sender_key_from_token(event: AstrMessageEvent, token: str) -> str | None:
    """Mint a sender overlay key from a raw sender id or a full ``im:`` id.

    Args:
        event: Current command event, used to mint ``Subject.im`` for raw ids.
        token: Platform sender id or a full ``im:`` subject id.

    Returns:
        The sender preference scope id, or None when the token is empty.
    """
    sender_id = token.strip()
    if not sender_id:
        return None
    if sender_id.startswith("im:"):
        return sender_id
    return Subject.im(
        platform_instance=event.get_platform_id(),
        bot_account_id=event.get_self_id() or "default",
        sender_id=sender_id,
    ).id


class UserCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def set_blocked(
        self, event: AstrMessageEvent, token: str, blocked: bool
    ) -> None:
        """Write the sender ``blocked`` overlay."""
        await self._write(
            event,
            token,
            "user.block.ok" if blocked else "user.unblock.ok",
            blocked=blocked,
        )

    async def set_llm_enabled(
        self, event: AstrMessageEvent, token: str, enabled: bool
    ) -> None:
        """Write the sender ``llm_enabled`` overlay."""
        await self._write(
            event,
            token,
            "user.llm.on.ok" if enabled else "user.llm.off.ok",
            llm_enabled=enabled,
        )

    async def _write(
        self,
        event: AstrMessageEvent,
        token: str,
        message_key: str,
        **fields: bool,
    ) -> None:
        sender_key = sender_key_from_token(event, token)
        if sender_key is None:
            await reply_i18n(self.context, event, "user.usage")
            return
        existing = await self.context.preferences.sender_get(
            sender_key,
            _SESSION_SERVICE_CONFIG_KEY,
            {},
        )
        await self.context.preferences.sender_put(
            sender_key,
            _SESSION_SERVICE_CONFIG_KEY,
            sender_service_config(existing, **fields),
        )
        await reply_i18n(self.context, event, message_key, sender=sender_key)
