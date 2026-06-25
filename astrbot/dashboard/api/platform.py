from typing import Any

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.asgi_runtime import DashboardRequest
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import BotRegistrationRequest
from astrbot.dashboard.services.platform_service import (
    PlatformService,
    PlatformServiceError,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Platforms"])


def get_service(request: Request) -> PlatformService:
    return request.app.state.services.platforms


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


def _raise_platform_error(exc: PlatformServiceError) -> None:
    raise ApiError(str(exc), status_code=exc.status_code) from exc


def _model_dict(payload) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        return ok(result)
    except PlatformServiceError as exc:
        _raise_platform_error(exc)


@router.post("/bot-types/{bot_type}/registration")
async def register_bot_type(
    bot_type: str,
    payload: BotRegistrationRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: PlatformService = Depends(get_service),
):
    return await _run(
        lambda: service.handle_platform_registration(bot_type, _model_dict(payload))
    )


@router.get("/webhooks/platforms/{webhook_uuid}")
async def verify_platform_webhook(
    webhook_uuid: str,
    request: Request,
    service: PlatformService = Depends(get_service),
):
    return await _run(
        lambda: service.handle_webhook_callback(webhook_uuid, DashboardRequest(request))
    )


@router.post("/webhooks/platforms/{webhook_uuid}")
async def receive_platform_webhook(
    webhook_uuid: str,
    request: Request,
    service: PlatformService = Depends(get_service),
):
    return await _run(
        lambda: service.handle_webhook_callback(webhook_uuid, DashboardRequest(request))
    )
