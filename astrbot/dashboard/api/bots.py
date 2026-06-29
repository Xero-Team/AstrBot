from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.responses import ok
from astrbot.dashboard.schemas import BotConfigRequest, EnabledPatch
from astrbot.dashboard.services.config_service import BotConfigService

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Bots"])


async def require_bot_scope(request: Request) -> AuthContext:
    return await require_scope(request, "bot")


def get_service(request: Request) -> BotConfigService:
    return request.app.state.services.bots


@router.get("/bot-types")
async def list_bot_types(
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.list_bot_types())


@router.get("/bots")
async def list_bots(
    enabled: bool | None = Query(default=None),
    type_: str | None = Query(default=None, alias="type"),
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.list_bots(enabled=enabled, type_=type_))


@router.post("/bots")
async def create_bot(
    payload: BotConfigRequest,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    config = dict(payload.config)
    config.setdefault("enable", True)
    await service.create_bot(config)
    return ok(message="新增平台配置成功~")


@router.get("/bots/stats")
async def list_bot_stats(
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.get_bot_stats())


@router.patch("/bots/{bot_id:path}/enabled")
async def set_bot_enabled(
    bot_id: str,
    payload: EnabledPatch,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    await service.set_bot_enabled(bot_id, payload.enabled)
    return ok(message="更新平台配置成功~")


@router.post("/bots/{bot_id:path}/test")
async def test_bot(
    bot_id: str,
    _auth: AuthContext = Depends(require_bot_scope),
):
    return ok({"id": bot_id, "status": "unsupported"})


@router.get("/bots/{bot_id:path}")
async def get_bot(
    bot_id: str,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    return ok(service.get_bot(bot_id))


@router.put("/bots/{bot_id:path}")
async def update_bot(
    bot_id: str,
    payload: BotConfigRequest,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    config = dict(payload.config)
    if "id" not in config:
        config["id"] = bot_id
    config.setdefault("enable", True)
    await service.update_bot(bot_id, config)
    return ok(message="更新平台配置成功~")


@router.delete("/bots/{bot_id:path}")
async def delete_bot(
    bot_id: str,
    _auth: AuthContext = Depends(require_bot_scope),
    service: BotConfigService = Depends(get_service),
):
    await service.delete_bot(bot_id)
    return ok(message="删除平台配置成功~")
