"""Dashboard appearance asset API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from astrbot.dashboard.responses import ok
from astrbot.dashboard.services.appearance_service import (
    AppearanceService,
    AppearanceServiceError,
)

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Appearance"])
_IMAGE_HEADERS = {
    "Cache-Control": "private, max-age=300",
    "X-Content-Type-Options": "nosniff",
}
_WALLPAPER_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Wallpaper image bytes",
        "content": {
            "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
            "image/png": {"schema": {"type": "string", "format": "binary"}},
            "image/webp": {"schema": {"type": "string", "format": "binary"}},
            "image/gif": {"schema": {"type": "string", "format": "binary"}},
        },
    }
}
_THUMBNAIL_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "WebP wallpaper thumbnail bytes",
        "content": {"image/webp": {"schema": {"type": "string", "format": "binary"}}},
    }
}


def get_service(request: Request) -> AppearanceService:
    return request.app.state.services.appearance


async def require_appearance_scope(request: Request) -> AuthContext:
    return await require_scope(request, "config")


@router.get("/appearance/wallpapers")
async def list_wallpapers(
    _auth: AuthContext = Depends(require_appearance_scope),
    service: AppearanceService = Depends(get_service),
):
    return ok({"items": await service.list_wallpapers()})


@router.post("/appearance/wallpapers")
async def upload_wallpaper(
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(require_appearance_scope),
    service: AppearanceService = Depends(get_service),
):
    try:
        return ok(await service.save_wallpaper(file))
    except AppearanceServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/appearance/wallpapers/{wallpaper_id}/thumbnail",
    responses=_THUMBNAIL_RESPONSE,
)
async def get_wallpaper_thumbnail(
    wallpaper_id: str,
    _auth: AuthContext = Depends(require_appearance_scope),
    service: AppearanceService = Depends(get_service),
):
    try:
        path, content_type = await service.resolve_thumbnail(wallpaper_id)
    except AppearanceServiceError as exc:
        raise HTTPException(
            status_code=404, detail="Wallpaper thumbnail not found"
        ) from exc
    return FileResponse(path, media_type=content_type, headers=_IMAGE_HEADERS)


@router.get("/appearance/wallpapers/{wallpaper_id}", responses=_WALLPAPER_RESPONSE)
async def get_wallpaper(
    wallpaper_id: str,
    _auth: AuthContext = Depends(require_appearance_scope),
    service: AppearanceService = Depends(get_service),
):
    try:
        path, content_type = await service.resolve_wallpaper(wallpaper_id)
    except AppearanceServiceError as exc:
        raise HTTPException(status_code=404, detail="Wallpaper not found") from exc
    return FileResponse(path, media_type=content_type, headers=_IMAGE_HEADERS)


@router.delete("/appearance/wallpapers/{wallpaper_id}")
async def delete_wallpaper(
    wallpaper_id: str,
    _auth: AuthContext = Depends(require_appearance_scope),
    service: AppearanceService = Depends(get_service),
):
    try:
        await service.delete_wallpaper(wallpaper_id)
    except AppearanceServiceError as exc:
        raise HTTPException(status_code=404, detail="Wallpaper not found") from exc
    return ok({"id": wallpaper_id})
