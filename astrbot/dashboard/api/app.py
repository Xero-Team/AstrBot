from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.log import LogBroker
from astrbot.dashboard.responses import ApiError, error
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import AuthService
from astrbot.dashboard.services.backup_service import BackupService
from astrbot.dashboard.services.chat_service import ChatService
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService
from astrbot.dashboard.services.command_service import CommandService
from astrbot.dashboard.services.config_service import (
    BotConfigService,
    ConfigDisplayService,
    ConfigFileService,
    ConfigProfileService,
    ConfigRoutingService,
    ProviderConfigService,
)
from astrbot.dashboard.services.conversation_service import ConversationService
from astrbot.dashboard.services.core_lifecycle import require_dashboard_core
from astrbot.dashboard.services.cron_service import CronService
from astrbot.dashboard.services.file_service import FileService
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService
from astrbot.dashboard.services.live_chat_service import LiveChatService
from astrbot.dashboard.services.log_service import LogService
from astrbot.dashboard.services.memory_service import MemoryService
from astrbot.dashboard.services.open_api_service import OpenApiService
from astrbot.dashboard.services.persona_service import PersonaService
from astrbot.dashboard.services.platform_service import PlatformService
from astrbot.dashboard.services.plugin_service import PluginService
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)
from astrbot.dashboard.services.skills_service import SkillsService
from astrbot.dashboard.services.stat_service import StatService
from astrbot.dashboard.services.subagent_service import SubAgentService
from astrbot.dashboard.services.t2i_service import T2iService
from astrbot.dashboard.services.tools_service import ToolsService
from astrbot.dashboard.services.update_service import (
    UpdateService,
    call_download_dashboard,
    call_extract_dashboard,
    call_get_dashboard_version,
    call_pip_install,
)

from .public_routes import router as public_routes_router
from .router import API_V1_PREFIX, build_api_router
from .static_files import router as static_files_router

CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


def create_dashboard_asgi_app(
    *,
    core_lifecycle: AstrBotCoreLifecycle,
    db: BaseDatabase,
    jwt_secret: str,
    static_folder: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AstrBot OpenAPI",
        version="1.0.0",
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs",
        redoc_url=f"{API_V1_PREFIX}/redoc",
    )
    core_lifecycle = require_dashboard_core(core_lifecycle)
    app.state.core_lifecycle = core_lifecycle
    app.state.db = db
    app.state.jwt_secret = jwt_secret
    app.state.dashboard_static_folder = static_folder
    app.state.dashboard_config = {}
    app.state.dashboard_testing = False
    log_broker = getattr(core_lifecycle, "log_broker", None) or LogBroker()
    app.state.services = SimpleNamespace(
        config_profiles=ConfigProfileService(core_lifecycle, db),
        config_display=ConfigDisplayService(core_lifecycle),
        config_files=ConfigFileService(core_lifecycle),
        config_routes=ConfigRoutingService(core_lifecycle),
        api_keys=ApiKeyService(db),
        auth=AuthService(
            db,
            core_lifecycle.astrbot_config,
            demo_mode=core_lifecycle.services.demo_mode,
        ),
        backups=BackupService(db, core_lifecycle),
        chat=ChatService(db, core_lifecycle),
        chat_projects=ChatUIProjectService(db),
        commands=CommandService(core_lifecycle.astrbot_config, core_lifecycle),
        conversations=ConversationService(db, core_lifecycle),
        cron=CronService(core_lifecycle),
        files=FileService(core_lifecycle.services.file_token_service),
        knowledge_bases=KnowledgeBaseService(core_lifecycle),
        memory=MemoryService(db, core_lifecycle),
        live_chat=LiveChatService(db, core_lifecycle),
        logs=LogService(log_broker, core_lifecycle.astrbot_config),
        bots=BotConfigService(core_lifecycle),
        platforms=PlatformService(core_lifecycle),
        providers=ProviderConfigService(core_lifecycle),
        personas=PersonaService(core_lifecycle),
        plugins=PluginService(core_lifecycle, core_lifecycle.plugin_manager),
        open_api=OpenApiService(db, core_lifecycle),
        sessions=SessionManagementService(core_lifecycle, db),
        skills=SkillsService(core_lifecycle),
        stats=StatService(db, core_lifecycle, core_lifecycle.astrbot_config),
        subagents=SubAgentService(core_lifecycle),
        t2i=T2iService(core_lifecycle),
        tools=ToolsService(core_lifecycle),
        updates=UpdateService(
            core_lifecycle.astrbot_updator,
            core_lifecycle,
            download_dashboard_func=call_download_dashboard,
            extract_dashboard_func=call_extract_dashboard,
            get_dashboard_version_func=call_get_dashboard_version,
            pip_install_func=lambda *args, **kwargs: call_pip_install(
                core_lifecycle.services.pip_installer, *args, **kwargs
            ),
            demo_mode=core_lifecycle.services.demo_mode,
            clear_site_data_headers=CLEAR_SITE_DATA_HEADERS,
        ),
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(
            error(exc.message, exc.data),
            status_code=exc.status_code,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(error(str(exc)), status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(error(detail), status_code=exc.status_code)

    app.include_router(build_api_router())
    app.include_router(public_routes_router)
    app.include_router(static_files_router)
    return app
