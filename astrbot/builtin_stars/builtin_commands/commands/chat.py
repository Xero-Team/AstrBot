from astrbot.api import overlay_flag_enabled, session_admission_key_from_event, star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class ChatCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def status(self, event: AstrMessageEvent) -> None:
        """Show the LLM chat state for the current session."""
        session_key = session_admission_key_from_event(event)
        settings = await self.context.preferences.session_get(
            session_key,
            "session_service_config",
            {},
        )
        enabled = overlay_flag_enabled(
            settings.get("llm_enabled"),
            scope_id=session_key,
        )
        await reply_i18n(
            self.context,
            event,
            "chat.status.enabled" if enabled else "chat.status.disabled",
        )

    async def set_enabled(
        self,
        event: AstrMessageEvent,
        enabled: bool,
    ) -> None:
        """Set the LLM chat state for the canonical group or private session."""
        session_key = session_admission_key_from_event(event)
        settings = await self.context.preferences.session_get(
            session_key,
            "session_service_config",
            {},
        )
        settings = dict(settings or {})
        settings["llm_enabled"] = enabled
        await self.context.preferences.session_put(
            session_key,
            "session_service_config",
            settings,
        )
        await reply_i18n(
            self.context,
            event,
            "chat.set.enabled" if enabled else "chat.set.disabled",
        )
