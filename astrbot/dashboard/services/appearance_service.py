"""Managed Dashboard wallpaper assets."""

from __future__ import annotations

import asyncio
import os
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.datastructures import UploadFile

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

MAX_WALLPAPER_BYTES = 10 * 1024 * 1024
MAX_WALLPAPER_PIXELS = 40_000_000
THUMBNAIL_MAX_SIDE = 320
_CHUNK_SIZE = 64 * 1024
_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"),
}
_WALLPAPER_SUFFIXES = frozenset(suffix for suffix, _ in _IMAGE_FORMATS.values())
_THUMBNAIL_RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


class AppearanceServiceError(ValueError):
    """Raised when a Dashboard appearance operation cannot be completed."""


class AppearanceService:
    """Store and validate Dashboard wallpaper assets under the runtime data root."""

    def __init__(self, data_root: Path | None = None) -> None:
        root = data_root or Path(get_astrbot_data_path())
        appearance_root = root / "dashboard" / "appearance"
        self.wallpaper_dir = appearance_root / "wallpapers"
        self.thumbnail_dir = appearance_root / "thumbnails"

    async def list_wallpapers(self) -> list[dict[str, int | str]]:
        return await asyncio.to_thread(self._list_wallpapers)

    async def save_wallpaper(self, upload: UploadFile) -> dict[str, int | str]:
        self._ensure_directories()
        temporary_path = self.wallpaper_dir / f".{uuid4().hex}.upload"
        target_path: Path | None = None
        try:
            await self._write_upload(upload, temporary_path)
            suffix, content_type, width, height = await asyncio.to_thread(
                self._inspect_image,
                temporary_path,
            )
            wallpaper_id = uuid4().hex
            target_path = self.wallpaper_dir / f"{wallpaper_id}{suffix}"
            await asyncio.to_thread(os.replace, temporary_path, target_path)
            await asyncio.to_thread(self._build_thumbnail, target_path, wallpaper_id)
            return self._wallpaper_item(target_path, content_type, width, height)
        except AppearanceServiceError:
            raise
        except OSError as exc:
            raise AppearanceServiceError("Unable to save wallpaper") from exc
        finally:
            await upload.close()
            temporary_path.unlink(missing_ok=True)
            if (
                target_path is not None
                and not self._thumbnail_path(target_path.stem).is_file()
            ):
                target_path.unlink(missing_ok=True)

    async def delete_wallpaper(self, wallpaper_id: str) -> None:
        path = await asyncio.to_thread(self._resolve_wallpaper, wallpaper_id)
        await asyncio.to_thread(path.unlink)
        self._thumbnail_path(wallpaper_id).unlink(missing_ok=True)

    async def resolve_wallpaper(self, wallpaper_id: str) -> tuple[Path, str]:
        path = await asyncio.to_thread(self._resolve_wallpaper, wallpaper_id)
        return path, self._content_type_for_path(path)

    async def resolve_thumbnail(self, wallpaper_id: str) -> tuple[Path, str]:
        self._validate_wallpaper_id(wallpaper_id)
        path = self._thumbnail_path(wallpaper_id)
        if not path.is_file():
            raise AppearanceServiceError("Wallpaper thumbnail was not found")
        return path, "image/webp"

    async def _write_upload(self, upload: UploadFile, destination: Path) -> None:
        size = 0
        try:
            with destination.open("xb") as output:
                while chunk := await upload.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_WALLPAPER_BYTES:
                        raise AppearanceServiceError("Wallpaper must not exceed 10 MiB")
                    await asyncio.to_thread(output.write, chunk)
        except AppearanceServiceError:
            raise
        except OSError as exc:
            raise AppearanceServiceError("Unable to receive wallpaper") from exc
        if size == 0:
            raise AppearanceServiceError("Wallpaper must not be empty")

    def _list_wallpapers(self) -> list[dict[str, int | str]]:
        if not self.wallpaper_dir.is_dir():
            return []
        wallpapers: list[dict[str, int | str]] = []
        for path in self.wallpaper_dir.iterdir():
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() not in _WALLPAPER_SUFFIXES
            ):
                continue
            try:
                suffix, content_type, width, height = self._inspect_image(path)
            except AppearanceServiceError:
                continue
            if suffix != path.suffix.lower():
                continue
            wallpapers.append(self._wallpaper_item(path, content_type, width, height))
        return sorted(wallpapers, key=lambda item: str(item["id"]), reverse=True)

    def _inspect_image(self, path: Path) -> tuple[str, str, int, int]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                    width, height = image.size
                    if (
                        width <= 0
                        or height <= 0
                        or width * height > MAX_WALLPAPER_PIXELS
                    ):
                        raise AppearanceServiceError(
                            "Wallpaper dimensions are not supported"
                        )
                    detected = _IMAGE_FORMATS.get((image.format or "").upper())
        except AppearanceServiceError:
            raise
        except (
            OSError,
            UnidentifiedImageError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise AppearanceServiceError("Unsupported wallpaper image") from exc
        if detected is None:
            raise AppearanceServiceError("Wallpaper must be JPEG, PNG, WebP, or GIF")
        return *detected, width, height

    def _build_thumbnail(self, source: Path, wallpaper_id: str) -> None:
        target = self._thumbnail_path(wallpaper_id)
        temporary = target.with_suffix(".webp.tmp")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source) as image:
                    image.seek(0)
                    thumbnail = ImageOps.exif_transpose(image).copy()
            thumbnail.thumbnail(
                (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE),
                _THUMBNAIL_RESAMPLE,
            )
            thumbnail.save(temporary, "WEBP", quality=72, method=4)
            temporary.replace(target)
        except (
            OSError,
            UnidentifiedImageError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise AppearanceServiceError(
                "Unable to create wallpaper thumbnail"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _resolve_wallpaper(self, wallpaper_id: str) -> Path:
        self._validate_wallpaper_id(wallpaper_id)
        matches = list(self.wallpaper_dir.glob(f"{wallpaper_id}.*"))
        if len(matches) != 1 or not matches[0].is_file() or matches[0].is_symlink():
            raise AppearanceServiceError("Wallpaper was not found")
        path = matches[0]
        if path.suffix.lower() not in _WALLPAPER_SUFFIXES:
            raise AppearanceServiceError("Wallpaper was not found")
        return path

    @staticmethod
    def _validate_wallpaper_id(wallpaper_id: str) -> None:
        if len(wallpaper_id) != 32 or any(
            char not in "0123456789abcdef" for char in wallpaper_id
        ):
            raise AppearanceServiceError("Invalid wallpaper ID")

    @staticmethod
    def _content_type_for_path(path: Path) -> str:
        for suffix, content_type in _IMAGE_FORMATS.values():
            if path.suffix.lower() == suffix:
                return content_type
        raise AppearanceServiceError("Unsupported wallpaper image")

    def _wallpaper_item(
        self,
        path: Path,
        content_type: str,
        width: int,
        height: int,
    ) -> dict[str, int | str]:
        wallpaper_id = path.stem
        return {
            "id": wallpaper_id,
            "content_type": content_type,
            "width": width,
            "height": height,
            "image_url": f"/api/v1/appearance/wallpapers/{wallpaper_id}",
            "thumbnail_url": f"/api/v1/appearance/wallpapers/{wallpaper_id}/thumbnail",
        }

    def _thumbnail_path(self, wallpaper_id: str) -> Path:
        return self.thumbnail_dir / f"{wallpaper_id}.webp"

    def _ensure_directories(self) -> None:
        self.wallpaper_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
