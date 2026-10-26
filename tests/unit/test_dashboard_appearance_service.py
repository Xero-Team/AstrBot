from __future__ import annotations

import json
from io import BytesIO
from tempfile import SpooledTemporaryFile

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from astrbot.dashboard.services import appearance_service as appearance_module
from astrbot.dashboard.services.appearance_service import (
    AppearanceService,
    AppearanceServiceError,
)


def _upload(
    *,
    format: str = "PNG",
    size: tuple[int, int] = (640, 360),
    color: str = "steelblue",
    filename: str | None = None,
    frames: int = 1,
) -> UploadFile:
    if frames > 1:
        images = [
            Image.new("RGB", size, color if index % 2 == 0 else "navy")
            for index in range(frames)
        ]
        payload = BytesIO()
        images[0].save(
            payload,
            format,
            save_all=True,
            append_images=images[1:],
            duration=100,
            loop=0,
        )
    else:
        image = Image.new("RGB", size, color)
        payload = BytesIO()
        image.save(payload, format)
    source = SpooledTemporaryFile()
    source.write(payload.getvalue())
    source.seek(0)
    return UploadFile(
        file=source,
        filename=filename or f"wallpaper.{format.lower()}",
        headers={"content-type": f"image/{format.lower()}"},
    )


@pytest.mark.asyncio
async def test_wallpaper_service_stores_lists_and_removes_assets(tmp_path):
    service = AppearanceService(tmp_path)

    uploaded = await service.save_wallpaper(_upload(), "landscape")

    assert uploaded["content_type"] == "image/png"
    assert uploaded["width"] == 640
    assert uploaded["height"] == 360
    assert uploaded["orientation"] == "landscape"
    assert uploaded["original_name"] == "wallpaper.png"
    assert uploaded["theme_primary"].startswith("#")
    assert uploaded["theme_secondary"].startswith("#")
    wallpapers = await service.list_wallpapers()
    assert wallpapers == [uploaded]

    wallpaper, content_type = await service.resolve_wallpaper(str(uploaded["id"]))
    thumbnail, thumbnail_type = await service.resolve_thumbnail(str(uploaded["id"]))
    assert wallpaper.is_file()
    assert content_type == "image/png"
    assert thumbnail.is_file()
    assert thumbnail_type == "image/webp"
    assert service.state_path.is_file()

    await service.delete_wallpaper(str(uploaded["id"]))

    assert await service.list_wallpapers() == []
    with pytest.raises(AppearanceServiceError):
        await service.resolve_wallpaper(str(uploaded["id"]))


@pytest.mark.asyncio
async def test_landscape_and_portrait_libraries_are_separate(tmp_path):
    service = AppearanceService(tmp_path)
    landscape = await service.save_wallpaper(_upload(color="green"), "landscape")
    portrait = await service.save_wallpaper(_upload(color="red"), "portrait")

    assert [item["id"] for item in await service.list_wallpapers("landscape")] == [
        landscape["id"]
    ]
    assert [item["id"] for item in await service.list_wallpapers("portrait")] == [
        portrait["id"]
    ]
    assert {item["id"] for item in await service.list_wallpapers()} == {
        landscape["id"],
        portrait["id"],
    }


@pytest.mark.asyncio
async def test_settings_persist_and_clear_invalid_selections(tmp_path):
    service = AppearanceService(tmp_path)
    wallpaper = await service.save_wallpaper(_upload(), "landscape")

    settings = await service.update_settings(
        {
            "enabled": True,
            "landscape_wallpaper_id": wallpaper["id"],
            "portrait_wallpaper_id": wallpaper["id"],
            "blur": 99,
            "rotation_interval_minutes": 0,
        }
    )
    assert settings["enabled"] is True
    assert settings["landscape_wallpaper_id"] == wallpaper["id"]
    assert settings["portrait_wallpaper_id"] == ""
    assert settings["blur"] == 40
    assert settings["rotation_interval_minutes"] == 1

    restarted = AppearanceService(tmp_path)
    assert (await restarted.get_settings())["landscape_wallpaper_id"] == wallpaper["id"]


@pytest.mark.asyncio
async def test_delete_clears_existing_selection(tmp_path):
    service = AppearanceService(tmp_path)
    wallpaper = await service.save_wallpaper(_upload(), "portrait")
    await service.update_settings(
        {"enabled": True, "portrait_wallpaper_id": wallpaper["id"]}
    )

    await service.delete_wallpaper(wallpaper["id"])

    settings = await service.get_settings()
    assert settings["portrait_wallpaper_id"] == ""
    assert settings["enabled"] is True


@pytest.mark.asyncio
async def test_rejects_non_images(tmp_path):
    source = SpooledTemporaryFile()
    source.write(b"not an image")
    source.seek(0)
    upload = UploadFile(file=source, filename="not-an-image.txt")
    service = AppearanceService(tmp_path)

    with pytest.raises(AppearanceServiceError, match="Unsupported wallpaper image"):
        await service.save_wallpaper(upload, "landscape")


@pytest.mark.asyncio
async def test_rejects_oversized_files_before_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(appearance_module, "MAX_WALLPAPER_BYTES", 10)
    service = AppearanceService(tmp_path)

    with pytest.raises(AppearanceServiceError, match="must not exceed"):
        await service.save_wallpaper(_upload(), "landscape")

    assert list(service.wallpaper_dir.glob("*")) == []


@pytest.mark.asyncio
async def test_rejects_excessive_pixels_before_full_decode(tmp_path, monkeypatch):
    monkeypatch.setattr(appearance_module, "MAX_WALLPAPER_PIXELS", 1000)
    service = AppearanceService(tmp_path)

    with pytest.raises(AppearanceServiceError, match="dimensions are not supported"):
        await service.save_wallpaper(_upload(), "landscape")


@pytest.mark.asyncio
async def test_animated_gif_is_detected_and_gets_static_thumbnail(tmp_path):
    service = AppearanceService(tmp_path)

    uploaded = await service.save_wallpaper(
        _upload(format="GIF", frames=2),
        "landscape",
    )

    assert uploaded["content_type"] == "image/gif"
    assert uploaded["animated"] is True
    thumbnail, _ = await service.resolve_thumbnail(uploaded["id"])
    with Image.open(thumbnail) as image:
        assert not getattr(image, "is_animated", False)


@pytest.mark.asyncio
async def test_legacy_file_is_migrated_to_both_orientations(tmp_path):
    service = AppearanceService(tmp_path)
    service.wallpaper_dir.mkdir(parents=True, exist_ok=True)
    service.thumbnail_dir.mkdir(parents=True, exist_ok=True)
    wallpaper_id = "a" * 32
    path = service.wallpaper_dir / f"{wallpaper_id}.png"
    Image.new("RGB", (640, 360), "teal").save(path, "PNG")
    thumbnail = service.thumbnail_dir / f"{wallpaper_id}.webp"
    with Image.open(path) as image:
        image.thumbnail((320, 320))
        image.save(thumbnail, "WEBP")

    listed = await service.list_wallpapers()

    assert listed[0]["orientation"] == "both"
    assert listed[0]["theme_primary"].startswith("#")
    assert service.state_path.is_file()
    assert [item["id"] for item in await service.list_wallpapers("landscape")] == [
        wallpaper_id
    ]
    assert [item["id"] for item in await service.list_wallpapers("portrait")] == [
        wallpaper_id
    ]


@pytest.mark.asyncio
async def test_listing_uses_persisted_metadata_without_decoding(tmp_path, monkeypatch):
    service = AppearanceService(tmp_path)
    await service.save_wallpaper(_upload(), "landscape")
    restarted = AppearanceService(tmp_path)

    def fail_open(*_args, **_kwargs):
        raise AssertionError("list must not decode wallpapers")

    monkeypatch.setattr(Image, "open", fail_open)
    listed = await restarted.list_wallpapers()
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_upload_rejects_invalid_orientation(tmp_path):
    service = AppearanceService(tmp_path)
    upload = _upload()
    with pytest.raises(AppearanceServiceError, match="orientation"):
        await service.save_wallpaper(upload, "square")
    assert upload.file.closed


@pytest.mark.asyncio
async def test_corrupt_asset_is_skipped_without_failing_state_load(tmp_path):
    service = AppearanceService(tmp_path)
    service.wallpaper_dir.mkdir(parents=True, exist_ok=True)
    (service.wallpaper_dir / f"{'a' * 32}.png").write_bytes(b"not an image")

    assert await service.list_wallpapers() == []
    assert (await service.get_settings())["enabled"] is False


@pytest.mark.asyncio
async def test_corrupt_asset_drops_unusable_persisted_metadata(tmp_path):
    service = AppearanceService(tmp_path)
    service.wallpaper_dir.mkdir(parents=True, exist_ok=True)
    service.thumbnail_dir.mkdir(parents=True, exist_ok=True)
    wallpaper_id = "a" * 32
    (service.wallpaper_dir / f"{wallpaper_id}.png").write_bytes(b"not an image")
    service.state_path.write_text(
        json.dumps(
            {
                "revision": 1,
                "settings": {"enabled": True},
                "wallpapers": {wallpaper_id: {"id": wallpaper_id}},
            }
        ),
        encoding="utf-8",
    )

    restarted = AppearanceService(tmp_path)
    assert await restarted.list_wallpapers() == []
    assert (await restarted.get_settings())["enabled"] is True
    state = json.loads(restarted.state_path.read_text(encoding="utf-8"))
    assert wallpaper_id not in state["wallpapers"]


@pytest.mark.asyncio
async def test_transient_rebuild_failure_keeps_usable_metadata(tmp_path, monkeypatch):
    service = AppearanceService(tmp_path)
    uploaded = await service.save_wallpaper(_upload(), "portrait")
    service.thumbnail_dir.joinpath(f"{uploaded['id']}.webp").unlink()

    def fail_rebuild(*_args, **_kwargs):
        raise AppearanceServiceError("transient failure")

    monkeypatch.setattr(AppearanceService, "_migrate_asset", fail_rebuild)

    listed = await AppearanceService(tmp_path).list_wallpapers()

    assert [item["id"] for item in listed] == [uploaded["id"]]
    assert listed[0]["orientation"] == "portrait"
    assert listed[0]["original_name"] == "wallpaper.png"


@pytest.mark.asyncio
async def test_invalid_persisted_metadata_is_rebuilt(tmp_path):
    service = AppearanceService(tmp_path)
    uploaded = await service.save_wallpaper(_upload(), "landscape")
    state = json.loads(service.state_path.read_text(encoding="utf-8"))
    state["wallpapers"][uploaded["id"]]["width"] = "invalid"
    state["wallpapers"][uploaded["id"]]["theme_primary"] = "not-a-color"
    service.state_path.write_text(json.dumps(state), encoding="utf-8")

    restarted = AppearanceService(tmp_path)
    listed = await restarted.list_wallpapers()

    assert listed[0]["id"] == uploaded["id"]
    assert listed[0]["width"] == 640
    assert listed[0]["theme_primary"].startswith("#")
    rebuilt = json.loads(restarted.state_path.read_text(encoding="utf-8"))
    assert rebuilt["wallpapers"][uploaded["id"]]["width"] == 640
    assert rebuilt["wallpapers"][uploaded["id"]]["theme_primary"].startswith("#")


def test_safe_original_name_strips_paths_and_controls():
    assert AppearanceService._safe_original_name("C:\\temp\\a\x00b.png") == "ab.png"
    assert AppearanceService._safe_original_name(None) == ""
