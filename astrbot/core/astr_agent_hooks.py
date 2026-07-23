from typing import Any

from mcp.types import CallToolResult

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.star_handler import EventType


def _runtime_hook_catalogs(run_context: ContextWrapper[AstrAgentContext]):
    """Return the per-runtime handler and plugin registries for agent hooks."""

    catalogs = run_context.context.context.catalogs
    return catalogs.handlers, catalogs.plugins


class MainAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    async def on_agent_begin(
        self, run_context: ContextWrapper[AstrAgentContext]
    ) -> None:
        handlers, plugins = _runtime_hook_catalogs(run_context)
        await call_event_hook(
            run_context.context.event,
            EventType.OnAgentBeginEvent,
            run_context,
            handler_registry=handlers,
            plugin_registry=plugins,
        )

    async def on_agent_done(self, run_context, llm_response) -> None:
        # 执行事件钩子
        if llm_response and llm_response.reasoning_content:
            # we will use this in result_decorate stage to inject reasoning content to chain
            run_context.context.event.set_extra(
                "_llm_reasoning_content", llm_response.reasoning_content
            )

        handlers, plugins = _runtime_hook_catalogs(run_context)
        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMResponseEvent,
            llm_response,
            handler_registry=handlers,
            plugin_registry=plugins,
        )
        await call_event_hook(
            run_context.context.event,
            EventType.OnAgentDoneEvent,
            run_context,
            llm_response,
            handler_registry=handlers,
            plugin_registry=plugins,
        )

    async def on_tool_start(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        tool: FunctionTool[Any],
        tool_args: dict | None,
    ) -> None:
        handlers, plugins = _runtime_hook_catalogs(run_context)
        await call_event_hook(
            run_context.context.event,
            EventType.OnUsingLLMToolEvent,
            tool,
            tool_args,
            handler_registry=handlers,
            plugin_registry=plugins,
        )

    async def on_tool_end(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        tool: FunctionTool[Any],
        tool_args: dict | None,
        tool_result: CallToolResult | None,
    ) -> None:
        run_context.context.event.clear_result()
        handlers, plugins = _runtime_hook_catalogs(run_context)
        await call_event_hook(
            run_context.context.event,
            EventType.OnLLMToolRespondEvent,
            tool,
            tool_args,
            tool_result,
            handler_registry=handlers,
            plugin_registry=plugins,
        )


class EmptyAgentHooks(BaseAgentRunHooks[AstrAgentContext]):
    pass
