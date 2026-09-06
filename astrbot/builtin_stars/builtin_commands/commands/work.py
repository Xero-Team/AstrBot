"""BTW work-loop command (/work, /work status)."""

from astrbot.api import btw_work_latest_status, btw_work_loop_enabled
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class WorkCommands:
    """BTW work-loop command surface."""

    def __init__(self, context) -> None:
        self.context = context

    async def handle(self, event: AstrMessageEvent, task: str = "") -> None:
        """Show status, or hand a free-text task to the work loop.

        ``/work`` and a remainder of ``status`` (case-insensitive) query
        the newest session task. Any other remainder is a work-loop
        request: the handler rewrites ``event.message_str`` and lets
        ProcessStage continue into ConversationLoop.
        """
        stripped = (task or "").strip()
        if stripped == "" or stripped.lower() == "status":
            await self.status(event)
            return
        await self.submit(event, stripped)

    async def status(self, event: AstrMessageEvent) -> None:
        """Show the newest work-session status for this origin."""
        config_id = getattr(getattr(event, "resource", None), "config_id", "") or ""
        latest = await btw_work_latest_status(
            config_id,
            event.unified_msg_origin,
        )
        if latest is None:
            await reply_i18n(self.context, event, "work.status.none")
            return
        request, status = latest
        body = await self.context.i18n.t(event, f"work.status.{status}", task=request)
        await reply_i18n(self.context, event, "work.status.body", body=body)

    async def submit(self, event: AstrMessageEvent, task: str) -> None:
        """Mark the event as a BTW work request and continue to the Agent."""
        cfg = self.context.config.get(umo=event.unified_msg_origin)
        if not btw_work_loop_enabled(cfg):
            await reply_i18n(self.context, event, "work.disabled")
            return
        event.message_str = task
        event.set_extra("should_run_command", False)
        event.set_extra("should_run_llm", True)
        event.set_extra("btw_force_work", True)
        event.set_extra("btw_loop", "work")
