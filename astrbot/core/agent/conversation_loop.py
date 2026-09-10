"""Opt-in conversation entry over the existing Agent request executor."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING

from astrbot.core.agent.btw.types import is_work_loop_enabled
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent

if TYPE_CHECKING:
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
    )


class ConversationLoop:
    """Own conversation admission without choosing an automatic classifier."""

    def __init__(self, agent_request: AgentRequestSubStage) -> None:
        self.agent_request = agent_request
        self._btw_enabled = False
        self.work_sessions = WorkSessionManager()
        self.work_loop: WorkLoop | None = None

    async def initialize(self, ctx: PipelineContext) -> None:
        """Initialize the shared Agent executor for this profile."""
        self.astrbot_config = ctx.astrbot_config
        btw = self.astrbot_config.get("btw", {})
        self._btw_enabled = isinstance(btw, dict) and bool(btw.get("enabled", False))
        await self.agent_request.initialize(ctx)
        btw = btw if isinstance(btw, dict) else {}
        work = btw.get("work_loop", {})
        work = work if isinstance(work, dict) else {}
        retention = btw.get("work_session", {})
        retention = retention if isinstance(retention, dict) else {}
        self.work_sessions.set_max_age_seconds(retention.get("max_age_seconds", 3600))
        concurrency = work.get("max_concurrent", 2)
        self.work_loop = WorkLoop(
            self.agent_request,
            self.work_sessions,
            max_concurrent=concurrency if type(concurrency) is int else 2,
        )

    def configure_detached_work(
        self,
        *,
        background_tasks: set[asyncio.Task],
        result_dispatcher: Callable[[AstrMessageEvent], Awaitable[None]],
        event_finalizer: Callable[[AstrMessageEvent], Awaitable[None]],
    ) -> None:
        """Attach the owning scheduler's delivery and cleanup services."""
        if self.work_loop is None:
            raise RuntimeError("ConversationLoop is not initialized")
        self.work_loop.configure_detached_execution(
            background_tasks=background_tasks,
            result_dispatcher=result_dispatcher,
            event_finalizer=event_finalizer,
        )

    async def close(self) -> None:
        """Stop work owned by this conversation entry."""
        if self.work_loop is not None:
            await self.work_loop.close()

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Process one admitted conversation using the current Agent path."""
        if (
            self._btw_enabled
            and event.get_extra("btw_force_work")
            and is_work_loop_enabled(self.astrbot_config)
        ):
            if self.work_loop is None:
                raise RuntimeError("ConversationLoop is not initialized")
            async for response in self.work_loop.submit(event):
                yield response
            return
        if self._btw_enabled:
            event.set_extra("btw_loop", "conversation")
        async for response in self.agent_request.process(event):
            yield response
