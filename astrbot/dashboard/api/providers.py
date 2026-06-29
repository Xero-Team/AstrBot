from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.responses import ok
from astrbot.dashboard.schemas import (
    EnabledPatch,
    ProviderConfigRequest,
    ProviderEmbeddingDimensionRequest,
    ProviderSourceRequest,
)
from astrbot.dashboard.services.config_service import ProviderConfigService

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Providers"])


async def require_provider_scope(request: Request) -> AuthContext:
    return await require_scope(request, "provider")


def get_service(request: Request) -> ProviderConfigService:
    return request.app.state.services.providers


def _reject_legacy_provider_query_params(
    request: Request,
    *forbidden: str,
) -> None:
    legacy_fields = [key for key in forbidden if key in request.query_params]
    if legacy_fields:
        fields = ", ".join(sorted(legacy_fields))
        raise ValueError(
            f"Legacy provider query parameters are not supported: {fields}"
        )


def _model_dict(payload) -> dict:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


def _provider_config_for_dimension(
    service: ProviderConfigService,
    provider_id: str,
    body: dict,
) -> dict:
    provider = service.get_provider(provider_id, merged=True)
    base_config = provider.get("provider") if isinstance(provider, dict) else {}
    if not isinstance(base_config, dict):
        base_config = {}
    provider_config = body.get("config")
    if isinstance(provider_config, dict):
        return {**base_config, **provider_config}
    return base_config


@router.get("/providers/schema")
async def get_provider_schema(
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    return ok(service.get_provider_schema())


@router.get("/provider-sources")
async def list_provider_sources(
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    return ok(service.list_provider_sources())


@router.post("/provider-sources")
async def create_provider_source(
    payload: ProviderSourceRequest,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    source_id = config.get("id")
    if not source_id:
        raise ValueError("Provider source config must have an 'id' field")
    await service.upsert_provider_source(source_id, config)
    return ok(message="更新 provider source 成功")


@router.get("/provider-sources/{source_id:path}/models")
async def list_provider_source_models(
    source_id: str,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    return ok(await service.list_provider_source_models(source_id))


@router.get("/provider-sources/{source_id:path}/providers")
async def list_providers_by_source(
    source_id: str,
    request: Request,
    provider_type: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    _reject_legacy_provider_query_params(request, "capability")
    return ok(
        service.list_providers(
            provider_type=provider_type,
            provider_source_id=source_id,
        )
    )


@router.post("/provider-sources/{source_id:path}/providers")
async def create_provider_in_source(
    source_id: str,
    payload: ProviderConfigRequest,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    config.setdefault("enable", True)
    config["provider_source_id"] = source_id
    await service.create_provider(config, source_id)
    return ok(message="新增服务提供商配置成功")


@router.get("/provider-sources/{source_id:path}")
async def get_provider_source(
    source_id: str,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    return ok(service.get_provider_source(source_id))


@router.put("/provider-sources/{source_id:path}")
async def upsert_provider_source(
    source_id: str,
    payload: ProviderSourceRequest,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await service.upsert_provider_source(
        source_id,
        dict(payload.config),
    )
    return ok(message="更新 provider source 成功")


@router.delete("/provider-sources/{source_id:path}")
async def delete_provider_source(
    source_id: str,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await service.delete_provider_source(source_id)
    return ok(message="删除 provider source 成功")


@router.get("/providers")
async def list_providers(
    request: Request,
    provider_type: str | None = Query(default=None),
    provider_source_id: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    _reject_legacy_provider_query_params(request, "capability", "source_id")
    return ok(
        service.list_providers(
            provider_type=provider_type,
            provider_source_id=provider_source_id,
            enabled=enabled,
        )
    )


@router.post("/providers")
async def create_provider(
    payload: ProviderConfigRequest,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    config.setdefault("enable", True)
    await service.create_provider(config)
    return ok(message="新增服务提供商配置成功")


@router.patch("/providers/{provider_id:path}/enabled")
async def set_provider_enabled(
    provider_id: str,
    payload: EnabledPatch,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await service.set_provider_enabled(provider_id, payload.enabled)
    return ok(message="更新成功，已经实时生效~")


@router.post("/providers/{provider_id:path}/test")
async def test_provider(
    provider_id: str,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    return ok(await service.test_provider(provider_id))


@router.post("/providers/{provider_id:path}/embedding-dimension")
async def get_embedding_dimension(
    provider_id: str,
    payload: ProviderEmbeddingDimensionRequest | None = None,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    body = _model_dict(payload)
    return ok(
        await service.get_embedding_dimension(
            _provider_config_for_dimension(service, provider_id, body)
        )
    )


@router.get("/providers/{provider_id:path}")
async def get_provider(
    provider_id: str,
    merged: bool = Query(default=False),
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    return ok(service.get_provider(provider_id, merged=merged))


@router.put("/providers/{provider_id:path}")
async def update_provider(
    provider_id: str,
    payload: ProviderConfigRequest,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    if "id" not in config:
        config["id"] = provider_id
    config.setdefault("enable", True)
    await service.update_provider(provider_id, config)
    return ok(message="更新成功，已经实时生效~")


@router.delete("/providers/{provider_id:path}")
async def delete_provider(
    provider_id: str,
    _auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await service.delete_provider(provider_id)
    return ok(message="删除成功，已经实时生效。")
