"""Explicit submission of free-text tasks to the BTW work loop."""

from astrbot.api import btw_work_loop_enabled
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class WorkCommands:
    """The built-in work-loop command surface."""

    def __init__(self, context) -> None:
        self.context = context

    async def handle(self, event: AstrMessageEvent, task: str = "") -> None:
        """Submit a task, reserving empty input and ``status`` for queries."""
        stripped = (task or "").strip()
        if not stripped or stripped.lower() == "status":
            await reply_i18n(self.context, event, "work.usage")
            return
        await self.submit(event, stripped)

    async def submit(self, event: AstrMessageEvent, task: str) -> None:
        """Continue the admitted command event through the work loop."""
        config = self.context.config.get(umo=event.unified_msg_origin)
        if not btw_work_loop_enabled(config):
            await reply_i18n(self.context, event, "work.disabled")
            return
        event.message_str = task
        event.set_extra("should_run_command", False)
        event.set_extra("should_run_llm", True)
        event.set_extra("btw_force_work", True)
        event.set_extra("btw_loop", "work")
