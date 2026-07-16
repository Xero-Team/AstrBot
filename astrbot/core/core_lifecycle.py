"""Astrbot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作.

该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus等。
该类还负责加载和执行插件, 以及处理事件总线的分发。

工作流程:
1. 初始化所有组件
2. 启动事件总线和任务, 所有任务都在这里运行
3. 执行启动完成事件钩子
"""

import asyncio
import os
import threading
import time
import traceback
from asyncio import Queue
from collections.abc import Awaitable, Callable

from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.default import VERSION
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron import CronJobManager
from astrbot.core.db import BaseDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.log import LogBroker, LogManager
from astrbot.core.memory import MemoryManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.persona_runtime import PersonaRuntimeManager
from astrbot.core.pipeline.scheduler import PipelineContext, PipelineScheduler
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.runtime_services import RuntimeServices
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType, star_handlers_registry, star_map
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.updator import AstrBotUpdator
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.event_loop_diagnostics import (
    create_event_loop_diagnostic_tasks,
)
from astrbot.core.utils.llm_metadata import update_llm_metadata
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.task_utils import cancel_tracked_tasks, create_tracked_task
from astrbot.core.utils.temp_dir_cleaner import TempDirCleaner
from astrbot.core.utils.trace import configure_trace

from .event_bus import EventBus

EVENT_QUEUE_MAXSIZE = 1024


class AstrBotCoreLifecycle:
    """AstrBot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作.

    该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、
    EventBus 等。
    该类还负责加载和执行插件, 以及处理事件总线的分发。
    """

    def __init__(self, log_broker: LogBroker, services: RuntimeServices) -> None:
        self.log_broker = log_broker  # 初始化日志代理
        self.services = services
        self.astrbot_config = services.config
        self.db: BaseDatabase = services.db

        self.subagent_orchestrator: SubAgentOrchestrator | None = None
        self.cron_manager: CronJobManager | None = None
        self.temp_dir_cleaner: TempDirCleaner | None = None
        self.umop_config_router: UmopConfigRouter | None = None
        self.astrbot_config_mgr: AstrBotConfigManager | None = None
        self.persona_mgr: PersonaManager | None = None
        self.persona_runtime_manager: PersonaRuntimeManager | None = None
        self.memory_manager: MemoryManager | None = None
        self.provider_manager: ProviderManager | None = None
        self.platform_manager: PlatformManager | None = None
        self.conversation_manager: ConversationManager | None = None
        self.platform_message_history_manager: PlatformMessageHistoryManager | None = (
            None
        )
        self.kb_manager: KnowledgeBaseManager | None = None
        self.star_context: Context | None = None
        self.plugin_manager: PluginManager | None = None
        self.event_bus: EventBus | None = None
        self.dashboard_shutdown_event: asyncio.Event | None = None
        self.pipeline_scheduler_mapping: dict[str, PipelineScheduler] = {}
        self.curr_tasks: list[asyncio.Task] = []
        self._default_chat_provider_warning_emitted = False
        self._background_tasks: set[asyncio.Task] = set()
        self._stop_lock = asyncio.Lock()
        self._initializing = False
        self._initialized = False
        self._stopped = False
        self._db_initialization_started = False
        self._html_renderer_initialization_started = False
        self._memory_initialization_started = False
        self._plugin_reload_started = False
        self._provider_initialization_started = False
        self._kb_initialization_started = False
        self._platform_initialization_started = False
        self._event_bus_started = False
        self._cron_started = False
        self._temp_dir_cleaner_started = False

        # 设置代理
        proxy_config = self.astrbot_config.get("http_proxy", "")
        if proxy_config != "":
            os.environ["https_proxy"] = proxy_config
            os.environ["http_proxy"] = proxy_config
            logger.debug(f"Using proxy: {proxy_config}")
            # 设置 no_proxy
            no_proxy_list = self.astrbot_config.get("no_proxy", [])
            os.environ["no_proxy"] = ",".join(no_proxy_list)
        else:
            # 清空代理环境变量
            if "https_proxy" in os.environ:
                del os.environ["https_proxy"]
            if "http_proxy" in os.environ:
                del os.environ["http_proxy"]
            if "no_proxy" in os.environ:
                del os.environ["no_proxy"]
            logger.debug("HTTP proxy cleared")

    async def _init_or_reload_subagent_orchestrator(self) -> None:
        """Create (if needed) and reload the subagent orchestrator from config.

        This keeps lifecycle wiring in one place while allowing the orchestrator
        to manage enable/disable and tool registration details.
        """
        try:
            if self.subagent_orchestrator is None:
                self.subagent_orchestrator = SubAgentOrchestrator(
                    self.provider_manager.llm_tools,
                    self.persona_mgr,
                )
            await self.subagent_orchestrator.reload_from_config(
                self.astrbot_config.get("subagent_orchestrator", {}),
            )
        except Exception as e:
            logger.error(
                "Subagent orchestrator init failed: %s",
                safe_error("", e),
            )

    def _warn_about_unset_default_chat_provider(self) -> None:
        if self._default_chat_provider_warning_emitted:
            return

        pm = getattr(self, "provider_manager", None)
        if not pm:
            return

        providers = pm.provider_insts
        if len(providers) == 0:
            return

        provider_settings = getattr(pm, "provider_settings", None) or {}
        default_id = provider_settings.get("default_provider_id")
        fallback = providers[0]
        fallback_id = fallback.provider_config.get("id") or "unknown"

        if not default_id:
            if len(providers) <= 1:
                return
            self._default_chat_provider_warning_emitted = True
            logger.warning(
                "Detected %d enabled chat providers but `provider_settings.default_provider_id` is empty. "
                "AstrBot will use `%s` as the startup fallback chat provider. "
                "Set a default chat model in the WebUI configuration page to avoid unexpected provider switching.",
                len(providers),
                fallback_id,
            )
            return

        found = any((p.provider_config.get("id") == default_id) for p in providers)
        if not found:
            self._default_chat_provider_warning_emitted = True
            logger.warning(
                "Configured `default_provider_id` is `%s` but no enabled provider matches that ID. "
                "AstrBot will use `%s` as the fallback chat provider. "
                "Please check the WebUI configuration page.",
                default_id,
                fallback_id,
            )

    async def initialize(self) -> None:
        """初始化 AstrBot 核心生命周期管理类.

        负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus、AstrBotUpdator等。
        """
        if self._initialized:
            return
        if self._initializing:
            raise RuntimeError(
                "AstrBot core lifecycle initialization is already running"
            )

        self._initializing = True
        try:
            await self._initialize()
        except BaseException:
            await self.stop()
            raise
        finally:
            self._initializing = False
        self._initialized = True

    async def _initialize(self) -> None:
        """Initialize core resources in dependency order."""
        # 初始化日志代理
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            LogManager.configure_logger(
                logger, self.astrbot_config, override_level="DEBUG"
            )
            LogManager.configure_trace_logger(self.astrbot_config)
        else:
            LogManager.configure_logger(logger, self.astrbot_config)
            LogManager.configure_trace_logger(self.astrbot_config)

        self._db_initialization_started = True
        await self.db.initialize()
        Metric.configure(self.astrbot_config, self.db)
        configure_trace(self.astrbot_config)

        self._html_renderer_initialization_started = True
        await self.services.html_renderer.initialize()

        # 初始化 UMOP 配置路由器
        self.umop_config_router = UmopConfigRouter(sp=self.services.preferences)
        await self.umop_config_router.initialize()

        # 初始化 AstrBot 配置管理器
        self.astrbot_config_mgr = AstrBotConfigManager(
            default_config=self.astrbot_config,
            ucr=self.umop_config_router,
            sp=self.services.preferences,
        )
        await self.astrbot_config_mgr.initialize()
        self.temp_dir_cleaner = TempDirCleaner(
            max_size_getter=lambda: self.astrbot_config_mgr.default_conf.get(
                TempDirCleaner.CONFIG_KEY,
                TempDirCleaner.DEFAULT_MAX_SIZE,
            ),
        )

        # 初始化事件队列
        self.event_queue = Queue(maxsize=EVENT_QUEUE_MAXSIZE)

        # 初始化人格管理器
        self.persona_mgr = PersonaManager(
            self.db,
            self.astrbot_config_mgr,
            self.services.preferences,
        )
        await self.persona_mgr.initialize()

        self.persona_runtime_manager = PersonaRuntimeManager(self.db)
        await self.persona_runtime_manager.initialize()

        self.memory_manager = MemoryManager(self.db)
        self._memory_initialization_started = True
        await self.memory_manager.initialize()

        # 初始化供应商管理器
        self.provider_manager = ProviderManager(
            self.astrbot_config_mgr,
            self.db,
            self.persona_mgr,
            self.services.preferences,
        )

        # 初始化平台管理器
        self.platform_manager = PlatformManager(self.astrbot_config, self.event_queue)
        self.platform_manager.database = self.db
        self.platform_manager.preferences = self.services.preferences

        # 初始化对话管理器
        self.conversation_manager = ConversationManager(
            self.db,
            self.services.preferences,
        )

        # 初始化平台消息历史管理器
        self.platform_message_history_manager = PlatformMessageHistoryManager(self.db)

        # 初始化知识库管理器
        self.kb_manager = KnowledgeBaseManager(self.provider_manager)

        # 初始化 CronJob 管理器
        self.cron_manager = CronJobManager(self.db)

        # Dynamic subagents (handoff tools) from config.
        await self._init_or_reload_subagent_orchestrator()

        # 初始化提供给插件的上下文
        self.star_context = Context(
            self.event_queue,
            self.astrbot_config,
            self.db,
            self.provider_manager,
            self.platform_manager,
            self.conversation_manager,
            self.platform_message_history_manager,
            self.persona_mgr,
            self.astrbot_config_mgr,
            self.kb_manager,
            self.cron_manager,
            self.services.preferences,
            self.services.html_renderer,
            self.services.file_token_service,
            self.subagent_orchestrator,
            demo_mode=self.services.demo_mode,
        )
        self.star_context.persona_runtime_manager = self.persona_runtime_manager
        self.star_context.memory_manager = self.memory_manager

        # 初始化插件管理器
        self.plugin_manager = PluginManager(
            self.star_context,
            self.astrbot_config,
            self.services.preferences,
            self.services.pip_installer,
        )

        # 扫描、注册插件、实例化插件类
        self._plugin_reload_started = True
        await self.plugin_manager.reload()

        # 根据配置实例化各个 Provider
        self._default_chat_provider_warning_emitted = False
        self._provider_initialization_started = True
        await self.provider_manager.initialize()
        self._warn_about_unset_default_chat_provider()

        self._kb_initialization_started = True
        await self.kb_manager.initialize()

        # 初始化消息事件流水线调度器
        self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

        # 初始化更新器
        self.astrbot_updator = AstrBotUpdator()

        # 初始化事件总线
        self.event_bus = EventBus(
            self.event_queue,
            self.pipeline_scheduler_mapping,
            self.astrbot_config_mgr,
        )

        # 记录启动时间
        self.start_time = int(time.time())

        # 初始化当前任务列表
        self.curr_tasks: list[asyncio.Task] = []

        # 根据配置实例化各个平台适配器
        self._platform_initialization_started = True
        await self.platform_manager.initialize()

        # 初始化关闭控制面板的事件
        self.dashboard_shutdown_event = asyncio.Event()

        create_tracked_task(
            self._background_tasks,
            update_llm_metadata(),
            name="update_llm_metadata",
        )

    def _load(self) -> None:
        """加载事件总线和任务并初始化."""
        # 创建一个异步任务来执行事件总线的 dispatch() 方法
        # dispatch是一个无限循环的协程, 从事件队列中获取事件并处理
        event_bus_task = asyncio.create_task(
            self.event_bus.dispatch(),
            name="event_bus",
        )
        self._event_bus_started = True
        cron_task = None
        if self.cron_manager:
            cron_task = asyncio.create_task(
                self.cron_manager.start(self.star_context),
                name="cron_manager",
            )
            self._cron_started = True
        temp_dir_cleaner_task = None
        if self.temp_dir_cleaner:
            temp_dir_cleaner_task = asyncio.create_task(
                self.temp_dir_cleaner.run(),
                name="temp_dir_cleaner",
            )
            self._temp_dir_cleaner_started = True
        diagnostic_tasks = create_event_loop_diagnostic_tasks()

        # 把插件中注册的所有协程函数注册到事件总线中并执行
        extra_tasks = []
        for task in self.star_context._register_tasks:
            extra_tasks.append(asyncio.create_task(task, name=task.__name__))  # type: ignore

        tasks_ = [
            event_bus_task,
            *diagnostic_tasks,
            *(extra_tasks if extra_tasks else []),
        ]
        if cron_task:
            tasks_.append(cron_task)
        if temp_dir_cleaner_task:
            tasks_.append(temp_dir_cleaner_task)
        for task in tasks_:
            self.curr_tasks.append(
                asyncio.create_task(self._task_wrapper(task), name=task.get_name()),
            )

        self.start_time = int(time.time())

    async def _task_wrapper(self, task: asyncio.Task) -> None:
        """异步任务包装器, 用于处理异步任务执行中出现的各种异常.

        Args:
            task (asyncio.Task): 要执行的异步任务

        """
        try:
            await task
        except asyncio.CancelledError:
            pass  # 任务被取消, 静默处理
        except Exception as e:
            # 获取完整的异常堆栈信息, 按行分割并记录到日志中
            logger.error(f"------- 任务 {task.get_name()} 发生错误: {e}")
            for line in traceback.format_exc().split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

    async def start(self) -> None:
        """启动 AstrBot 核心生命周期管理类.

        用load加载事件总线和任务并初始化, 执行启动完成事件钩子
        """
        self._load()
        logger.info("AstrBot started.")

        # 执行启动完成事件钩子
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnAstrBotLoadedEvent,
        )
        for handler in handlers:
            try:
                logger.info(
                    f"hook(on_astrbot_loaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
                )
                await handler.handler()
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt, SystemExit:
                raise
            except Exception:
                logger.error(traceback.format_exc())

        # 同时运行curr_tasks中的所有任务
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Stop initialized resources once, including partially initialized state."""

        async with self._stop_lock:
            if self._stopped:
                return

            async def cleanup_once(
                flag_name: str,
                label: str,
                action: Callable[[], Awaitable[None]],
            ) -> None:
                if not getattr(self, flag_name):
                    return
                setattr(self, flag_name, False)
                try:
                    await action()
                except Exception as exc:
                    logger.warning(
                        "Failed to clean up %s: %s",
                        label,
                        safe_error("", exc),
                    )

            tasks = self.curr_tasks
            self.curr_tasks = []
            for task in tasks:
                task.cancel()

            await cleanup_once(
                "_temp_dir_cleaner_started",
                "temporary directory cleaner",
                lambda: self.temp_dir_cleaner.stop(),  # type: ignore[union-attr]
            )
            await cleanup_once(
                "_event_bus_started",
                "event bus",
                lambda: self.event_bus.shutdown(),  # type: ignore[union-attr]
            )
            await cleanup_once(
                "_cron_started",
                "cron manager",
                lambda: self.cron_manager.shutdown(),  # type: ignore[union-attr]
            )

            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.error(
                        "Task %s failed during shutdown: %s",
                        task.get_name(),
                        safe_error("", exc),
                    )

            try:
                await cancel_tracked_tasks(self._background_tasks)
            except Exception as exc:
                logger.warning(
                    "Failed to cancel lifecycle background tasks: %s",
                    safe_error("", exc),
                )

            await cleanup_once(
                "_platform_initialization_started",
                "platform manager",
                lambda: self.platform_manager.terminate(),  # type: ignore[union-attr]
            )
            await cleanup_once(
                "_kb_initialization_started",
                "knowledge base manager",
                lambda: self.kb_manager.terminate(),  # type: ignore[union-attr]
            )
            await cleanup_once(
                "_provider_initialization_started",
                "provider manager",
                lambda: self.provider_manager.terminate(),  # type: ignore[union-attr]
            )

            if self._plugin_reload_started:
                self._plugin_reload_started = False
                plugin_manager = self.plugin_manager
                if plugin_manager is not None:
                    try:
                        plugins = list(plugin_manager.context.get_all_stars())
                    except Exception as exc:
                        logger.warning(
                            "Failed to enumerate plugins during shutdown: %s",
                            safe_error("", exc),
                        )
                        plugins = []
                    for plugin in plugins:
                        try:
                            await plugin_manager._terminate_plugin(plugin)
                        except Exception as exc:
                            logger.warning(
                                "Plugin %s failed to terminate: %s",
                                plugin.name,
                                safe_error("", exc),
                            )

            await cleanup_once(
                "_memory_initialization_started",
                "memory manager",
                lambda: self.memory_manager.terminate(),  # type: ignore[union-attr]
            )
            await cleanup_once(
                "_html_renderer_initialization_started",
                "HTML renderer",
                self.services.html_renderer.terminate,
            )
            await cleanup_once(
                "_db_initialization_started",
                "database",
                self.db.close,
            )

            if self.dashboard_shutdown_event is not None:
                self.dashboard_shutdown_event.set()
            self._initialized = False
            self._stopped = True

    async def restart(self) -> None:
        """重启 AstrBot 核心生命周期管理类, 终止各个管理器并重新加载平台实例"""
        await self.provider_manager.terminate()
        await self.platform_manager.terminate()
        await self.kb_manager.terminate()
        await self.services.html_renderer.terminate()
        self.dashboard_shutdown_event.set()
        threading.Thread(
            target=self.astrbot_updator._reboot,
            name="restart",
            daemon=True,
        ).start()

    async def load_pipeline_scheduler(self) -> dict[str, PipelineScheduler]:
        """加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        mapping = {}
        for conf_id, ab_config in self.astrbot_config_mgr.confs.items():
            scheduler = PipelineScheduler(
                PipelineContext(
                    ab_config,
                    self.plugin_manager,
                    conf_id,
                    self.services.html_renderer,
                    self.services.file_token_service,
                    self.services.preferences,
                ),
            )
            await scheduler.initialize()
            mapping[conf_id] = scheduler
        return mapping

    async def reload_pipeline_scheduler(self, conf_id: str) -> None:
        """重新加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        ab_config = self.astrbot_config_mgr.confs.get(conf_id)
        if not ab_config:
            raise ValueError(f"配置文件 {conf_id} 不存在")
        scheduler = PipelineScheduler(
            PipelineContext(
                ab_config,
                self.plugin_manager,
                conf_id,
                self.services.html_renderer,
                self.services.file_token_service,
                self.services.preferences,
            ),
        )
        await scheduler.initialize()
        self.pipeline_scheduler_mapping[conf_id] = scheduler
