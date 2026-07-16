"""AstrBot 启动器，负责初始化和启动核心组件和仪表板服务器。

工作流程:
1. 初始化核心生命周期, 传递数据库和日志代理实例到核心生命周期
2. 运行核心生命周期任务和仪表板服务器
"""

import asyncio
import traceback

from astrbot import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.log import LogBroker
from astrbot.core.runtime_services import RuntimeServices
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error
from astrbot.dashboard.server import AstrBotDashboard


class InitialLoader:
    """AstrBot 启动器，负责初始化和启动核心组件和仪表板服务器。"""

    def __init__(self, services: RuntimeServices, log_broker: LogBroker) -> None:
        self.services = services
        self.logger = logger
        self.log_broker = log_broker
        self.webui_dir: str | None = None

    async def start(self) -> None:
        core_lifecycle = AstrBotCoreLifecycle(self.log_broker, self.services)

        try:
            await core_lifecycle.initialize()
        except Exception as e:
            await core_lifecycle.stop()
            logger.critical(redact_sensitive_text(traceback.format_exc()))
            logger.critical("😭 初始化 AstrBot 失败：%s !!!", safe_error("", e))
            return

        core_task = core_lifecycle.start()

        webui_dir = self.webui_dir

        self.dashboard_server = AstrBotDashboard(
            core_lifecycle,
            self.services.db,
            core_lifecycle.dashboard_shutdown_event,
            webui_dir,
        )

        coro = self.dashboard_server.run()
        if coro:
            # 启动核心任务和仪表板服务器
            task = asyncio.gather(core_task, coro)
        else:
            task = core_task
        try:
            await task  # 整个AstrBot在这里运行
        except asyncio.CancelledError:
            logger.info("🌈 正在关闭 AstrBot...")
            await core_lifecycle.stop()
            raise
