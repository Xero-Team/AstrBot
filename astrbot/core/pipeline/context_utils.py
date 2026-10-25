import asyncio
import inspect
import traceback
import typing as T
from collections.abc import AsyncGenerator as AsyncGeneratorABC

from astrbot import logger
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star import PluginRegistry
from astrbot.core.star.star_handler import EventType, HandlerRegistry
from astrbot.core.utils.error_redaction import redact_sensitive_text


async def call_handler(
    event: AstrMessageEvent,
    handler: T.Callable[..., T.Awaitable[T.Any] | T.AsyncGenerator[T.Any]],
    *args,
    **kwargs,
) -> T.AsyncGenerator[T.Any]:
    """执行事件处理函数并处理其返回结果

    该方法负责调用处理函数并处理不同类型的返回值。它支持两种类型的处理函数:
    1. 异步生成器: 实现洋葱模型，每次 yield 都会将控制权交回上层
    2. 协程: 执行一次并处理返回值

    Args:
        event (AstrMessageEvent): 事件对象
        handler (Awaitable): 事件处理函数

    Returns:
        AsyncGenerator[None, None]: 异步生成器，用于在管道中传递控制流

    """
    ready_to_call = None  # 一个协程或者异步生成器

    trace_ = None

    try:
        ready_to_call = handler(event, *args, **kwargs)
    except TypeError:
        logger.error("处理函数参数不匹配，请检查 handler 的定义。")
        raise

    if ready_to_call is None:
        return

    if isinstance(ready_to_call, AsyncGeneratorABC):
        _has_yielded = False
        try:
            async for ret in ready_to_call:
                # 这里逐步执行异步生成器, 对于每个 yield 返回的 ret, 执行下面的代码
                # 返回值只能是 MessageEventResult 或者 None（无返回值）
                _has_yielded = True
                if isinstance(ret, MessageEventResult):
                    # 如果返回值是 MessageEventResult, 设置结果并继续
                    event.set_result(ret)
                    yield
                else:
                    # 如果返回值是 None, 则不设置结果并继续
                    # 继续执行后续阶段
                    yield ret
            if not _has_yielded:
                # 如果这个异步生成器没有执行到 yield 分支
                yield
        except Exception as e:
            logger.error(f"Previous Error: {trace_}")
            raise e
    elif inspect.iscoroutine(ready_to_call):
        # 如果只是一个协程, 直接执行
        ret = await ready_to_call
        if isinstance(ret, MessageEventResult):
            event.set_result(ret)
            yield
        else:
            yield ret


async def call_event_hook(
    event: AstrMessageEvent,
    hook_type: EventType,
    *args,
    handler_registry: HandlerRegistry,
    plugin_registry: PluginRegistry,
    **kwargs,
) -> bool:
    """调用事件钩子函数

    Returns:
        bool: 如果事件被终止，返回 True
    #

    """
    handlers = handler_registry.get_handlers_by_event_type(
        hook_type,
        plugins_name=event.plugins_name,
    )
    for handler in handlers:
        plugin = plugin_registry.get_by_module(handler.handler_module_path)
        plugin_name = plugin.name if plugin else handler.handler_module_path
        plugin_display_name = plugin.display_name if plugin else None
        handler_category = (
            "llm_tool" if hook_type == EventType.OnCallingFuncToolEvent else "hook"
        )
        event.trace.record(
            "handler_start",
            kind="plugin_handler",
            status="running",
            plugin=plugin_name,
            plugin_display_name=plugin_display_name or plugin_name,
            handler=handler.handler_name,
            handler_full_name=handler.handler_full_name,
            handler_type=handler.event_type.name,
            handler_category=handler_category,
            hook=hook_type.name,
        )
        try:
            assert inspect.iscoroutinefunction(handler.handler)
            logger.debug(
                f"hook({hook_type.name}) -> {plugin_name} - {handler.handler_name}",
            )
            await handler.handler(event, *args, **kwargs)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt, SystemExit:
            raise
        except Exception:
            logger.error(redact_sensitive_text(traceback.format_exc()))
            event.trace.record(
                "handler_end",
                kind="plugin_handler",
                status="error",
                plugin=plugin_name,
                plugin_display_name=plugin_display_name or plugin_name,
                handler=handler.handler_name,
                handler_full_name=handler.handler_full_name,
                handler_type=handler.event_type.name,
                handler_category=handler_category,
                hook=hook_type.name,
            )
        else:
            event.trace.record(
                "handler_end",
                kind="plugin_handler",
                status="success",
                plugin=plugin_name,
                plugin_display_name=plugin_display_name or plugin_name,
                handler=handler.handler_name,
                handler_full_name=handler.handler_full_name,
                handler_type=handler.event_type.name,
                handler_category=handler_category,
                hook=hook_type.name,
            )

        if event.is_stopped():
            logger.info(
                f"{plugin_name} - {handler.handler_name} 终止了事件传播。",
            )
            return True

    return event.is_stopped()
