from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from astrbot.core import logger
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ok
from astrbot.dashboard.schemas import (
    EnabledPatch,
    PluginByIdRequest,
    PluginConfigFileDeleteRequest,
    PluginConfigPayload,
    PluginConfigUpdateRequest,
    PluginEnabledRequest,
    PluginInstallRequest,
    PluginSourceRequest,
    PluginUninstallRequest,
    PluginUpdateRequest,
    PluginVersionSupportRequest,
)
from astrbot.dashboard.services.config_service import (
    ConfigDisplayService,
    ConfigFileService,
)
from astrbot.dashboard.services.plugin_service import (
    PLUGIN_OPERATION_FAILED_MESSAGE,
    PluginService,
    PluginServiceError,
    PluginServiceWarning,
)

from .auth import AuthContext, require_scope
from .multipart import multipart_parts

router = APIRouter(tags=["Plugins"])


async def require_plugin_scope(request: Request) -> AuthContext:
    return await require_scope(request, "plugin")


def get_service(request: Request) -> PluginService:
    return request.app.state.services.plugins


def get_config_display_service(request: Request) -> ConfigDisplayService:
    return request.app.state.services.config_display


def get_config_file_service(request: Request) -> ConfigFileService:
    return request.app.state.services.config_files


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _required_text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing key: {name}")
    return text


def _plugin_id_from_body(body: dict[str, Any]) -> str:
    return _required_text(body.get("plugin_id"), "plugin_id")


def _model_dict(payload) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


def _service_ok(result):
    if isinstance(result, tuple):
        data, message = result
        return ok(data, message)
    return ok(result)


async def _run_service(operation, *, log_label: str | None = None):
    try:
        result = await run_maybe_async(operation)
        return _service_ok(result)
    except PluginServiceWarning as exc:
        return {
            "status": "warning",
            "message": exc.public_message,
            "data": exc.data,
        }
    except PluginServiceError as exc:
        return {"status": "error", "message": exc.public_message, "data": {}}
    except Exception:
        if log_label:
            logger.error("%s failed", log_label, exc_info=True)
        else:
            logger.error("Plugin service operation failed", exc_info=True)
        return {
            "status": "error",
            "message": PLUGIN_OPERATION_FAILED_MESSAGE,
            "data": {},
        }


async def _check_plugin_version_support_payload(
    payload: dict[str, Any],
    service: PluginService,
):
    return await _run_service(
        lambda: service.check_plugin_version_support(payload),
        log_label="/api/v1/plugins/version-support/check",
    )


async def _install_plugin_upload(
    request: Request,
    service: PluginService,
    *,
    log_label: str,
):
    async def operation():
        form, files = await multipart_parts(request)
        upload_file = files.get("file")
        if upload_file is None:
            raise PluginServiceError("缺少插件文件")
        return await service.install_plugin_upload_from_dashboard_form(
            upload_file=upload_file,
            ignore_version_check=form.get("ignore_version_check", "false"),
        )

    return await _run_service(operation, log_label=log_label)


@router.get("/plugins/failed")
async def list_failed_plugins(
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(service.get_failed_plugins)


@router.post("/plugins/update")
async def update_plugins(
    payload: PluginUpdateRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    if body.get("plugin_id"):
        plugin_id = _plugin_id_from_body(body)
        return await _run_service(
            service.update_plugin(
                {
                    "name": plugin_id,
                    **{key: value for key, value in body.items() if key != "plugin_id"},
                }
            ),
            log_label="/api/v1/plugins/update",
        )
    return await _run_service(
        service.update_all_plugins(
            {
                **body,
                "names": body.get("names") or body.get("plugin_ids") or [],
            }
        ),
        log_label="/api/v1/plugins/update-all",
    )


@router.post("/plugins/version-support/check")
async def check_plugin_version_support(
    payload: PluginVersionSupportRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _check_plugin_version_support_payload(_model_dict(payload), service)


@router.post("/plugins/install/github")
async def install_plugin_from_github(
    payload: PluginInstallRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    repository = str(body.get("repository") or body.get("url") or "").strip()
    if repository and not repository.startswith(("http://", "https://")):
        repository = f"https://github.com/{repository}"
    install_payload = {
        "url": repository,
        "proxy": body.get("proxy"),
        "ignore_version_check": body.get("ignore_version_check", False),
    }
    if body.get("download_url"):
        install_payload["download_url"] = body["download_url"]
    return await _run_service(
        service.install_plugin(install_payload),
        log_label="/api/v1/plugins/install/github",
    )


@router.post("/plugins/install/url")
async def install_plugin_from_url(
    payload: PluginInstallRequest | None = Body(default=None),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    url = str(body.get("url") or body.get("repository") or "").strip()
    download_url = str(body.get("download_url") or url).strip()
    return await _run_service(
        service.install_plugin(
            {
                "url": url or download_url,
                "download_url": download_url,
                "proxy": body.get("proxy"),
                "ignore_version_check": body.get("ignore_version_check", False),
            }
        ),
        log_label="/api/v1/plugins/install/url",
    )


@router.post("/plugins/install/upload")
async def install_plugin_from_upload(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _install_plugin_upload(
        request,
        service,
        log_label="/api/v1/plugins/install/upload",
    )


@router.get("/plugins/market")
async def list_plugin_market(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.get_online_plugins_from_dashboard_query(
            custom_registry=request.query_params.get("custom_registry"),
            force_refresh=request.query_params.get("force_refresh", "false"),
        ),
        log_label="/api/v1/plugins/market",
    )


@router.get("/plugins/market/categories")
async def list_plugin_market_categories(
    _auth: AuthContext = Depends(require_plugin_scope),
):
    return ok({"categories": []})


@router.get("/plugin-sources")
async def list_plugin_sources(
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok({"sources": await service.get_custom_sources()})


@router.post("/plugin-sources")
async def create_plugin_source(
    payload: PluginSourceRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.create_custom_source(_model_dict(payload))},
        message="保存成功",
    )


@router.put("/plugin-sources")
async def replace_plugin_sources(
    payload: PluginSourceRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.replace_custom_sources(_model_dict(payload))},
        message="保存成功",
    )


@router.delete("/plugin-sources/by-id")
async def delete_plugin_source_by_id(
    source_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.delete_custom_source(source_id)},
        message="保存成功",
    )


@router.delete("/plugin-sources/{source_id}")
async def delete_plugin_source(
    source_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return ok(
        {"sources": await service.delete_custom_source(source_id)},
        message="保存成功",
    )


@router.get("/plugins")
async def list_plugins(
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.list_plugins_from_dashboard_query(
            plugin_name=request.query_params.get("name")
            or request.query_params.get("plugin_id"),
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
        ),
        log_label="/api/v1/plugins",
    )


@router.get("/plugins/by-id")
async def get_plugin_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.get_plugin_detail(
            plugin_name=plugin_id,
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
        ),
        log_label="/api/v1/plugins/by-id",
    )


@router.delete("/plugins/by-id")
async def uninstall_plugin_by_id(
    payload: PluginUninstallRequest | None = None,
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_plugin({"name": plugin_id, **body}),
        log_label="/api/v1/plugins/by-id",
    )


@router.get("/plugins/config")
async def get_plugin_config_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.put("/plugins/config")
async def update_plugin_config_by_id(
    payload: PluginConfigUpdateRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    body = _model_dict(payload)
    plugin_id = _plugin_id_from_body(body)
    config = body.get("config")
    config = config if isinstance(config, dict) else {}
    return ok(
        message=await service.save_plugin_configs_from_dashboard_payload(
            config,
            plugin_name=plugin_id,
        )
    )


@router.get("/plugins/config/schema")
async def get_plugin_config_schema_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.get("/plugins/config-files")
async def list_plugin_config_files_by_id(
    plugin_id: str = Query(...),
    config_key: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        service.list_config_files(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
        )
    )


@router.post("/plugins/config-files")
async def upload_plugin_config_files_by_id(
    request: Request,
    plugin_id: str = Query(...),
    config_key: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    _, files = await multipart_parts(request)
    return ok(
        await service.upload_config_file(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
            files=files,
        )
    )


@router.delete("/plugins/config-files")
async def delete_plugin_config_file_by_id(
    payload: PluginConfigFileDeleteRequest | None = None,
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        message=service.delete_config_file_from_dashboard_payload(
            scope="plugin",
            name=plugin_id,
            payload=_model_dict(payload),
        )
    )


@router.get("/plugins/readme")
async def get_plugin_readme_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_readme(plugin_id),
        log_label="/api/v1/plugins/readme",
    )


@router.get("/plugins/changelog")
async def get_plugin_changelog_by_id(
    plugin_id: str = Query(...),
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_changelog(plugin_id),
        log_label="/api/v1/plugins/changelog",
    )


@router.post("/plugins/reload")
async def reload_plugin_by_id(
    payload: PluginByIdRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    plugin_id = _plugin_id_from_body(_model_dict(payload))
    return await _run_service(
        service.reload_plugin({"name": plugin_id}),
        log_label="/api/v1/plugins/reload",
    )


@router.patch("/plugins/enabled")
async def set_plugin_enabled_by_id(
    payload: PluginEnabledRequest,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    plugin_id = _plugin_id_from_body(body)
    return await _run_service(
        service.set_plugin_enabled(
            {"name": plugin_id}, enabled=bool(body.get("enabled"))
        ),
        log_label="/api/v1/plugins/enabled:on"
        if body.get("enabled")
        else "/api/v1/plugins/enabled:off",
    )


@router.get("/plugins/{plugin_id}")
async def get_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.get_plugin_detail(
            plugin_name=plugin_id,
            logo_token_resolver=service.get_plugin_logo_token,
            installed_at_resolver=service.get_plugin_installed_at,
        ),
        log_label="/api/v1/plugins/{plugin_id}",
    )


@router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(
    plugin_id: str,
    payload: PluginUninstallRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_plugin({"name": plugin_id, **body}),
        log_label="/api/v1/plugins/{plugin_id}",
    )


@router.delete("/plugins/failed/{plugin_id}")
async def uninstall_failed_plugin(
    plugin_id: str,
    payload: PluginUninstallRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.uninstall_failed_plugin({"dir_name": plugin_id, **body}),
        log_label="/api/v1/plugins/failed/{plugin_id}",
    )


@router.post("/plugins/failed/{plugin_id}/reload")
async def reload_failed_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.reload_failed_plugin({"dir_name": plugin_id}),
        log_label="/api/v1/plugins/failed/{plugin_id}/reload",
    )


@router.get("/plugins/{plugin_id}/config")
async def get_plugin_config(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.put("/plugins/{plugin_id}/config")
async def update_plugin_config(
    plugin_id: str,
    payload: PluginConfigPayload,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    body = _model_dict(payload)
    config = body.get("config")
    config = config if isinstance(config, dict) else body
    return ok(
        message=await service.save_plugin_configs_from_dashboard_payload(
            config,
            plugin_name=plugin_id,
        )
    )


@router.get("/plugins/{plugin_id}/config/schema")
async def get_plugin_config_schema(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigDisplayService = Depends(get_config_display_service),
):
    return ok({"plugin_name": plugin_id, **await service.get_configs(plugin_id)})


@router.get("/plugins/{plugin_id}/config-files/{config_key:path}")
async def list_plugin_config_files(
    plugin_id: str,
    config_key: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        service.list_config_files(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
        )
    )


@router.post("/plugins/{plugin_id}/config-files/{config_key:path}")
async def upload_plugin_config_files(
    plugin_id: str,
    config_key: str,
    request: Request,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    _, files = await multipart_parts(request)
    return ok(
        await service.upload_config_file(
            scope="plugin",
            name=plugin_id,
            key_path=config_key,
            files=files,
        )
    )


@router.delete("/plugins/{plugin_id}/config-files")
async def delete_plugin_config_file(
    plugin_id: str,
    payload: PluginConfigFileDeleteRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: ConfigFileService = Depends(get_config_file_service),
):
    return ok(
        message=service.delete_config_file_from_dashboard_payload(
            scope="plugin",
            name=plugin_id,
            payload=_model_dict(payload),
        )
    )


@router.get("/plugins/{plugin_id}/readme")
async def get_plugin_readme(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_readme(plugin_id),
        log_label="/api/v1/plugins/{plugin_id}/readme",
    )


@router.get("/plugins/{plugin_id}/changelog")
async def get_plugin_changelog(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        lambda: service.get_plugin_changelog(plugin_id),
        log_label="/api/v1/plugins/{plugin_id}/changelog",
    )


@router.post("/plugins/{plugin_id}/reload")
async def reload_plugin(
    plugin_id: str,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.reload_plugin({"name": plugin_id}),
        log_label="/api/v1/plugins/{plugin_id}/reload",
    )


@router.patch("/plugins/{plugin_id}/enabled")
async def set_plugin_enabled(
    plugin_id: str,
    payload: EnabledPatch,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    return await _run_service(
        service.set_plugin_enabled({"name": plugin_id}, enabled=payload.enabled),
        log_label="/api/v1/plugins/{plugin_id}/enabled:on"
        if payload.enabled
        else "/api/v1/plugins/{plugin_id}/enabled:off",
    )


@router.post("/plugins/{plugin_id}/update")
async def update_plugin(
    plugin_id: str,
    payload: PluginUpdateRequest | None = None,
    _auth: AuthContext = Depends(require_plugin_scope),
    service: PluginService = Depends(get_service),
):
    body = _model_dict(payload)
    return await _run_service(
        service.update_plugin({"name": plugin_id, **body}),
        log_label="/api/v1/plugins/{plugin_id}/update",
    )
