from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.star.session_llm_manager import SessionServiceManager


class LLMCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def llm(self, event: AstrMessageEvent) -> None:
        """Toggle LLM chat for the current session."""
        umo = event.unified_msg_origin
        enabled = await SessionServiceManager.is_llm_enabled_for_session(umo)
        new_enabled = not enabled
        await SessionServiceManager.set_llm_status_for_session(umo, new_enabled)
        status = "enabled" if new_enabled else "disabled"
        event.set_result(
            MessageEventResult().message(
                f"✅ LLM chat is now {status} for the current session.",
            ),
        )
