import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

from astrbot.core.agent.conversation_loop import ConversationLoop
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import StarHandlerMetadata

from ..context import PipelineContext
from ..stage import Stage
from .method.agent_request import AgentRequestSubStage
from .method.star_request import StarRequestSubStage


class ProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

        btw = self.config.get("btw", {})
        btw = btw if isinstance(btw, dict) else {}
        self._btw_enabled = bool(btw.get("enabled", False))
        if self._btw_enabled:
            # BTW dual-loop mode: the ConversationLoop classifies and
            # dispatches work requests over the same Agent sub-stage.
            self.conversation_loop = ConversationLoop()
            await self.conversation_loop.initialize(ctx)
            self.conversation_loop.expose_to_commands(ctx.astrbot_config_id)
            self._agent_request = self.conversation_loop.agent_request
        else:
            # BTW disabled: ProcessStage holds the current Agent sub-stage
            # directly, exactly as upstream master does — no wrapper.
            self.conversation_loop = None
            self._agent_request = AgentRequestSubStage()
            await self._agent_request.initialize(ctx)

        # initialize star request sub stage
        self.star_request_sub_stage = StarRequestSubStage()
        await self.star_request_sub_stage.initialize(ctx)

    def configure_detached_work(
        self,
        *,
        background_tasks: set[asyncio.Task],
        result_dispatcher: Callable[[AstrMessageEvent], Awaitable[None]],
        event_finalizer: Callable[[AstrMessageEvent], Awaitable[None]],
    ) -> None:
        """Give the BTW work loop lifecycle-owned background services."""
        if self.conversation_loop is None:
            return
        self.conversation_loop.configure_detached_work(
            background_tasks=background_tasks,
            result_dispatcher=result_dispatcher,
            event_finalizer=event_finalizer,
        )

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[None]:
        """处理事件"""
        activated_handlers: list[StarHandlerMetadata] = event.get_extra(
            "activated_handlers",
        )
        handled_plugin_provider_request = False
        # 有插件 Handler 被激活
        if activated_handlers:
            async for resp in self.star_request_sub_stage.process(event):
                # 生成器返回值处理
                if isinstance(resp, ProviderRequest):
                    # Handler 的 LLM 请求
                    handled_plugin_provider_request = True
                    event.set_extra("provider_request", resp)
                    _t = False
                    async for _ in self._agent_request.process(event):
                        _t = True
                        yield
                    if not _t:
                        yield
                else:
                    yield
        if handled_plugin_provider_request:
            return

        # 调用 LLM 相关请求
        if not self.ctx.astrbot_config["provider_settings"].get("enable", True):
            return

        if (
            not event._has_send_oper
            and event.get_extra("should_run_llm")
            and not event.call_llm
        ):
            # Skip the default Agent after a handler has already produced output.
            if (
                event.get_result() and not event.is_stopped()
            ) or not event.get_result():
                async for _ in self._dispatch_agent(event):
                    yield

    def _dispatch_agent(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Run BTW classification when enabled, otherwise the Agent sub-stage."""
        if self.conversation_loop is not None:
            return self.conversation_loop.process(event)
        return self._agent_request.process(event)
