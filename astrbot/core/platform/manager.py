import asyncio
import traceback
from asyncio import Queue
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.star_handler import EventType, star_handlers_registry, star_map
from astrbot.core.utils.webhook_utils import (
    configure_webhook_utils,
    ensure_platform_webhook_config,
)

from .astrbot_message import AstrBotMessage
from .discovery import discover_platform_adapter
from .message_session import MessageSession
from .platform import Platform, PlatformStatus
from .send_result import PlatformSendResult


@dataclass
class PlatformTasks:
    run: asyncio.Task
    wrapper: asyncio.Task


_T = TypeVar("_T")


class PlatformManager:
    def __init__(self, config: AstrBotConfig, event_queue: Queue) -> None:
        configure_webhook_utils(config)
        self._platform_insts: list[Platform] = []
        """加载的 Platform 的实例"""

        self._inst_map: dict[str, dict] = {}
        self._platform_tasks: dict[str, PlatformTasks] = {}
        self._platform_limiters: dict[str, asyncio.Semaphore] = {}
        self._platform_limit_settings: dict[str, int] = {}
        # Keep an old shutdown from cancelling a replacement with the same client ID.
        self._platform_lifecycle_lock = asyncio.Lock()

        self.astrbot_config = config
        self.platforms_config = config["platform"]
        self.settings = config["platform_settings"]
        """NOTE: 这里是 default 的配置文件，以保证最大的兼容性；
        这个配置中的 unique_session 需要特殊处理，
        约定整个项目中对 unique_session 的引用都从 default 的配置中获取"""
        self.event_queue = event_queue

    def _is_valid_platform_id(self, platform_id: str | None) -> bool:
        if not platform_id:
            return False
        return ":" not in platform_id and "!" not in platform_id

    def _sanitize_platform_id(self, platform_id: str | None) -> tuple[str | None, bool]:
        if not platform_id:
            return platform_id, False
        sanitized = platform_id.replace(":", "_").replace("!", "_")
        return sanitized, sanitized != platform_id

    def _start_platform_task(self, task_name: str, inst: Platform) -> None:
        run_task = asyncio.create_task(inst.run(), name=task_name)
        wrapper_task = asyncio.create_task(
            self._task_wrapper(run_task, platform=inst),
            name=f"{task_name}_wrapper",
        )
        self._platform_tasks[inst.client_self_id] = PlatformTasks(
            run=run_task,
            wrapper=wrapper_task,
        )

    async def _stop_platform_task(self, client_id: str) -> None:
        tasks = self._platform_tasks.pop(client_id, None)
        if not tasks:
            return
        for task in (tasks.run, tasks.wrapper):
            if not task.done():
                task.cancel()
        await asyncio.gather(tasks.run, tasks.wrapper, return_exceptions=True)

    async def _terminate_inst_and_tasks(self, inst: Platform) -> None:
        client_id = inst.client_self_id
        try:
            if getattr(inst, "terminate", None):
                try:
                    await inst.terminate()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        "终止平台适配器失败: client_id=%s, error=%s",
                        client_id,
                        e,
                    )
                    logger.error(traceback.format_exc())
        finally:
            await self._stop_platform_task(client_id)

    def set_platform_concurrency_limit(
        self, platform_id: str, limit: int | None
    ) -> None:
        if limit is None:
            self._platform_limiters.pop(platform_id, None)
            self._platform_limit_settings.pop(platform_id, None)
            return
        if limit < 1:
            raise ValueError("platform concurrency limit must be >= 1")
        self._platform_limiters[platform_id] = asyncio.Semaphore(limit)
        self._platform_limit_settings[platform_id] = limit

    def get_platform_concurrency_limit(self, platform_id: str) -> int | None:
        return self._platform_limit_settings.get(platform_id)

    async def run_with_platform_limit(
        self,
        platform_id: str,
        operation: Callable[[], Awaitable[_T]],
    ) -> _T:
        limiter = self._platform_limiters.get(platform_id)
        if limiter is None:
            return await operation()
        async with limiter:
            return await operation()

    async def initialize(self) -> None:
        """初始化所有平台适配器"""
        for platform in self.platforms_config:
            try:
                if ensure_platform_webhook_config(platform):
                    self.astrbot_config.save_config()
                await self.load_platform(platform)
            except Exception as e:
                logger.error(f"初始化 {platform} 平台适配器失败: {e}")

        # 网页聊天 is built-in but follows the same lazy discovery boundary.
        webchat_cls = discover_platform_adapter("webchat")
        if webchat_cls is None:
            raise RuntimeError("Built-in webchat platform adapter was not registered")
        webchat_inst = webchat_cls({}, self.settings, self.event_queue)
        self._platform_insts.append(webchat_inst)
        self._start_platform_task("webchat", webchat_inst)

    async def load_platform(self, platform_config: dict) -> None:
        """实例化一个平台"""
        async with self._platform_lifecycle_lock:
            await self._load_platform_unlocked(platform_config)

    async def _load_platform_unlocked(self, platform_config: dict) -> None:
        # 动态导入
        cls_type: type | None = None
        try:
            if not platform_config["enable"]:
                return
            platform_id = platform_config.get("id")
            if not self._is_valid_platform_id(platform_id):
                sanitized_id, changed = self._sanitize_platform_id(platform_id)
                if sanitized_id and changed:
                    logger.warning(
                        "平台 ID %r 包含非法字符 ':' 或 '!'，已替换为 %r。",
                        platform_id,
                        sanitized_id,
                    )
                    platform_config["id"] = sanitized_id
                    self.astrbot_config.save_config()
                else:
                    logger.error(
                        f"平台 ID {platform_id!r} 不能为空，跳过加载该平台适配器。",
                    )
                    return

            logger.info(
                "Loading IM platform adapter %s(%s) ...",
                platform_config["type"],
                platform_config["id"],
            )
            cls_type = discover_platform_adapter(platform_config["type"])
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(
                f"加载平台适配器 {platform_config['type']} 失败，原因：{e}。请检查依赖库是否安装。提示：可以在 管理面板->平台日志->安装Pip库 中安装依赖库。",
            )
        except Exception as e:
            logger.error(f"加载平台适配器 {platform_config['type']} 失败，原因：{e}。")

        if cls_type is None:
            logger.error(
                f"Platform adapter not found: {platform_config['type']}({platform_config['id']}).",
            )
            return
        inst: Platform = cls_type(platform_config, self.settings, self.event_queue)
        inst.database = getattr(self, "database", None)
        inst.runtime_config = self.astrbot_config
        inst.preferences = getattr(self, "preferences", None)
        self._inst_map[platform_config["id"]] = {
            "inst": inst,
            "client_id": inst.client_self_id,
        }
        self._platform_insts.append(inst)
        self._start_platform_task(
            f"platform_{platform_config['type']}_{platform_config['id']}",
            inst,
        )
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnPlatformLoadedEvent,
        )
        for handler in handlers:
            try:
                logger.info(
                    f"hook(on_platform_loaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
                )
                await handler.handler()
            except Exception:
                logger.error(traceback.format_exc())

    async def _task_wrapper(
        self, task: asyncio.Task, platform: Platform | None = None
    ) -> None:
        # 设置平台状态为运行中
        if platform:
            platform.status = PlatformStatus.RUNNING

        try:
            await task
        except asyncio.CancelledError:
            if platform:
                platform.status = PlatformStatus.STOPPED
        except Exception as e:
            error_msg = str(e)
            tb_str = traceback.format_exc()
            logger.error(f"------- 任务 {task.get_name()} 发生错误: {e}")
            for line in tb_str.split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

            # 记录错误到平台实例
            if platform:
                platform.record_error(error_msg, tb_str)

    async def reload(self, platform_config: dict) -> None:
        async with self._platform_lifecycle_lock:
            await self._terminate_platform_unlocked(platform_config["id"])
            if platform_config["enable"]:
                await self._load_platform_unlocked(platform_config)

            # 和配置文件保持同步
            config_ids = [provider["id"] for provider in self.platforms_config]
            for key in list(self._inst_map.keys()):
                if key not in config_ids:
                    await self._terminate_platform_unlocked(key)

    async def terminate_platform(self, platform_id: str) -> None:
        async with self._platform_lifecycle_lock:
            await self._terminate_platform_unlocked(platform_id)

    async def _terminate_platform_unlocked(self, platform_id: str) -> None:
        self._platform_limiters.pop(platform_id, None)
        self._platform_limit_settings.pop(platform_id, None)
        if platform_id in self._inst_map:
            logger.info(f"正在尝试终止 {platform_id} 平台适配器 ...")

            # client_id = self._inst_map.pop(platform_id, None)
            info = self._inst_map.pop(platform_id)
            client_id = info["client_id"]
            inst: Platform = info["inst"]
            try:
                self._platform_insts.remove(
                    next(
                        inst
                        for inst in self._platform_insts
                        if inst.client_self_id == client_id
                    ),
                )
            except Exception:
                logger.warning(f"可能未完全移除 {platform_id} 平台适配器")

            await self._terminate_inst_and_tasks(inst)

    async def terminate(self) -> None:
        terminated_client_ids: set[str] = set()
        for platform_id in list(self._inst_map.keys()):
            info = self._inst_map.get(platform_id)
            if info:
                terminated_client_ids.add(info["client_id"])
            await self.terminate_platform(platform_id)

        for inst in list(self._platform_insts):
            client_id = inst.client_self_id
            if client_id in terminated_client_ids:
                continue
            await self._terminate_inst_and_tasks(inst)

        self._platform_insts.clear()
        self._inst_map.clear()
        self._platform_tasks.clear()
        self._platform_limiters.clear()
        self._platform_limit_settings.clear()

    def get_platform_count(self) -> int:
        return len(self._platform_insts)

    def _find_inst_by_id(self, platform_id: str) -> Platform | None:
        info = self._inst_map.get(platform_id)
        if info:
            inst = info.get("inst")
            if isinstance(inst, Platform):
                return inst

        for inst in self._platform_insts:
            if inst.meta().id == platform_id or inst.config.get("id") == platform_id:
                return inst
        return None

    def _find_inst_by_name(self, platform_name: str) -> Platform | None:
        for inst in self._platform_insts:
            if inst.meta().name == platform_name:
                return inst
        return None

    def find_inst_by_webhook_uuid(self, webhook_uuid: str) -> Platform | None:
        for inst in self._platform_insts:
            if (
                inst.config.get("webhook_uuid") == webhook_uuid
                and inst.unified_webhook()
            ):
                return inst
        return None

    async def send_to_session(
        self,
        session: MessageSession,
        message_chain,
    ) -> PlatformSendResult:
        inst = self._find_inst_by_id(session.platform_id)
        if inst is None:
            return PlatformSendResult(
                platform_id=session.platform_id,
                success=False,
                target=session.session_id,
                message_count=len(message_chain.chain),
                error_message="platform adapter not found",
            )
        try:
            result = await self.run_with_platform_limit(
                session.platform_id,
                lambda: inst.send_by_session(session, message_chain),
            )
        except Exception as exc:
            return PlatformSendResult(
                platform_id=session.platform_id,
                success=False,
                target=session.session_id,
                message_count=len(message_chain.chain),
                error_message=str(exc),
            )
        if isinstance(result, PlatformSendResult):
            return result
        return PlatformSendResult(
            platform_id=session.platform_id,
            success=True,
            target=session.session_id,
            message_count=len(message_chain.chain),
        )

    async def invoke_action(
        self,
        platform_id: str,
        action_name: str,
        **kwargs,
    ) -> dict[str, object]:
        inst = self._find_inst_by_id(platform_id)
        if inst is None:
            raise LookupError(f"Platform adapter not found: {platform_id}")
        if not inst.supports_action(action_name):
            raise NotImplementedError(
                f"Platform {platform_id} does not support action `{action_name}`"
            )

        method = getattr(inst, action_name, None)
        if method is None or not callable(method):
            raise NotImplementedError(
                f"Platform {platform_id} action handler missing: `{action_name}`"
            )
        action_handler = cast(Callable[..., Awaitable[dict[str, object]]], method)
        return await self.run_with_platform_limit(
            platform_id,
            lambda: action_handler(**kwargs),
        )

    def create_event(
        self,
        platform: str,
        event_message: object,
        *,
        is_wake: bool = True,
    ) -> None:
        inst = self._find_inst_by_id(platform)
        if inst is None:
            inst = self._find_inst_by_name(platform)
        if inst is None:
            raise ValueError(f"Platform not found: {platform}")

        event = inst.create_event(cast(AstrBotMessage, event_message))
        event.is_wake = is_wake
        inst.commit_event(event)

    def get_all_stats(self) -> dict:
        """获取所有平台的统计信息

        Returns:
            包含所有平台统计信息的字典
        """
        stats_list = []
        total_errors = 0
        running_count = 0
        error_count = 0

        for inst in self._platform_insts:
            try:
                stat = inst.get_stats()
                stats_list.append(stat)
                total_errors += stat.get("error_count", 0)
                if stat.get("status") == PlatformStatus.RUNNING.value:
                    running_count += 1
                elif stat.get("status") == PlatformStatus.ERROR.value:
                    error_count += 1
            except Exception as e:
                # 如果获取统计信息失败，记录基本信息
                logger.warning(f"获取平台统计信息失败: {e}")
                stats_list.append(
                    {
                        "id": getattr(inst, "config", {}).get("id", "unknown"),
                        "type": "unknown",
                        "status": "unknown",
                        "error_count": 0,
                        "last_error": None,
                    }
                )

        return {
            "platforms": stats_list,
            "summary": {
                "total": len(stats_list),
                "running": running_count,
                "error": error_count,
                "total_errors": total_errors,
            },
        }
