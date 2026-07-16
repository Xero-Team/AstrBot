"""Non-optional lifecycle view used after dashboard startup completes."""

from __future__ import annotations

from typing import Protocol, cast

from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.cron import CronJobManager
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.memory import MemoryManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.runtime_services import RuntimeServices
from astrbot.core.star.context import Context
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.umop_config_router import UmopConfigRouter


class DashboardCoreLifecycle(Protocol):
    """Lifecycle capabilities guaranteed before dashboard services are created."""

    services: RuntimeServices
    astrbot_config: AstrBotConfig
    astrbot_config_mgr: AstrBotConfigManager
    persona_mgr: PersonaManager
    provider_manager: ProviderManager
    platform_manager: PlatformManager
    conversation_manager: ConversationManager
    platform_message_history_manager: PlatformMessageHistoryManager
    kb_manager: KnowledgeBaseManager
    memory_manager: MemoryManager
    star_context: Context
    plugin_manager: PluginManager
    cron_manager: CronJobManager
    umop_config_router: UmopConfigRouter
    pipeline_scheduler_mapping: dict[str, PipelineScheduler]
    start_time: int

    async def reload_pipeline_scheduler(self, conf_id: str) -> None: ...

    async def restart(self) -> None: ...


def require_dashboard_core(
    core_lifecycle: AstrBotCoreLifecycle,
) -> DashboardCoreLifecycle:
    """Expose the initialized lifecycle capabilities used by dashboard services.

    Runtime startup creates dashboard services after the lifecycle has initialized.
    Lightweight ASGI users can still expose routes that do not touch every
    lifecycle component, so initialization is deliberately checked by the
    service that consumes a component rather than when the app is assembled.
    """
    return cast(DashboardCoreLifecycle, core_lifecycle)
