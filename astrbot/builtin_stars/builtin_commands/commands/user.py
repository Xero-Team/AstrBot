from astrbot.api import (
    Subject,
    sender_admission_key_from_id,
    sender_service_config,
    star,
)
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n

_SESSION_SERVICE_CONFIG_KEY = "session_service_config"


def _event_sender_scope(event: AstrMessageEvent) -> tuple[str, str]:
    platform_id = event.get_platform_id()
    if not (isinstance(platform_id, str) and platform_id.strip()):
        name = event.get_platform_name()
        platform_id = name if isinstance(name, str) and name.strip() else "unknown"
    bot_id = str(event.get_self_id() or "").strip() or "default"
    return platform_id, bot_id


def sender_key_from_token(event: AstrMessageEvent, token: str) -> str | None:
    """Mint a sender overlay key from a raw sender id or a full ``im:`` id.

    Args:
        event: Current command event, used to mint ``Subject.im`` for raw ids.
        token: Platform sender id or a full ``im:`` subject id.

    Returns:
        The sender preference scope id, or None when the token is empty or
        cannot be minted.
    """
    sender_id = token.strip()
    if not sender_id:
        return None
    platform_id, bot_id = _event_sender_scope(event)
    if sender_id.lower().startswith("im:"):
        parts = sender_id.split(":", 3)
        if len(parts) != 4:
            return None
        try:
            # Compare canonical subject components: platform and bot ids that
            # are not plain identifiers are base64-encoded by ``Subject.im``.
            token_subject = Subject.im(
                platform_instance=parts[1].strip(),
                bot_account_id=parts[2].strip(),
                sender_id=parts[3].strip(),
            )
            event_subject = Subject.im(
                platform_instance=platform_id,
                bot_account_id=bot_id,
                sender_id=parts[3].strip(),
            )
        except ValueError:
            return None
        if token_subject.id != event_subject.id:
            return None
        return sender_admission_key_from_id(sender_id)
    try:
        return Subject.im(
            platform_instance=platform_id,
            bot_account_id=bot_id,
            sender_id=sender_id,
        ).id
    except ValueError:
        return None


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
