from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.star.session_llm_manager import SessionServiceManager


class ChatCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def status(self, event: AstrMessageEvent) -> None:
        """Show the LLM chat state for the current session."""
        umo = event.unified_msg_origin
        services = SessionServiceManager(self.context.preferences)
        enabled = await services.is_llm_enabled_for_session(umo)
        status = "enabled" if enabled else "disabled"
        event.set_result(
            MessageEventResult().message(
                f"LLM chat is {status} for the current session.",
            ),
        )

    async def set_enabled(
        self,
        event: AstrMessageEvent,
        enabled: bool,
    ) -> None:
        """Set the LLM chat state for the current session."""
        umo = event.unified_msg_origin
        services = SessionServiceManager(self.context.preferences)
        await services.set_llm_status_for_session(umo, enabled)
        status = "enabled" if enabled else "disabled"
        event.set_result(
            MessageEventResult().message(
                f"✅ LLM chat is now {status} for the current session.",
            ),
        )
