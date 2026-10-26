"""Managed Dashboard wallpaper assets and appearance settings."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.datastructures import UploadFile

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_dashboard_path

from .appearance_colors import DEFAULT_THEME_COLORS, extract_theme_colors

MAX_WALLPAPER_BYTES = 32 * 1024 * 1024
MAX_WALLPAPER_PIXELS = 36_000_000
MAX_LEGACY_WALLPAPER_PIXELS = 40_000_000
THUMBNAIL_MAX_SIDE = 480
STATE_VERSION = 1
STATE_FILENAME = "state.json"
ORIENTATIONS = frozenset({"landscape", "portrait"})
STORED_ORIENTATIONS = ORIENTATIONS | {"both"}
FITS = frozenset({"cover", "contain"})
POSITIONS = frozenset(
    {"center center", "center top", "center bottom", "left center", "right center"}
)
TEXT_ENHANCEMENT_MODES = frozenset({"off", "soft_shadow", "stroke"})

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "landscape_wallpaper_id": "",
    "portrait_wallpaper_id": "",
    "fit": "cover",
    "position": "center center",
    "blur": 0,
    "brightness": 1.0,
    "dim": 0.5,
    "surface_opacity": 0.35,
    "surface_blur": 14,
    "saturation": 1.0,
    "grayscale": 0.0,
    "random_on_load": False,
    "rotation_enabled": False,
    "rotation_interval_minutes": 30,
    "auto_theme": False,
    "text_enhancement": "soft_shadow",
    "text_enhancement_strength": 1.0,
    "mobile_sidebar_blur": 18,
}

_CHUNK_SIZE = 64 * 1024
_THUMBNAIL_QUALITY = 78
_PROCESS_CONCURRENCY = 2
_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"),
}
_WALLPAPER_SUFFIXES = frozenset(suffix for suffix, _ in _IMAGE_FORMATS.values())
_THUMBNAIL_RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
_ANIMATED_FORMATS = frozenset({"GIF", "WEBP"})
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")


class AppearanceServiceError(ValueError):
    """Raised when a Dashboard appearance operation cannot be completed."""


class _ProcessedImage:
    __slots__ = ("animated", "colors", "content_type", "suffix", "width", "height")

    def __init__(
        self,
        *,
        suffix: str,
        content_type: str,
        width: int,
        height: int,
        animated: bool,
        colors: tuple[str, str],
    ) -> None:
        self.suffix = suffix
        self.content_type = content_type
        self.width = width
        self.height = height
        self.animated = animated
        self.colors = colors


class AppearanceService:
    """Store wallpapers, metadata, and appearance settings under the data root."""

    def __init__(self, data_root: Path | None = None) -> None:
        appearance_root = (
            Path(get_astrbot_dashboard_path()) / "appearance"
            if data_root is None
            else data_root / "dashboard" / "appearance"
        )
        self.wallpaper_dir = appearance_root / "wallpapers"
        self.thumbnail_dir = appearance_root / "thumbnails"
        self.state_path = appearance_root / STATE_FILENAME
        self._state: dict[str, Any] | None = None
        self._state_lock = asyncio.Lock()
        self._processing_semaphore = asyncio.Semaphore(_PROCESS_CONCURRENCY)

    async def get_settings(self) -> dict[str, Any]:
        await self._ensure_state()
        async with self._state_lock:
            return dict(self._settings())

    async def update_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        await self._ensure_state()
        async with self._state_lock:
            current = self._settings()
            merged = {**current, **dict(payload)}
            settings = self._normalize_settings(merged)
            self._reconcile_selections(settings)
            self._state_dict()["settings"] = settings
            await asyncio.to_thread(self._save_state)
            return dict(settings)

    async def list_wallpapers(
        self, orientation: str | None = None
    ) -> list[dict[str, Any]]:
        if orientation is not None and orientation not in ORIENTATIONS:
            raise AppearanceServiceError("Invalid wallpaper orientation")
        await self._ensure_state()
        async with self._state_lock:
            wallpapers = self._state_dict()["wallpapers"]
            items = [
                self._wallpaper_item(item)
                for item in wallpapers.values()
                if orientation is None
                or item.get("orientation") in {orientation, "both"}
            ]
            return sorted(
                items,
                key=lambda item: (str(item.get("created_at", "")), str(item["id"])),
                reverse=True,
            )

    async def save_wallpaper(
        self,
        upload: UploadFile,
        orientation: str,
    ) -> dict[str, Any]:
        if orientation not in ORIENTATIONS:
            await upload.close()
            raise AppearanceServiceError(
                "Wallpaper orientation must be landscape or portrait"
            )
        try:
            await self._ensure_state()
            self._ensure_directories()
        except BaseException:
            await upload.close()
            raise
        wallpaper_id = uuid4().hex
        temporary_path = self.wallpaper_dir / f".{uuid4().hex}.upload"
        target_path: Path | None = None
        thumbnail_path = self._thumbnail_path(wallpaper_id)
        original_name = self._safe_original_name(upload.filename)
        committed = False
        try:
            await self._write_upload(upload, temporary_path)
            async with self._processing_semaphore:
                processed = await asyncio.to_thread(
                    self._process_image,
                    temporary_path,
                    wallpaper_id,
                )
            target_path = self.wallpaper_dir / f"{wallpaper_id}{processed.suffix}"
            size_bytes = temporary_path.stat().st_size
            await asyncio.to_thread(os.replace, temporary_path, target_path)
            item = {
                "id": wallpaper_id,
                "content_type": processed.content_type,
                "width": processed.width,
                "height": processed.height,
                "orientation": orientation,
                "original_name": original_name,
                "created_at": datetime.now(UTC).isoformat(),
                "size_bytes": size_bytes,
                "animated": processed.animated,
                "theme_primary": processed.colors[0],
                "theme_secondary": processed.colors[1],
            }
            async with self._state_lock:
                self._state_dict()["wallpapers"][wallpaper_id] = item
                try:
                    await asyncio.to_thread(self._save_state)
                except Exception:
                    self._state_dict()["wallpapers"].pop(wallpaper_id, None)
                    raise
                committed = True
            return self._wallpaper_item(item)
        except AppearanceServiceError:
            raise
        except OSError as exc:
            raise AppearanceServiceError("Unable to save wallpaper") from exc
        finally:
            await upload.close()
            temporary_path.unlink(missing_ok=True)
            if not committed:
                if target_path is not None:
                    target_path.unlink(missing_ok=True)
                thumbnail_path.unlink(missing_ok=True)

    async def delete_wallpaper(self, wallpaper_id: str) -> None:
        await self._ensure_state()
        path = await asyncio.to_thread(self._resolve_wallpaper, wallpaper_id)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError as exc:
            raise AppearanceServiceError("Wallpaper was not found") from exc
        try:
            thumbnail = await asyncio.to_thread(
                self._resolve_thumbnail,
                wallpaper_id,
            )
        except AppearanceServiceError:
            thumbnail = None
        if thumbnail is not None:
            try:
                await asyncio.to_thread(thumbnail.unlink)
            except OSError:
                logger.warning("Unable to remove Dashboard wallpaper thumbnail")
        async with self._state_lock:
            self._state_dict()["wallpapers"].pop(wallpaper_id, None)
            self._reconcile_selections(self._settings())
            await asyncio.to_thread(self._save_state)

    async def resolve_wallpaper(self, wallpaper_id: str) -> tuple[Path, str]:
        path = await asyncio.to_thread(self._resolve_wallpaper, wallpaper_id)
        return path, self._content_type_for_path(path)

    async def resolve_thumbnail(self, wallpaper_id: str) -> tuple[Path, str]:
        path = await asyncio.to_thread(self._resolve_thumbnail, wallpaper_id)
        return path, "image/webp"

    async def _ensure_state(self) -> None:
        if self._state is not None:
            return
        async with self._state_lock:
            if self._state is not None:
                return
            await asyncio.to_thread(self._ensure_state_sync)

    def _ensure_state_sync(self) -> None:
        self._ensure_directories()
        state = self._load_state()
        changed = False
        wallpapers = state["wallpapers"]
        assets = self._asset_paths()
        for wallpaper_id, path in assets.items():
            metadata = wallpapers.get(wallpaper_id)
            if self._metadata_is_usable(metadata, path, wallpaper_id):
                continue
            try:
                item = self._migrate_asset(wallpaper_id, path, metadata)
            except AppearanceServiceError as exc:
                logger.warning(
                    "Skipping invalid Dashboard wallpaper %s: %s",
                    wallpaper_id,
                    exc,
                )
                # Keep usable metadata when the rebuild failed transiently, but
                # drop an entry the listing would raise on because the
                # migration could not supply fields it is missing.
                try:
                    self._wallpaper_item(metadata)
                except TypeError, ValueError, KeyError, OverflowError:
                    if wallpapers.pop(wallpaper_id, None) is not None:
                        changed = True
                continue
            wallpapers[wallpaper_id] = item
            changed = True

        for wallpaper_id in list(wallpapers):
            if wallpaper_id not in assets:
                wallpapers.pop(wallpaper_id, None)
                changed = True

        state["settings"] = self._normalize_settings(state.get("settings"))
        self._state = state
        if self._reconcile_selections(state["settings"]):
            changed = True
        if changed:
            self._save_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.is_file():
            try:
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            except OSError, ValueError:
                logger.warning("Ignoring unreadable Dashboard appearance state")
            else:
                if isinstance(raw, dict):
                    wallpapers = raw.get("wallpapers")
                    try:
                        revision = int(raw.get("revision", 0))
                    except TypeError, ValueError, OverflowError:
                        revision = 0
                    return {
                        "version": STATE_VERSION,
                        "revision": revision,
                        "settings": self._normalize_settings(raw.get("settings")),
                        "wallpapers": {
                            str(key): value
                            for key, value in (
                                wallpapers.items()
                                if isinstance(wallpapers, dict)
                                else []
                            )
                            if isinstance(value, dict)
                            and self._is_wallpaper_id(str(key))
                        },
                    }
        return {
            "version": STATE_VERSION,
            "revision": 0,
            "settings": dict(DEFAULT_SETTINGS),
            "wallpapers": {},
        }

    def _save_state(self) -> None:
        self._ensure_directories()
        state = self._state_dict()
        state["revision"] = int(state.get("revision", 0)) + 1
        temporary = self.state_path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.state_path)
        except OSError as exc:
            raise AppearanceServiceError("Unable to save appearance state") from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _state_dict(self) -> dict[str, Any]:
        if self._state is None:
            raise RuntimeError("Appearance state is not loaded")
        return self._state

    def _settings(self) -> dict[str, Any]:
        return self._state_dict()["settings"]

    def _asset_paths(self) -> dict[str, Path]:
        if not self.wallpaper_dir.is_dir():
            return {}
        assets: dict[str, Path] = {}
        for path in self.wallpaper_dir.iterdir():
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() not in _WALLPAPER_SUFFIXES
            ):
                continue
            wallpaper_id = path.stem
            if self._is_wallpaper_id(wallpaper_id):
                assets[wallpaper_id] = path
        return assets

    def _metadata_is_usable(
        self,
        metadata: Any,
        path: Path,
        wallpaper_id: str,
    ) -> bool:
        if not isinstance(metadata, dict):
            return False
        if str(metadata.get("id", "")) != wallpaper_id:
            return False
        if metadata.get("content_type") not in {
            content_type for _, content_type in _IMAGE_FORMATS.values()
        }:
            return False
        if metadata.get("orientation") not in STORED_ORIENTATIONS:
            return False
        for key in ("theme_primary", "theme_secondary"):
            value = metadata.get(key)
            if not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
                return False
        raw_width: Any = metadata.get("width")
        raw_height: Any = metadata.get("height")
        raw_size: Any = metadata.get("size_bytes", 0)
        try:
            width = int(raw_width)
            height = int(raw_height)
            size_bytes = int(raw_size)
        except TypeError, ValueError, OverflowError:
            return False
        if width <= 0 or height <= 0 or size_bytes < 0:
            return False
        if not self._thumbnail_path(wallpaper_id).is_file():
            return False
        return True

    def _migrate_asset(
        self,
        wallpaper_id: str,
        path: Path,
        metadata: Any,
    ) -> dict[str, Any]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    fmt = (image.format or "").upper()
                    width, height = image.size
                    animated = bool(getattr(image, "is_animated", False)) and (
                        getattr(image, "n_frames", 1) > 1
                    )
            stat_result = path.stat()
        except (
            OSError,
            UnidentifiedImageError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise AppearanceServiceError("Unsupported wallpaper image") from exc
        detected = _IMAGE_FORMATS.get(fmt)
        if detected is None:
            raise AppearanceServiceError("Unsupported wallpaper image")
        if width <= 0 or height <= 0 or width * height > MAX_LEGACY_WALLPAPER_PIXELS:
            raise AppearanceServiceError("Wallpaper dimensions are not supported")
        thumbnail = self._thumbnail_path(wallpaper_id)
        if not thumbnail.is_file():
            self._build_thumbnail(path, thumbnail)
        colors = self._colors_from_thumbnail(thumbnail)
        orientation = (
            metadata.get("orientation")
            if isinstance(metadata, dict)
            and metadata.get("orientation") in STORED_ORIENTATIONS
            else "both"
        )
        raw_primary = (
            metadata.get("theme_primary") if isinstance(metadata, dict) else None
        )
        raw_secondary = (
            metadata.get("theme_secondary") if isinstance(metadata, dict) else None
        )
        theme_primary = (
            raw_primary
            if isinstance(raw_primary, str) and _HEX_COLOR_RE.fullmatch(raw_primary)
            else colors[0]
        )
        theme_secondary = (
            raw_secondary
            if isinstance(raw_secondary, str) and _HEX_COLOR_RE.fullmatch(raw_secondary)
            else colors[1]
        )
        item = {
            "id": wallpaper_id,
            "content_type": detected[1],
            "width": width,
            "height": height,
            "orientation": orientation,
            "original_name": (
                str(metadata.get("original_name", ""))[:200]
                if isinstance(metadata, dict)
                else ""
            ),
            "created_at": (
                str(metadata.get("created_at", ""))
                if isinstance(metadata, dict) and metadata.get("created_at")
                else datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()
            ),
            "size_bytes": stat_result.st_size,
            "animated": animated,
            "theme_primary": theme_primary,
            "theme_secondary": theme_secondary,
        }
        return item

    def _process_image(self, path: Path, wallpaper_id: str) -> _ProcessedImage:
        thumbnail_path = self._thumbnail_path(wallpaper_id)
        temporary = thumbnail_path.with_suffix(".webp.tmp")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    fmt = (image.format or "").upper()
                    width, height = image.size
                    if (
                        width <= 0
                        or height <= 0
                        or width * height > MAX_WALLPAPER_PIXELS
                    ):
                        raise AppearanceServiceError(
                            "Wallpaper dimensions are not supported"
                        )
                    image.verify()
                with Image.open(path) as image:
                    if fmt == "JPEG":
                        image.draft("RGB", (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
                    image.seek(0)
                    image.thumbnail(
                        (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE),
                        _THUMBNAIL_RESAMPLE,
                    )
                    thumbnail = ImageOps.exif_transpose(image)
                    thumbnail = thumbnail.convert("RGB")
                    thumbnail.save(
                        temporary,
                        "WEBP",
                        quality=_THUMBNAIL_QUALITY,
                        method=4,
                    )
                    colors = extract_theme_colors(thumbnail)
                    animated = bool(getattr(image, "is_animated", False)) and (
                        getattr(image, "n_frames", 1) > 1
                    )
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
        detected = _IMAGE_FORMATS.get(fmt)
        if detected is None:
            raise AppearanceServiceError("Wallpaper must be JPEG, PNG, WebP, or GIF")
        try:
            temporary.replace(thumbnail_path)
        except OSError as exc:
            raise AppearanceServiceError("Unable to save wallpaper thumbnail") from exc
        finally:
            temporary.unlink(missing_ok=True)
        return _ProcessedImage(
            suffix=detected[0],
            content_type=detected[1],
            width=width,
            height=height,
            animated=animated and fmt in _ANIMATED_FORMATS,
            colors=(colors.primary, colors.secondary),
        )

    def _build_thumbnail(self, source: Path, target: Path) -> None:
        temporary = target.with_suffix(".webp.tmp")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source) as image:
                    if (image.format or "").upper() == "JPEG":
                        image.draft("RGB", (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
                    image.seek(0)
                    image.thumbnail(
                        (THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE),
                        _THUMBNAIL_RESAMPLE,
                    )
                    thumbnail = ImageOps.exif_transpose(image).convert("RGB")
                    thumbnail.save(
                        temporary,
                        "WEBP",
                        quality=_THUMBNAIL_QUALITY,
                        method=4,
                    )
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

    def _colors_from_thumbnail(self, thumbnail: Path) -> tuple[str, str]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(thumbnail) as image:
                    colors = extract_theme_colors(image)
        except (
            OSError,
            UnidentifiedImageError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            return DEFAULT_THEME_COLORS
        return colors.primary, colors.secondary

    async def _write_upload(self, upload: UploadFile, destination: Path) -> None:
        size = 0
        try:
            with destination.open("xb") as output:
                while chunk := await upload.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_WALLPAPER_BYTES:
                        raise AppearanceServiceError("Wallpaper must not exceed 32 MiB")
                    await asyncio.to_thread(output.write, chunk)
        except AppearanceServiceError:
            raise
        except OSError as exc:
            raise AppearanceServiceError("Unable to receive wallpaper") from exc
        if size == 0:
            raise AppearanceServiceError("Wallpaper must not be empty")

    def _resolve_wallpaper(self, wallpaper_id: str) -> Path:
        self._validate_wallpaper_id(wallpaper_id)
        path = self._asset_paths().get(wallpaper_id)
        if path is None:
            raise AppearanceServiceError("Wallpaper was not found")
        return path

    def _resolve_thumbnail(self, wallpaper_id: str) -> Path:
        self._validate_wallpaper_id(wallpaper_id)
        if not self.thumbnail_dir.is_dir():
            raise AppearanceServiceError("Wallpaper thumbnail was not found")
        expected = f"{wallpaper_id}.webp"
        for path in self.thumbnail_dir.iterdir():
            if path.name == expected and path.is_file() and not path.is_symlink():
                return path
        raise AppearanceServiceError("Wallpaper thumbnail was not found")

    @staticmethod
    def _validate_wallpaper_id(wallpaper_id: str) -> None:
        if not AppearanceService._is_wallpaper_id(wallpaper_id):
            raise AppearanceServiceError("Invalid wallpaper ID")

    @staticmethod
    def _is_wallpaper_id(wallpaper_id: str) -> bool:
        return len(wallpaper_id) == 32 and all(
            char in "0123456789abcdef" for char in wallpaper_id
        )

    @staticmethod
    def _content_type_for_path(path: Path) -> str:
        for suffix, content_type in _IMAGE_FORMATS.values():
            if path.suffix.lower() == suffix:
                return content_type
        raise AppearanceServiceError("Unsupported wallpaper image")

    def _wallpaper_item(self, item: Mapping[str, Any]) -> dict[str, Any]:
        wallpaper_id = str(item["id"])
        return {
            "id": wallpaper_id,
            "content_type": str(item["content_type"]),
            "width": int(item["width"]),
            "height": int(item["height"]),
            "orientation": str(item.get("orientation", "both")),
            "original_name": str(item.get("original_name", "")),
            "created_at": str(item.get("created_at", "")),
            "size_bytes": int(item.get("size_bytes", 0)),
            "animated": bool(item.get("animated", False)),
            "theme_primary": str(item.get("theme_primary", DEFAULT_THEME_COLORS[0])),
            "theme_secondary": str(
                item.get("theme_secondary", DEFAULT_THEME_COLORS[1])
            ),
            "image_url": f"/api/v1/appearance/wallpapers/{wallpaper_id}",
            "thumbnail_url": f"/api/v1/appearance/wallpapers/{wallpaper_id}/thumbnail",
        }

    def _normalize_settings(self, value: Any) -> dict[str, Any]:
        settings = dict(DEFAULT_SETTINGS)
        if not isinstance(value, Mapping):
            return settings
        for key in DEFAULT_SETTINGS:
            if key in value:
                settings[key] = value[key]
        settings["enabled"] = settings["enabled"] is True
        settings["random_on_load"] = settings["random_on_load"] is True
        settings["rotation_enabled"] = settings["rotation_enabled"] is True
        settings["auto_theme"] = settings["auto_theme"] is True
        for key in ("landscape_wallpaper_id", "portrait_wallpaper_id"):
            candidate = settings.get(key)
            settings[key] = candidate if isinstance(candidate, str) else ""
            if settings[key] and not self._is_wallpaper_id(settings[key]):
                settings[key] = ""
        settings["fit"] = (
            settings["fit"]
            if isinstance(settings["fit"], str) and settings["fit"] in FITS
            else DEFAULT_SETTINGS["fit"]
        )
        settings["position"] = (
            settings["position"]
            if isinstance(settings["position"], str)
            and settings["position"] in POSITIONS
            else DEFAULT_SETTINGS["position"]
        )
        settings["text_enhancement"] = (
            settings["text_enhancement"]
            if isinstance(settings["text_enhancement"], str)
            and settings["text_enhancement"] in TEXT_ENHANCEMENT_MODES
            else DEFAULT_SETTINGS["text_enhancement"]
        )
        settings["blur"] = int(self._clamp(settings["blur"], 0, 40, 0))
        settings["surface_blur"] = int(self._clamp(settings["surface_blur"], 0, 40, 0))
        settings["mobile_sidebar_blur"] = int(
            self._clamp(settings["mobile_sidebar_blur"], 0, 40, 0)
        )
        settings["rotation_interval_minutes"] = int(
            self._clamp(settings["rotation_interval_minutes"], 1, 1440, 30)
        )
        settings["brightness"] = self._clamp(settings["brightness"], 0.5, 1.5, 1.0)
        settings["dim"] = self._clamp(settings["dim"], 0, 0.9, 0.5)
        settings["surface_opacity"] = self._clamp(
            settings["surface_opacity"],
            0,
            1,
            DEFAULT_SETTINGS["surface_opacity"],
        )
        settings["saturation"] = self._clamp(settings["saturation"], 0, 2, 1.0)
        settings["grayscale"] = self._clamp(settings["grayscale"], 0, 1, 0.0)
        settings["text_enhancement_strength"] = self._clamp(
            settings["text_enhancement_strength"], 0, 2, 1.0
        )
        return settings

    def _reconcile_selections(self, settings: dict[str, Any]) -> bool:
        wallpapers = self._state_dict()["wallpapers"] if self._state else {}
        changed = False
        for key, orientation in (
            ("landscape_wallpaper_id", "landscape"),
            ("portrait_wallpaper_id", "portrait"),
        ):
            wallpaper_id = settings.get(key)
            item = wallpapers.get(wallpaper_id) if wallpaper_id else None
            if item is None or item.get("orientation") not in {orientation, "both"}:
                if settings.get(key):
                    changed = True
                settings[key] = ""
        return changed

    @staticmethod
    def _clamp(value: Any, minimum: float, maximum: float, fallback: float) -> float:
        try:
            parsed = float(value)
        except TypeError, ValueError, OverflowError:
            return fallback
        if math.isnan(parsed) or parsed in {float("inf"), float("-inf")}:
            return fallback
        return min(max(parsed, minimum), maximum)

    @staticmethod
    def _safe_original_name(filename: str | None) -> str:
        if not filename:
            return ""
        name = Path(filename.replace("\\", "/")).name
        name = "".join(char for char in name if char.isprintable())
        return name[:200]

    def _thumbnail_path(self, wallpaper_id: str) -> Path:
        return self.thumbnail_dir / f"{wallpaper_id}.webp"

    def _ensure_directories(self) -> None:
        self.wallpaper_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
