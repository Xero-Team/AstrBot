"""BTW work-loop commands (/work status, /work <task>)."""


from typing import Annotated

from astrbot.api import btw_work_latest_status
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import GreedyStr

from .reply import reply_i18n


class WorkCommands:
    """BTW work-loop command surface."""

    def __init__(self, context) -> None:
        self.context = context

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

    async def run(
        self,
        event: AstrMessageEvent,
        task: Annotated[str, GreedyStr],
    ) -> None:
        """Dispatch the task text through the BTW work loop.

        The command handler tags the in-flight event so the process stage's
        Agent request runs with the work-loop policy; the message text is
        rewritten to the task body so downstream assembly sees only the task.
        """
        task = (task or "").strip()
        if not task:
            await reply_i18n(self.context, event, "work.run.usage")
            return
        event.message_str = task
        event.set_extra("should_run_command", False)
        event.set_extra("should_run_llm", True)
        event.set_extra("btw_loop", "work")
        # Do not stop the event: the pipeline continues into the Agent stage.
