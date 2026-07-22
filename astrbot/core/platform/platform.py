import abc
import asyncio
import logging
import uuid
from asyncio import Queue, QueueFull
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.task_utils import cancel_tracked_tasks, create_tracked_task

from .astr_message_event import AstrMessageEvent
from .astrbot_message import AstrBotMessage
from .message_session import MessageSession
from .platform_metadata import PlatformMetadata
from .route_identity import PlatformRouteIdentity
from .send_result import PlatformSendResult

PLATFORM_ACTION_METHOD_NAMES = (
    "set_group_admin",
    "set_group_ban",
    "set_group_card",
    "kick_group_member",
    "kick_group_members",
    "leave_group",
    "set_group_whole_ban",
    "set_essence_message",
    "delete_essence_message",
    "send_group_notice",
    "send_like",
    "send_poke",
)

logger = logging.getLogger("astrbot")


class PlatformStatus(Enum):
    """平台运行状态"""

    PENDING = "pending"  # 待启动
    RUNNING = "running"  # 运行中
    ERROR = "error"  # 发生错误
    STOPPED = "stopped"  # 已停止


@dataclass
class PlatformError:
    """平台错误信息"""

    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    traceback: str | None = None


class Platform(abc.ABC):
    @classmethod
    def declared_supported_actions(cls) -> list[str]:
        """Return proactive platform actions implemented by the adapter class."""
        supported: list[str] = []
        for action_name in PLATFORM_ACTION_METHOD_NAMES:
            platform_method = getattr(Platform, action_name, None)
            adapter_method = getattr(cls, action_name, None)
            if platform_method is None or adapter_method is None:
                continue
            if adapter_method is not platform_method:
                supported.append(action_name)
        return supported

    def __init__(self, config: dict, event_queue: Queue) -> None:
        super().__init__()
        # 平台配置
        self.config = config
        # Runtime capabilities are injected by PlatformManager after adapter
        # construction. Adapters that need them declare no module globals.
        self.database: Any = None
        self.runtime_config: Any = None
        self.preferences: Any = None
        # 维护了消息平台的事件队列，EventBus 会从这里取出事件并处理。
        self._event_queue = event_queue
        self.client_self_id = uuid.uuid4().hex
        # Auxiliary work triggered by this adapter cannot outlive the adapter
        # instance. PlatformManager tears it down even if an adapter's own
        # terminate() implementation does not call super().
        self._background_tasks: set[asyncio.Task] = set()

        # 平台运行状态
        self._status: PlatformStatus = PlatformStatus.PENDING
        self._errors: list[PlatformError] = []
        self._started_at: datetime | None = None

    @property
    def status(self) -> PlatformStatus:
        """获取平台运行状态"""
        return self._status

    @status.setter
    def status(self, value: PlatformStatus) -> None:
        """设置平台运行状态"""
        self._status = value
        if value == PlatformStatus.RUNNING and self._started_at is None:
            self._started_at = datetime.now()

    @property
    def errors(self) -> list[PlatformError]:
        """获取错误列表"""
        return self._errors

    @property
    def last_error(self) -> PlatformError | None:
        """获取最近的错误"""
        return self._errors[-1] if self._errors else None

    def record_error(self, message: str, traceback_str: str | None = None) -> None:
        """记录一个错误"""
        self._errors.append(PlatformError(message=message, traceback=traceback_str))
        self._status = PlatformStatus.ERROR

    def clear_errors(self) -> None:
        """清除错误记录"""
        self._errors.clear()
        if self._status == PlatformStatus.ERROR:
            self._status = PlatformStatus.RUNNING

    def unified_webhook(self) -> bool:
        """是否正在使用统一 Webhook 模式"""
        return bool(
            self.config.get("unified_webhook_mode", False)
            and self.config.get("webhook_uuid")
        )

    def get_stats(self) -> dict:
        """获取平台统计信息"""
        meta = self.meta()
        meta_info = {
            "id": meta.id,
            "name": meta.name,
            "display_name": meta.adapter_display_name or meta.name,
            "description": meta.description,
            "support_streaming_message": meta.support_streaming_message,
            "support_proactive_message": meta.support_proactive_message,
            "supported_actions": self.supported_actions(),
        }
        return {
            "id": meta.id or self.config.get("id"),
            "type": meta.name,
            "display_name": meta.adapter_display_name or meta.name,
            "status": self._status.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "error_count": len(self._errors),
            "last_error": {
                "message": self.last_error.message,
                "timestamp": self.last_error.timestamp.isoformat(),
                "traceback": self.last_error.traceback,
            }
            if self.last_error
            else None,
            "unified_webhook": self.unified_webhook(),
            "meta": meta_info,
        }

    @abc.abstractmethod
    def run(self) -> Coroutine[Any, Any, None]:
        """得到一个平台的运行实例，需要返回一个协程对象。"""
        raise NotImplementedError

    async def terminate(self) -> None:
        """终止一个平台的运行实例。"""

    async def _cancel_background_tasks(self) -> None:
        """Cancel auxiliary tasks owned by this platform instance."""
        await cancel_tracked_tasks(self._background_tasks)

    async def refresh_registered_commands(self) -> None:
        """Refresh platform-native command registrations when supported."""

    @abc.abstractmethod
    def meta(self) -> PlatformMetadata:
        """得到一个平台的元数据。"""
        raise NotImplementedError

    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ) -> PlatformSendResult | None:
        """通过会话发送消息。该方法旨在让插件能够直接通过**可持久化的会话数据**发送消息，而不需要保存 event 对象。

        异步方法。
        """
        create_tracked_task(
            self._background_tasks,
            Metric.upload(msg_event_tick=1, adapter_name=self.meta().name),
            name=f"metric:send-by-session:{self.meta().name}",
        )
        return PlatformSendResult(
            platform_id=self.meta().id,
            success=True,
            target=session.session_id,
            message_count=len(message_chain.chain),
        )

    async def send_by_route(
        self,
        route_identity: PlatformRouteIdentity,
        message_chain: MessageChain,
    ) -> PlatformSendResult | None:
        """Send a reply using immutable transport routing identity."""
        session = MessageSession(
            platform_name=route_identity.platform_id,
            message_type=route_identity.message_type,
            session_id=route_identity.target_id,
        )
        return await self.send_by_session(session, message_chain)

    def supported_actions(self) -> list[str]:
        """Return platform-specific proactive actions supported by this adapter."""
        return type(self).declared_supported_actions()

    def supports_action(self, action_name: str) -> bool:
        """Whether this adapter overrides a named proactive platform action."""
        return action_name in type(self).declared_supported_actions()

    def commit_event(self, event: AstrMessageEvent) -> bool:
        """提交一个事件到事件队列。"""
        try:
            self._event_queue.put_nowait(event)
        except QueueFull:
            logger.warning(
                "Event queue full; dropping event from %s",
                event.unified_msg_origin,
            )
            return False
        return True

    def create_event(self, message: AstrBotMessage) -> AstrMessageEvent:
        """Creates a message event for this platform.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created message event.
        """
        return AstrMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
        )

    def _unsupported_action(self, action_name: str) -> NotImplementedError:
        return NotImplementedError(
            f"平台 {self.meta().name} 不支持动作 `{action_name}`"
        )

    async def set_group_admin(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        enable: bool = True,
    ) -> dict[str, object]:
        raise self._unsupported_action("set_group_admin")

    async def set_group_ban(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        duration: int | float = 0,
    ) -> dict[str, object]:
        raise self._unsupported_action("set_group_ban")

    async def set_group_card(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        card: str | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("set_group_card")

    async def kick_group_member(
        self,
        *,
        group_id: str | int,
        user_id: str | int,
        reject_add_request: bool | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("kick_group_member")

    async def kick_group_members(
        self,
        *,
        group_id: str | int,
        user_ids: list[str | int],
        reject_add_request: bool | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("kick_group_members")

    async def leave_group(
        self,
        *,
        group_id: str | int,
        is_dismiss: bool | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("leave_group")

    async def set_group_whole_ban(
        self,
        *,
        group_id: str | int,
        enable: bool = True,
    ) -> dict[str, object]:
        raise self._unsupported_action("set_group_whole_ban")

    async def set_essence_message(
        self,
        *,
        message_id: str | int | float,
    ) -> dict[str, object]:
        raise self._unsupported_action("set_essence_message")

    async def delete_essence_message(
        self,
        *,
        message_id: str | int | float | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: str | int | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("delete_essence_message")

    async def send_group_notice(
        self,
        *,
        group_id: str | int,
        content: str,
        pinned: int | float | None = None,
        type_: int | float | None = None,
        confirm_required: int | float | None = None,
        is_show_edit_card: int | float | None = None,
        tip_window_type: int | float | None = None,
        image: str | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("send_group_notice")

    async def send_like(
        self,
        *,
        user_id: str | int,
        times: int | float = 1,
    ) -> dict[str, object]:
        raise self._unsupported_action("send_like")

    async def send_poke(
        self,
        *,
        user_id: str | int,
        group_id: str | int | None = None,
        target_id: str | int | None = None,
    ) -> dict[str, object]:
        raise self._unsupported_action("send_poke")

    async def webhook_callback(self, request: Any) -> Any:
        """统一 Webhook 回调入口。

        支持统一 Webhook 模式的平台需要实现此方法。
        当 Dashboard 收到 /api/v1/webhooks/platforms/{uuid} 请求时，会调用此方法。

        Args:
            request: webhook 请求对象

        Returns:
            响应内容，格式取决于具体平台的要求

        Raises:
            NotImplementedError: 平台未实现统一 Webhook 模式
        """
        raise NotImplementedError(f"平台 {self.meta().name} 未实现统一 Webhook 模式")
