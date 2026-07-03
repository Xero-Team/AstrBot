"""事件总线, 用于处理事件的分发和处理
事件总线是一个异步队列, 用于接收各种消息事件, 并将其发送到Scheduler调度器进行处理
其中包含了一个无限循环的调度函数, 用于从事件队列中获取新的事件, 并创建一个新的异步任务来执行管道调度器的处理逻辑

class:
    EventBus: 事件总线, 用于处理事件的分发和处理

工作流程:
1. 维护一个异步队列, 来接受各种消息事件
2. 无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑
"""

import asyncio
from asyncio import Queue

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.pipeline.scheduler import PipelineScheduler

from .platform import AstrMessageEvent


class EventBus:
    """用于处理事件的分发和处理"""

    def __init__(
        self,
        event_queue: Queue,
        pipeline_scheduler_mapping: dict[str, PipelineScheduler],
        astrbot_config_mgr: AstrBotConfigManager,
        max_concurrency: int = 128,
    ) -> None:
        self.event_queue = event_queue  # 事件队列
        # abconf uuid -> scheduler
        self.pipeline_scheduler_mapping = pipeline_scheduler_mapping
        self.astrbot_config_mgr = astrbot_config_mgr
        # 持有正在执行的 pipeline 任务的强引用, 防止 task 在 pending 状态被 GC 回收
        self._pending_tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def dispatch(self) -> None:
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            try:
                conf_info = self.astrbot_config_mgr.get_conf_info(
                    event.unified_msg_origin
                )
                conf_id = conf_info["id"]
                conf_name = conf_info.get("name") or conf_id
                self._print_event(event, conf_name)
                scheduler = self.pipeline_scheduler_mapping.get(conf_id)
                if not scheduler:
                    logger.error(
                        f"PipelineScheduler not found for id: {conf_id}, event ignored."
                    )
                    continue
                task = asyncio.create_task(
                    self._execute_with_limit(scheduler, event),
                    name=f"pipeline:{conf_id}",
                )
                self._pending_tasks.add(task)
                task.add_done_callback(self._on_task_done)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("事件总线分发异常", exc_info=True)

    async def _execute_with_limit(
        self,
        scheduler: PipelineScheduler,
        event: AstrMessageEvent,
    ) -> None:
        async with self._semaphore:
            await scheduler.execute(event)

    def _on_task_done(self, task: asyncio.Task) -> None:
        """pipeline 任务结束回调: 移除强引用并暴露未捕获的异常"""
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("pipeline 任务执行异常", exc_info=exc)

    async def shutdown(self) -> None:
        """Cancel and await in-flight pipeline tasks."""
        tasks = list(self._pending_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pending_tasks.clear()

    def _print_event(self, event: AstrMessageEvent, conf_name: str) -> None:
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象

        """
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}",
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_id()}: {event.get_message_outline()}",
            )
