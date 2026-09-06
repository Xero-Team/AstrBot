"""The user-facing BTW conversation-loop entry point.

The first BTW increment intentionally reuses the established Agent request
path.  It therefore preserves the current local Tool Loop and third-party
Agent runner behaviour, while giving later classifier and work-loop work one
stable hand-off boundary.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING

from astrbot.core.agent.btw import (
    TaskClassifier,
    TaskType,
    WorkLoop,
    WorkSessionManager,
    WorkSessionStatus,
    runtime_registry,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent

if TYPE_CHECKING:
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
    )


class ConversationLoop:
    """Process user-visible AI conversations through the current Agent path.

    It owns task classification and dispatches work requests to the work loop.
    Both loops reuse the established Agent request executor. Plugin and MCP
    execution capabilities default to the work loop unless an operator assigns
    them to the conversation loop or both loops explicitly.  When BTW is
    disabled the loop is a transparent pass-through to the Agent request
    executor, matching the upstream path exactly.
    """

    def __init__(
        self,
        agent_request: AgentRequestSubStage | None = None,
        *,
        classifier: TaskClassifier | None = None,
        work_sessions: WorkSessionManager | None = None,
    ) -> None:
        if agent_request is None:
            from ..pipeline.process_stage.method.agent_request import (
                AgentRequestSubStage,
            )

            agent_request = AgentRequestSubStage()
        self.agent_request = agent_request
        self.classifier = classifier
        self.work_sessions = work_sessions or WorkSessionManager()
        self.work_loop: WorkLoop | None = None
        self._btw_enabled = False

    async def initialize(self, ctx: PipelineContext) -> None:
        """Initialize the existing Agent request executor.

        Args:
            ctx: The owning pipeline context.
        """
        await self.agent_request.initialize(ctx)
        if self.classifier is None:
            self.classifier = TaskClassifier(ctx.astrbot_config)
        btw = ctx.astrbot_config.get("btw", {})
        btw = btw if isinstance(btw, dict) else {}
        self._btw_enabled = bool(btw.get("enabled", False))
        work_loop_config = btw.get("work_loop", {}) if isinstance(btw, dict) else {}
        work_session_config = (
            btw.get("work_session", {}) if isinstance(btw, dict) else {}
        )
        max_concurrent = (
            work_loop_config.get("max_concurrent", 2)
            if isinstance(work_loop_config, dict)
            else 2
        )
        max_age_seconds = (
            work_session_config.get("max_age_seconds", 3600)
            if isinstance(work_session_config, dict)
            else 3600
        )
        self.work_sessions.set_max_age_seconds(max_age_seconds)
        self.work_loop = WorkLoop(
            self.agent_request,
            self.work_sessions,
            max_concurrent=max_concurrent if isinstance(max_concurrent, int) else 2,
        )

    def configure_detached_work(
        self,
        *,
        background_tasks: set[asyncio.Task],
        result_dispatcher: Callable[[AstrMessageEvent], Awaitable[None]],
        event_finalizer: Callable[[AstrMessageEvent], Awaitable[None]],
    ) -> None:
        """Attach runtime-owned execution callbacks to the work loop."""
        if self.work_loop is None:
            raise RuntimeError("ConversationLoop must be initialized before use")
        self.work_loop.configure_detached_execution(
            background_tasks=background_tasks,
            result_dispatcher=result_dispatcher,
            event_finalizer=event_finalizer,
        )

    def expose_to_commands(self, config_id: str) -> None:
        """Publish work-session state for the built-in ``work`` command group."""
        runtime_registry.register(config_id, self.work_sessions)

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Run one conversation through the current Agent request path.

        When BTW is disabled the loop is a transparent pass-through: no
        classification, no loop tagging — the event reaches the Agent request
        executor exactly as it would on the upstream path.  Work-session
        status is queried through the ``/work status`` command, not by
        inspecting message text.

        Args:
            event: The message event to process.

        Yields:
            Pipeline progress markers emitted by the Agent request executor.
        """
        if not self._btw_enabled:
            async for response in self.agent_request.process(event):
                yield response
            return

        if self.classifier is None:
            raise RuntimeError("ConversationLoop must be initialized before use")
        task_type = await self.classifier.classify(event)
        if task_type is TaskType.WORK:
            if self.work_loop is None:
                raise RuntimeError("ConversationLoop must be initialized before use")
            async for response in self.work_loop.submit(event):
                yield response
            return

        event.set_extra("btw_loop", "conversation")
        async for response in self.agent_request.process(event):
            yield response

    @staticmethod
    def format_status(status: WorkSessionStatus, locale: str = "zh-CN") -> str:
        """Render one work-session status as a user-facing string."""
        from astrbot.core.agent.btw import i18n as work_i18n

        return f"📊 {work_i18n.text(locale, f'btw.work.status.{status.value}')}"
