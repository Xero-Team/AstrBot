import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

from astrbot.core.agent.conversation_loop import ConversationLoop
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import StarHandlerMetadata

from ..context import PipelineContext
from ..stage import Stage
from .method.star_request import StarRequestSubStage


class ProcessStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

        self.conversation_loop = ConversationLoop()
        await self.conversation_loop.initialize(ctx)

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
                    async for _ in self.conversation_loop.process(event):
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
                async for _ in self.conversation_loop.process(event):
                    yield
