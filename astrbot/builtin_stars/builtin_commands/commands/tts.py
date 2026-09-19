from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.core.auth.admission import overlay_flag_enabled

from .reply import reply_i18n


class TtsCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def status(self, event: AstrMessageEvent) -> None:
        """Show the TTS state for the current session."""
        umo = event.unified_msg_origin
        settings = await self.context.preferences.session_get(
            umo,
            "session_service_config",
            {},
        )
        enabled = overlay_flag_enabled(settings.get("tts_enabled"), scope_id=umo)
        await reply_i18n(
            self.context,
            event,
            "tts.status.enabled" if enabled else "tts.status.disabled",
        )

    async def set_enabled(
        self,
        event: AstrMessageEvent,
        enabled: bool,
    ) -> None:
        """Set the TTS state for the current session."""
        umo = event.unified_msg_origin
        settings = await self.context.preferences.session_get(
            umo,
            "session_service_config",
            {},
        )
        settings = dict(settings or {})
        settings["tts_enabled"] = enabled
        await self.context.preferences.session_put(
            umo,
            "session_service_config",
            settings,
        )
        await reply_i18n(
            self.context,
            event,
            "tts.set.enabled" if enabled else "tts.set.disabled",
        )
