from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from astrbot import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.log import LogBroker
from astrbot.core.utils.error_redaction import safe_error
from astrbot.dashboard.responses import ApiError, error
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.appearance_service import AppearanceService
from astrbot.dashboard.services.auth_service import (
    DASHBOARD_JWT_COOKIE_NAME,
    AuthService,
    DashboardTokenValidator,
)
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
from astrbot.dashboard.services.plugin_dashboard_service import PluginDashboardService
from astrbot.dashboard.services.plugin_file_ticket_service import (
    PluginFileTicketService,
)
from astrbot.dashboard.services.plugin_page_session_service import (
    PluginPageSessionService,
)
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

from .plugin_files import router as plugin_files_router
from .plugin_page_assets import router as plugin_page_assets_router
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
    dashboard_core = require_dashboard_core(core_lifecycle)
    app.state.core_lifecycle = dashboard_core
    app.state.db = db
    app.state.jwt_secret = jwt_secret
    dashboard_token_validator = DashboardTokenValidator(jwt_secret)
    app.state.dashboard_token_validator = dashboard_token_validator
    app.state.dashboard_static_folder = static_folder
    app.state.dashboard_config = {}
    app.state.dashboard_testing = False
    log_broker = getattr(core_lifecycle, "log_broker", None) or LogBroker()
    extension_registry = dashboard_core.plugin_manager.dashboard_extension_registry
    plugin_page_sessions = PluginPageSessionService(extension_registry, jwt_secret)
    plugin_file_tickets = PluginFileTicketService(extension_registry, jwt_secret)
    plugin_dashboard = PluginDashboardService(
        extension_registry,
        plugin_page_sessions,
        plugin_file_tickets,
    )
    app.state.services = SimpleNamespace(
        appearance=AppearanceService(),
        config_profiles=ConfigProfileService(dashboard_core, db),
        config_display=ConfigDisplayService(dashboard_core),
        config_files=ConfigFileService(dashboard_core),
        config_routes=ConfigRoutingService(dashboard_core),
        api_keys=ApiKeyService(db),
        auth=AuthService(
            db,
            dashboard_core.astrbot_config,
            demo_mode=dashboard_core.services.demo_mode,
            token_validator=dashboard_token_validator,
        ),
        backups=BackupService(
            db,
            core_lifecycle,
            token_validator=dashboard_token_validator,
        ),
        chat=ChatService(db, dashboard_core),
        chat_projects=ChatUIProjectService(db),
        commands=CommandService(dashboard_core.astrbot_config, core_lifecycle),
        conversations=ConversationService(db, dashboard_core),
        cron=CronService(core_lifecycle),
        files=FileService(dashboard_core.services.file_token_service),
        knowledge_bases=KnowledgeBaseService(dashboard_core),
        memory=MemoryService(db, core_lifecycle),
        live_chat=LiveChatService(
            db,
            dashboard_core,
            token_validator=dashboard_token_validator,
        ),
        logs=LogService(log_broker, dashboard_core.astrbot_config),
        bots=BotConfigService(dashboard_core),
        platforms=PlatformService(dashboard_core),
        providers=ProviderConfigService(dashboard_core),
        personas=PersonaService(dashboard_core),
        plugin_dashboard=plugin_dashboard,
        plugin_page_sessions=plugin_page_sessions,
        plugin_file_tickets=plugin_file_tickets,
        plugins=PluginService(dashboard_core, dashboard_core.plugin_manager),
        open_api=OpenApiService(db, dashboard_core),
        sessions=SessionManagementService(dashboard_core, db),
        skills=SkillsService(dashboard_core),
        stats=StatService(db, dashboard_core, dashboard_core.astrbot_config),
        subagents=SubAgentService(dashboard_core),
        t2i=T2iService(dashboard_core),
        tools=ToolsService(dashboard_core),
        updates=UpdateService(
            core_lifecycle.astrbot_updator,
            core_lifecycle,
            download_dashboard_func=call_download_dashboard,
            extract_dashboard_func=call_extract_dashboard,
            get_dashboard_version_func=call_get_dashboard_version,
            pip_install_func=lambda *args, **kwargs: call_pip_install(
                dashboard_core.services.pip_installer, *args, **kwargs
            ),
            demo_mode=dashboard_core.services.demo_mode,
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

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, str):
            return JSONResponse(
                error(exc.detail),
                status_code=exc.status_code,
                headers=exc.headers,
            )
        return JSONResponse(
            error("Request failed"),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ):
        return JSONResponse(error("Invalid request payload"), status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        logger.error("Unhandled dashboard API exception: %s", safe_error("", exc))
        return JSONResponse(error("Internal server error"), status_code=500)

    app.include_router(build_api_router())
    app.include_router(plugin_page_assets_router)
    app.include_router(plugin_files_router)
    app.include_router(static_files_router)

    def dashboard_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        security_schemes = schema.setdefault("components", {}).setdefault(
            "securitySchemes",
            {},
        )
        security_schemes["DashboardBearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Dashboard session JWT",
        }
        security_schemes["DashboardCookieAuth"] = {
            "type": "apiKey",
            "in": "cookie",
            "name": DASHBOARD_JWT_COOKIE_NAME,
        }
        app.openapi_schema = schema
        return schema

    app.openapi = dashboard_openapi

    async def shutdown_plugin_dashboard_services() -> None:
        await plugin_page_sessions.shutdown()
        await plugin_file_tickets.shutdown()

    app.router.add_event_handler("shutdown", shutdown_plugin_dashboard_services)
    return app
