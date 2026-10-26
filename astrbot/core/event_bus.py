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
import re
import time
from collections.abc import Callable
from contextlib import nullcontext

from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config import AstrBotConfig
from astrbot.core.observability import get_observability
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.error_redaction import redact_sensitive_text

from .platform import AstrMessageEvent

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_IDENTITY_LOG_LIMIT = 64


def _sanitize_log_identity(value: object | None, *, fallback: str = "") -> str:
    text = str(value) if value is not None else ""
    text = _CONTROL_CHARS.sub("", redact_sensitive_text(text)).strip()
    if not text:
        return fallback
    return text[:_IDENTITY_LOG_LIMIT]


UNIQUE_SESSION_ID_BUILDERS: dict[str, Callable[[AstrMessageEvent], str | None]] = {
    "aiocqhttp": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "napcat": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "slack": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "dingtalk": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "qq_official": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "qq_official_webhook": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "lark": lambda e: f"{e.get_sender_id()}%{e.get_group_id()}",
    "misskey": lambda e: f"{e.get_session_id()}_{e.get_sender_id()}",
    "matrix": lambda e: f"{e.get_sender_id()}_{e.get_group_id() or e.get_session_id()}",
}


def build_unique_session_id(event: AstrMessageEvent) -> str | None:
    """Build the per-member session ID for the event's platform, if any."""
    builder = UNIQUE_SESSION_ID_BUILDERS.get(event.get_platform_name())
    return builder(event) if builder else None


class EventBus:
    """用于处理事件的分发和处理"""

    _QUEUE_WAIT_LOG_THRESHOLD_S = 0.5

    def __init__(
        self,
        event_queue: asyncio.Queue,
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
            get_observability().record_event(event.get_platform_name())
            try:
                routing_umo = self._routing_umo(event)
                conf_info = self.astrbot_config_mgr.get_conf_info(routing_umo)
                conf_id = conf_info["id"]
                conf_name = conf_info.get("name") or conf_id
                with event.trace.context():
                    self._print_event(event, conf_name)
                scheduler = self.pipeline_scheduler_mapping.get(conf_id)
                if not scheduler:
                    logger.error(
                        f"PipelineScheduler not found for id: {conf_id}, event ignored."
                    )
                    continue
                self._apply_session_isolation(event, scheduler.ctx.astrbot_config)
                await self._semaphore.acquire()
                task = asyncio.create_task(
                    self._execute_scheduler(scheduler, event),
                    name=f"pipeline:{conf_id}",
                )
                self._pending_tasks.add(task)
                task.add_done_callback(self._on_task_done)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("事件总线分发异常", exc_info=True)

    @staticmethod
    def _apply_session_isolation(
        event: AstrMessageEvent,
        config: AstrBotConfig,
    ) -> None:
        """Finalize the session before pipeline registration and stop lookup.

        Isolating here, rather than in a pipeline stage, keeps the unified
        message origin used to register the event in ``ActiveEventRegistry``
        identical to the one used for stop lookup and unregistration.

        Args:
            event: Incoming event whose original UMO selected the profile.
            config: Selected profile's configuration controlling isolation.
        """
        platform_settings = config.get("platform_settings", {})
        if not platform_settings.get("unique_session", False):
            return
        if event.message_obj.type != MessageType.GROUP_MESSAGE:
            return
        if event.get_extra("onebot_post_type") in {"notice", "request"}:
            return
        sid = build_unique_session_id(event)
        if sid:
            event.session_id = sid
            event.trace.umo = event.unified_msg_origin

    @staticmethod
    def _routing_umo(event: AstrMessageEvent) -> str:
        """Resolve a trusted WebChat thread to its parent config route."""

        parent_session_id = event.get_extra("webchat_parent_session_id")
        if (
            event.get_platform_name() == "webchat"
            and isinstance(parent_session_id, str)
            and parent_session_id
        ):
            sender_id = str(event.get_sender_id())
            return f"webchat:FriendMessage:webchat!{sender_id}!{parent_session_id}"
        return event.unified_msg_origin

    async def _execute_scheduler(
        self,
        scheduler: PipelineScheduler,
        event: AstrMessageEvent,
    ) -> None:
        observability = get_observability()
        # Only build the span attributes when tracing is actually enabled.
        span = (
            observability.span(
                "pipeline.execute",
                {"platform": event.get_platform_name()},
            )
            if observability.tracing_enabled
            else nullcontext()
        )
        try:
            with span:
                await scheduler.execute(event)
        finally:
            self._semaphore.release()
            observability.record_event_processed()

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
        queue_wait_suffix = ""
        created_at = getattr(event, "created_at", None)
        if isinstance(created_at, int | float):
            queue_wait = max(0.0, time.time() - created_at)
            if queue_wait >= self._QUEUE_WAIT_LOG_THRESHOLD_S:
                queue_wait_suffix = f" (queued {queue_wait:.2f}s)"

        raw_sender_id = str(event.get_sender_id())
        sender_id = _sanitize_log_identity(raw_sender_id, fallback="unknown")
        sender_name = _sanitize_log_identity(event.get_sender_name())
        platform_id = event.get_platform_id()
        platform_name = event.get_platform_name()
        outline = redact_sensitive_text(str(event.get_message_outline()))[:160]
        summary = f"{conf_name} event from {sender_name or sender_id}: {outline}{queue_wait_suffix}"
        sender_label = f"{sender_name}/{sender_id}" if sender_name else sender_id
        logger.info(
            f"[{conf_name}] Inbound platform event from {sender_label}: {outline}",
            extra={
                "category": "user_chat",
                "privacy": "private",
                "platform": str(platform_id or platform_name),
                "platform_id": platform_id,
                "platform_type": platform_name,
                "conversation_id": event.unified_msg_origin,
                "sender_id": sender_id,
                "summary": summary,
            },
        )
