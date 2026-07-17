from __future__ import annotations

from io import BytesIO
from tempfile import SpooledTemporaryFile

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from astrbot.dashboard.services.appearance_service import (
    AppearanceService,
    AppearanceServiceError,
)


def _png_upload() -> UploadFile:
    image = Image.new("RGB", (640, 360), "steelblue")
    payload = BytesIO()
    image.save(payload, "PNG")
    source = SpooledTemporaryFile()
    source.write(payload.getvalue())
    source.seek(0)
    return UploadFile(
        file=source, filename="wallpaper.png", headers={"content-type": "image/png"}
    )


@pytest.mark.asyncio
async def test_wallpaper_service_stores_lists_and_removes_assets(tmp_path):
    service = AppearanceService(tmp_path)

    uploaded = await service.save_wallpaper(_png_upload())

    assert uploaded["content_type"] == "image/png"
    assert uploaded["width"] == 640
    assert uploaded["height"] == 360
    wallpapers = await service.list_wallpapers()
    assert wallpapers == [uploaded]

    wallpaper, content_type = await service.resolve_wallpaper(str(uploaded["id"]))
    thumbnail, thumbnail_type = await service.resolve_thumbnail(str(uploaded["id"]))
    assert wallpaper.is_file()
    assert content_type == "image/png"
    assert thumbnail.is_file()
    assert thumbnail_type == "image/webp"

    await service.delete_wallpaper(str(uploaded["id"]))

    assert await service.list_wallpapers() == []
    with pytest.raises(AppearanceServiceError):
        await service.resolve_wallpaper(str(uploaded["id"]))


@pytest.mark.asyncio
async def test_wallpaper_service_rejects_non_images(tmp_path):
    source = SpooledTemporaryFile()
    source.write(b"not an image")
    source.seek(0)
    upload = UploadFile(file=source, filename="not-an-image.txt")
    service = AppearanceService(tmp_path)

    with pytest.raises(AppearanceServiceError, match="Unsupported wallpaper image"):
        await service.save_wallpaper(upload)
