from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from astrbot.core.platform.webhook_server import (
    WebhookRequest,
    webhook_response_from_result,
)
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    BotRegistrationRequest,
    model_dict,
)
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


async def _run(operation):
    try:
        result = await run_maybe_async(operation)
        if isinstance(result, Response):
            return result
        return ok(result)
    except PlatformServiceError as exc:
        _raise_platform_error(exc)


async def _run_webhook(operation):
    """Run a platform webhook callback and preserve the platform response.

    Args:
        operation: Callback operation returning a platform-specific response.

    Returns:
        Raw FastAPI response compatible with third-party webhook protocols.
    """
    try:
        result = await run_maybe_async(operation)
    except PlatformServiceError as exc:
        return webhook_response_from_result(({"error": str(exc)}, exc.status_code))

    return webhook_response_from_result(result)


@router.post("/bot-types/{bot_type}/registration")
async def register_bot_type(
    bot_type: str,
    payload: BotRegistrationRequest,
    _auth: AuthContext = Depends(require_config_scope),
    service: PlatformService = Depends(get_service),
):
    return await _run(
        lambda: service.handle_platform_registration(bot_type, model_dict(payload))
    )


@router.get("/webhooks/platforms/{webhook_uuid}")
async def verify_platform_webhook(
    webhook_uuid: str,
    request: Request,
    service: PlatformService = Depends(get_service),
):
    return await _run_webhook(
        lambda: service.handle_webhook_callback(webhook_uuid, WebhookRequest(request))
    )


@router.post("/webhooks/platforms/{webhook_uuid}")
async def receive_platform_webhook(
    webhook_uuid: str,
    request: Request,
    service: PlatformService = Depends(get_service),
):
    return await _run_webhook(
        lambda: service.handle_webhook_callback(webhook_uuid, WebhookRequest(request))
    )
