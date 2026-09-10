"""Opt-in conversation entry over the existing Agent request executor."""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

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

    async def initialize(self, ctx: PipelineContext) -> None:
        """Initialize the shared Agent executor for this profile."""
        self.astrbot_config = ctx.astrbot_config
        btw = self.astrbot_config.get("btw", {})
        self._btw_enabled = isinstance(btw, dict) and bool(btw.get("enabled", False))
        await self.agent_request.initialize(ctx)

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Process one admitted conversation using the current Agent path."""
        if self._btw_enabled:
            event.set_extra("btw_loop", "conversation")
        async for response in self.agent_request.process(event):
            yield response
