"""Application-level supervision for the core lifecycle and Dashboard."""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable

from astrbot import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.log import LogBroker
from astrbot.core.runtime_services import RuntimeServices
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error
from astrbot.core.utils.task_utils import await_first_terminal_task
from astrbot.dashboard.server import AstrBotDashboard


class InitialLoader:
    """Start one initialized core runtime and supervise its process tasks."""

    def __init__(
        self,
        services: RuntimeServices,
        log_broker: LogBroker,
        *,
        webui_dir: str | None = None,
    ) -> None:
        self.services = services
        self.logger = logger
        self.log_broker = log_broker
        self.webui_dir = webui_dir
        self.core_lifecycle: AstrBotCoreLifecycle | None = None
        self.dashboard_server: AstrBotDashboard | None = None

    async def _stop_lifecycle(self, lifecycle: AstrBotCoreLifecycle) -> None:
        """Stop once without hiding the task failure that triggered shutdown."""
        try:
            await lifecycle.stop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Failed to stop AstrBot core: %s", safe_error("", exc))

    @staticmethod
    async def _wait_for_runtime_tasks(tasks: list[asyncio.Task[None]]) -> None:
        """Wait until a runtime task completes or surface its failure."""
        await await_first_terminal_task(tasks)

    @staticmethod
    async def _cancel_and_join(tasks: list[asyncio.Task[None]]) -> None:
        """Cancel unfinished sibling tasks and wait for them to settle."""
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start(self) -> None:
        """Initialize and supervise the core and Dashboard for this process."""
        lifecycle = AstrBotCoreLifecycle(self.log_broker, self.services)
        self.core_lifecycle = lifecycle
        tasks: list[asyncio.Task[None]] = []

        try:
            try:
                await lifecycle.initialize()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.critical(redact_sensitive_text(traceback.format_exc()))
                logger.critical("😭 初始化 AstrBot 失败：%s !!!", safe_error("", exc))
                raise

            runtime = lifecycle.runtime
            self.dashboard_server = await AstrBotDashboard.create(
                runtime,
                lifecycle,
                self.services.db,
                runtime.dashboard_shutdown_event,
                self.webui_dir,
            )
            core_task = asyncio.create_task(
                lifecycle.start(),
                name="astrbot-core",
            )
            tasks.append(core_task)
            dashboard_coro: Awaitable[None] | None = self.dashboard_server.run()
            if dashboard_coro is not None:
                tasks.append(
                    asyncio.create_task(
                        dashboard_coro,
                        name="astrbot-dashboard",
                    )
                )
            await self._wait_for_runtime_tasks(tasks)
        finally:
            await self._cancel_and_join(tasks)
            await self._stop_lifecycle(lifecycle)
