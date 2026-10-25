from fastapi import APIRouter, Depends, Request

from astrbot.core.auth.models import AuthorizationValueError, Resource
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    ConfigContentRequest,
    ConfigProfileCreateRequest,
    ConfigRoutesReplaceRequest,
    ConfigRouteUpsertRequest,
    RenameRequest,
    model_dict,
)
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
    ConfigProfileService,
    ConfigRoutingService,
    sensitive_config_changed,
)

from .auth import AuthContext, require_resource_action, require_scope

router = APIRouter(tags=["Config Profiles"])


async def require_config_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config", authorize_action=False)


def get_service(request: Request) -> ConfigProfileService:
    return request.app.state.services.config_profiles


def get_routing_service(request: Request) -> ConfigRoutingService:
    return request.app.state.services.config_routes


def get_display_service(request: Request) -> ConfigDisplayService:
    return request.app.state.services.config_display


def get_file_service(request: Request) -> ConfigFileService:
    return request.app.state.services.config_files


async def _authorize_config_resource(
    request: Request,
    auth: AuthContext,
    *,
    config_id: str,
    write: bool = False,
) -> None:
    await require_resource_action(
        request,
        auth,
        action="platform.manage" if write else "platform.read",
        resource=Resource.instance(config_id),
    )


async def _authorize_config_route_collection(
    request: Request,
    auth: AuthContext,
    *,
    write: bool,
) -> None:
    await require_resource_action(
        request,
        auth,
        action="platform.manage" if write else "platform.read",
        resource=Resource.named("config-route", "collection", config_id="default"),
    )


def _validate_config_route_ids(config_ids: set[str]) -> None:
    for config_id in config_ids:
        try:
            Resource.instance(config_id)
        except AuthorizationValueError as exc:
            raise ApiError("Invalid config id", status_code=400) from exc


async def _authorize_config_route_targets(
    request: Request,
    auth: AuthContext,
    config_ids: set[str],
    *,
    tolerate_invalid: bool = False,
) -> None:
    for config_id in config_ids:
        if config_id == "default":
            continue
        try:
            await _authorize_config_resource(
                request,
                auth,
                config_id=config_id,
                write=True,
            )
        except AuthorizationValueError:
            if tolerate_invalid:
                continue
            raise ApiError("Invalid config id", status_code=400) from None


def _persisted_config_route_targets(service: ConfigRoutingService) -> set[str]:
    routing = service.list_routes().get("routing", {})
    if not isinstance(routing, dict):
        return set()
    return {value for value in routing.values() if isinstance(value, str)}


async def _can_read_config(
    request: Request,
    auth: AuthContext,
    config_id: str,
) -> bool:
    try:
        await _authorize_config_resource(request, auth, config_id=config_id)
    except ApiError as exc:
        if exc.status_code == 403:
            return False
        raise
    except AuthorizationValueError:
        # Persisted routing data predates route-id validation; do not let one
        # malformed entry break the whole listing endpoint.
        return False
    return True


async def _authorize_config_credentials_if_changed(
    request: Request,
    auth: AuthContext,
    *,
    config_id: str,
    posted_config: dict | None,
    service: ConfigProfileService,
    missing_is_change: bool = True,
) -> None:
    if not isinstance(posted_config, dict):
        return
    current_config = service.acm.confs.get(config_id)
    if not isinstance(current_config, dict) or not sensitive_config_changed(
        current_config,
        posted_config,
        missing_is_change=missing_is_change,
        ignored_paths=(
            ("dashboard", "totp", "enable"),
            ("dashboard", "totp", "secret"),
            ("dashboard", "totp", "recovery_code_hash"),
        ),
    ):
        return
    await require_resource_action(
        request,
        auth,
        action="provider.credentials.write",
        resource=Resource.instance(config_id),
    )


@router.get("/config-profiles/schema")
async def get_config_profile_schema(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.get_profile_schema())


@router.get("/config-profiles")
async def list_config_profiles(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.list_profiles())


@router.post("/config-profiles")
async def create_config_profile(
    payload: ConfigProfileCreateRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await require_resource_action(
        request,
        auth,
        action="platform.manage",
        resource=Resource.named("config-profile", "collection", config_id="default"),
    )
    await _authorize_config_credentials_if_changed(
        request,
        auth,
        config_id="default",
        posted_config=payload.config,
        service=service,
        missing_is_change=False,
    )
    return ok(
        await service.create_profile(
            payload.name,
            payload.config,
        ),
        "创建成功",
    )


@router.get("/config-profiles/{config_id}")
async def get_config_profile(
    config_id: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id)
    return ok(service.get_profile(config_id))


@router.put("/config-profiles/{config_id}")
async def update_config_profile(
    config_id: str,
    payload: ConfigContentRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    posted_config = model_dict(payload)
    await _authorize_config_credentials_if_changed(
        request,
        auth,
        config_id=config_id,
        posted_config=posted_config,
        service=service,
    )
    message = await service.update_profile(
        config_id,
        posted_config,
        subject=auth.subject,
        two_factor_code=request.headers.get("X-2FA-Code"),
    )
    return ok(message=message or "保存成功")


@router.patch("/config-profiles/{config_id}")
async def rename_config_profile(
    config_id: str,
    payload: RenameRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    await service.rename_profile(config_id, payload.name)
    return ok(message="更新成功")


@router.delete("/config-profiles/{config_id}")
async def delete_config_profile(
    config_id: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id=config_id, write=True)
    await service.delete_profile(config_id)
    return ok(message="删除成功")


@router.get("/system-config/schema")
async def get_system_config_schema(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.get_system_schema())


@router.get("/system-config")
async def get_system_config(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(service.get_system_config())


@router.get("/system-config/runtime")
async def get_system_config_runtime(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigDisplayService = Depends(get_display_service),
):
    await _authorize_config_resource(request, auth, config_id="default")
    return ok(await service.get_configs())


@router.put("/system-config")
async def update_system_config(
    payload: ConfigContentRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigProfileService = Depends(get_service),
):
    await _authorize_config_resource(request, auth, config_id="default", write=True)
    posted_config = model_dict(payload)
    await _authorize_config_credentials_if_changed(
        request,
        auth,
        config_id="default",
        posted_config=posted_config,
        service=service,
    )
    message = await service.update_profile(
        "default",
        posted_config,
        subject=auth.subject,
        two_factor_code=request.headers.get("X-2FA-Code"),
    )
    return ok(message=message or "保存成功")


@router.get("/config-routes")
async def list_config_routes(
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await _authorize_config_route_collection(request, auth, write=False)
    routes = service.list_routes()
    readable_ids = {
        config_id
        for config_id in set(routes.get("routing", {}).values())
        if await _can_read_config(request, auth, config_id)
    }
    return ok(
        {
            "routing": {
                umo: config_id
                for umo, config_id in routes.get("routing", {}).items()
                if config_id in readable_ids
            }
        }
    )


@router.put("/config-routes")
async def replace_config_routes(
    payload: ConfigRoutesReplaceRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await _authorize_config_route_collection(request, auth, write=True)
    new_targets = set(payload.routing.values())
    _validate_config_route_ids(new_targets)
    await _authorize_config_route_targets(request, auth, new_targets)
    # Replacing the mapping can remove routes from profiles the caller must not
    # modify, so authorize the targets that the replacement unbinds as well.
    removed_targets = _persisted_config_route_targets(service) - new_targets
    await _authorize_config_route_targets(
        request,
        auth,
        removed_targets,
        tolerate_invalid=True,
    )
    await service.replace_route_mapping(payload.routing)
    return ok(message="更新成功")


@router.put("/config-routes/{umo}")
async def upsert_config_route(
    umo: str,
    payload: ConfigRouteUpsertRequest,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await _authorize_config_route_collection(request, auth, write=True)
    _validate_config_route_ids({payload.config_id})
    await _authorize_config_route_targets(request, auth, {payload.config_id})
    current_config_id = service.list_routes().get("routing", {}).get(umo)
    if isinstance(current_config_id, str) and current_config_id != payload.config_id:
        # Rebinding a session removes its previous profile binding.
        await _authorize_config_route_targets(
            request,
            auth,
            {current_config_id},
            tolerate_invalid=True,
        )
    await service.set_route(umo, payload.config_id)
    return ok(message="更新成功")


@router.delete("/config-routes/{umo}")
async def delete_config_route(
    umo: str,
    request: Request,
    auth: AuthContext = Depends(require_config_scope),
    service: ConfigRoutingService = Depends(get_routing_service),
):
    await _authorize_config_route_collection(request, auth, write=True)
    current_config_id = service.list_routes().get("routing", {}).get(umo)
    if isinstance(current_config_id, str):
        # Persisted routing data may predate route-id validation. Deleting a
        # mapping whose target id is malformed cannot affect any profile.
        await _authorize_config_route_targets(
            request,
            auth,
            {current_config_id},
            tolerate_invalid=True,
        )
    await service.delete_route_by_umo(umo)
    return ok(message="删除成功")
