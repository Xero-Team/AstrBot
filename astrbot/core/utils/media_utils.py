"""Media file utilities.

Provides shared media reference materialization, format conversion, duration
probing, and image compression helpers.
"""

import asyncio
import base64
import binascii
import io
import math
import mimetypes
import os
import statistics
import subprocess
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse, urlsplit
from urllib.request import url2pathname

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.tencent_record_helper import (
    tencent_silk_to_wav,
    wav_to_tencent_silk,
)

IMAGE_COMPRESS_DEFAULT_MAX_SIZE = 1024
IMAGE_COMPRESS_DEFAULT_QUALITY = 85
IMAGE_COMPRESS_DEFAULT_OPTIMIZE = True
IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_MB = 1.0
PROVIDER_JPEG_MAX_ANIMATED_FRAMES = 8
PROVIDER_JPEG_MAX_COMPOSE_FRAMES = 64
PROVIDER_JPEG_STATIC_HAMMING = 12
PROVIDER_JPEG_DEDUP_HAMMING = 16
PROVIDER_JPEG_MU_REF = 16 / 64
PROVIDER_JPEG_T_REF_SECONDS = 8.0
PROVIDER_JPEG_BLANK_VARIANCE = 12
PROVIDER_JPEG_DEFAULT_DELAY_MS = 100
PROVIDER_JPEG_HAMMING_CAP = 32
PROVIDER_JPEG_BLINK_OCCUPANCY = 0.8

MEDIA_MIME_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/flac": ".flac",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "audio/silk": ".silk",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

IMAGE_FORMAT_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "AVIF": "image/avif",
}

AUDIO_FORMAT_MIME_TYPES = {
    "aac": "audio/aac",
    "amr": "audio/amr",
    "flac": "audio/flac",
    "mp3": "audio/mp3",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "silk": "audio/silk",
    "tencent_silk": "audio/silk",
    "wav": "audio/wav",
}

DEFAULT_MEDIA_SUFFIXES = {
    "audio": ".wav",
    "image": ".bin",
    "video": ".mp4",
    "file": ".bin",
}


type MediaRefStr = str
"""
A media reference string accepted by MediaResolver: local path, file URI, HTTP(S),
base64://, or data URI.

Examples:
    Local path: ``/tmp/image.png``
    File URI: ``file:///tmp/image.png``
    HTTP(S) URL: ``https://example.com/image.png``
    base64:// payload: ``base64://iVBORw0KGgo...``
    Data URI: ``data:image/png;base64,iVBORw0KGgo...``
"""


@dataclass(slots=True)
class ResolvedMediaData:
    """Base64 media bytes plus the metadata needed by provider payloads.

    Attributes:
        base64_data: Raw base64 payload without a ``data:`` URI prefix.
        mime_type: MIME type to send with provider payloads.
        format: Optional normalized media format, such as ``wav`` for audio.
    """

    base64_data: str
    mime_type: str
    format: str | None = None

    def to_bytes(self) -> bytes:
        """Decode the base64 payload, accepting missing padding."""
        return _decode_base64_payload(
            self.base64_data,
            error_message="invalid resolved media base64 data",
        )

    def to_data_url(self) -> str:
        """Return a ``data:<mime>;base64,...`` URL for multimodal providers."""
        return f"data:{self.mime_type};base64,{self.base64_data}"


@dataclass(slots=True)
class _LocalMediaFile:
    path: Path
    mime_type: str | None = None
    cleanup_paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class ResolvedMediaFile:
    """A media reference resolved to a local path.

    ``cleanup_paths`` contains temporary files owned by the resolver. Callers that
    use ``MediaResolver.as_path()`` get automatic cleanup; callers that need to
    keep a path after the resolver returns should use ``MediaResolver.to_path()``.
    """

    source_ref: MediaRefStr
    media_type: str
    path: Path
    mime_type: str | None = None
    format: str | None = None
    cleanup_paths: list[Path] = field(default_factory=list)

    def read_bytes(self) -> bytes:
        """Read the resolved local file."""
        return self.path.read_bytes()

    def to_base64(self) -> str:
        """Read the resolved local file and return raw base64 data."""
        return base64.b64encode(self.read_bytes()).decode("utf-8")

    def to_data_url(self) -> str:
        """Read the resolved local file and return a data URL."""
        mime_type = self.mime_type or "application/octet-stream"
        return f"data:{mime_type};base64,{self.to_base64()}"

    def open(self, mode: str = "rb"):
        """Open the resolved local file."""
        return self.path.open(mode)

    def detach(self) -> None:
        """Keep temporary files alive after resolver cleanup would normally run."""

        self.cleanup_paths.clear()

    def cleanup(self) -> None:
        _cleanup_paths(self.cleanup_paths)


@dataclass(slots=True)
class ComposedFrame:
    """One fully composited RGB frame used for provider JPEG sampling.

    Attributes:
        image: Flattened RGB pixels, never a raw GIF patch.
        duration_ms: Frame delay in milliseconds. Missing or zero delays are
            stored as ``PROVIDER_JPEG_DEFAULT_DELAY_MS``.
        global_hash: 64-bit difference hash of the full frame.
        tile_hashes: Difference hashes of the four 2x2 quadrants.
    """

    image: PILImage.Image
    duration_ms: int
    global_hash: int
    tile_hashes: tuple[int, int, int, int]
    color_hash: int
    tile_colors: tuple[int, int, int, int]

    @classmethod
    def from_image(cls, image: PILImage.Image, duration_ms: int) -> ComposedFrame:
        """Build a composed frame, flattening alpha and hashing the result.

        Args:
            image: Source frame pixels.
            duration_ms: Frame delay in milliseconds.

        Returns:
            A composed RGB frame with global and tile dhashes.
        """
        rgb = image if image.mode == "RGB" else _flatten_alpha_on_white(image)
        delay = duration_ms if duration_ms > 0 else PROVIDER_JPEG_DEFAULT_DELAY_MS
        return cls(
            rgb,
            delay,
            _dhash64(rgb),
            _tile_dhashes(rgb),
            _mean_rgb_pack(rgb),
            _tile_color_packs(rgb),
        )


def is_file_uri(value: object) -> bool:
    """Return whether a value is a ``file:`` URI.

    Args:
        value: Candidate media reference or local path.

    Returns:
        ``True`` only for string values whose parsed URI scheme is ``file``.
    """

    if not isinstance(value, str):
        return False
    try:
        return urlsplit(value).scheme.lower() == "file"
    except ValueError:
        return False


def file_uri_to_path(file_uri: MediaRefStr) -> str:
    """Normalize file URIs to local filesystem paths.

    Args:
        file_uri: A ``file:`` URI or a plain filesystem path.

    Returns:
        The local filesystem path decoded with standard-library URL path rules.
        Non-``file:`` inputs are returned unchanged for convenience.
    """

    if not is_file_uri(file_uri):
        return file_uri

    parsed = urlparse(file_uri)
    netloc = unquote(parsed.netloc or "")
    path = unquote(parsed.path or "")
    if netloc.lower().startswith("localhost") and len(netloc) > len("localhost"):
        netloc = netloc[len("localhost") :]
    if netloc and netloc.lower() != "localhost":
        if len(netloc) == 2 and netloc[1] == ":" and netloc[0].isalpha():
            return str(Path(url2pathname(f"{netloc}{path}")))
        if os.name == "nt":
            return str(Path(url2pathname(f"//{netloc}{path}")))
        return str(Path(f"//{netloc}{path}"))

    if os.name != "nt" and path.startswith("//"):
        # Older AstrBot builds generated file:////path for POSIX absolute paths.
        # Collapse the legacy prefix before url2pathname, which in Python 3.14
        # treats a leading // as a non-local authority and raises URLError.
        path = "/" + path.lstrip("/")
    path = url2pathname(path)
    # url2pathname keeps "/" on POSIX but converts it to "\" on Windows, so
    # accept both prefixes before the drive colon.
    if (
        len(path) >= 4
        and path[0] in ("/", "\\")
        and path[2] == ":"
        and path[1].isalpha()
    ):
        path = path[1:]
    return str(Path(path))


def _extension_from_mime_type(mime_type: str | None) -> str | None:
    """Return a filesystem suffix for a MIME type, if one is known."""
    if not mime_type:
        return None
    normalized = mime_type.split(";", 1)[0].strip().lower()
    if not normalized:
        return None
    return MEDIA_MIME_EXTENSIONS.get(normalized) or mimetypes.guess_extension(
        normalized
    )


def _temp_media_path(media_type: str, suffix: str) -> Path:
    """Create a unique path under AstrBot's temp directory for materialized media."""
    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    safe_media_type = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_" for char in media_type
    )
    return temp_dir / f"media_{safe_media_type}_{uuid.uuid4().hex}{suffix}"


def _parse_base64_data_uri(data_uri: str) -> tuple[str | None, bytes]:
    """Parse a base64 data URI and return ``(mime_type, decoded_bytes)``."""
    header, separator, payload = data_uri.partition(",")
    if not separator or not header.lower().startswith("data:"):
        raise ValueError("invalid data URI")

    header_body = header[5:]
    header_parts = header_body.split(";") if header_body else []
    mime_type = header_parts[0].strip() if header_parts and header_parts[0] else None
    if not any(part.lower() == "base64" for part in header_parts[1:]):
        raise ValueError("data URI is not base64 encoded")

    return mime_type, _decode_base64_payload(
        payload,
        error_message="invalid base64 data URI payload",
    )


def _decode_base64_payload(
    payload: str,
    *,
    error_message: str,
    validate: bool = False,
) -> bytes:
    """Decode a base64 payload while tolerating omitted padding.

    Args:
        payload: Base64 payload without a data URI header.
        error_message: Message to use when decoding fails.
        validate: Whether to ask ``base64.b64decode`` to reject non-base64
            characters.

    Returns:
        Decoded bytes.

    Raises:
        ValueError: Raised when the payload cannot be decoded.
    """
    payload = "".join(payload.split())
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)

    try:
        return base64.b64decode(payload, validate=validate)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(error_message) from exc


def describe_media_ref(media_ref: object | None) -> str:
    """Return a log-safe description of a media reference.

    Args:
        media_ref: Original media reference from a platform, plugin, or provider
            request. It may contain a signed URL or a large base64 payload.

    Returns:
        A short description that avoids logging query strings, tokens, and base64
        payload contents.
    """

    if not media_ref:
        return "<empty media ref>"
    if not isinstance(media_ref, str):
        return f"media ref type={type(media_ref).__name__}"

    ref_len = len(media_ref)
    if media_ref.startswith("data:"):
        header, _, payload = media_ref.partition(",")
        mime_type = header[5:].split(";", 1)[0] or "unknown"
        return f"data URI mime={mime_type!r} payload_len={len(payload)}"

    if media_ref.startswith("base64://"):
        return f"base64 media payload_len={len(media_ref.removeprefix('base64://'))}"

    parsed = urlparse(media_ref)
    if parsed.scheme in {"http", "https"}:
        filename = Path(unquote(parsed.path or "")).name
        suffix = f" file={filename!r}" if filename else ""
        return f"{parsed.scheme} URL host={parsed.netloc!r}{suffix} len={ref_len}"

    if is_file_uri(media_ref):
        filename = Path(file_uri_to_path(media_ref)).name
        return f"file URI name={filename!r} len={ref_len}"

    return f"local media path name={Path(media_ref).name!r} len={ref_len}"


def detect_image_mime_type(
    image_source: bytes | str | os.PathLike[str],
    *,
    default_mime_type: str | None = "image/jpeg",
) -> str | None:
    """Detect an image MIME type from bytes.

    Args:
        image_source: Encoded image bytes or a local image path to inspect.
        default_mime_type: MIME type to return when detection fails.

    Returns:
        The detected MIME type, or ``default_mime_type`` when detection fails or
        the format is unknown.
    """

    try:
        if isinstance(image_source, bytes):
            image_resource = io.BytesIO(image_source)
        else:
            image_resource = Path(image_source)
        with PILImage.open(image_resource) as image:
            image.verify()
            image_format = str(image.format or "").upper()
    except Exception:
        return default_mime_type

    return IMAGE_FORMAT_MIME_TYPES.get(image_format, default_mime_type)


async def detect_image_mime_type_async(
    image_source: bytes | str | os.PathLike[str],
    *,
    default_mime_type: str | None = "image/jpeg",
) -> str | None:
    """Detect an image MIME type without blocking the event loop."""

    return await asyncio.to_thread(
        detect_image_mime_type,
        image_source,
        default_mime_type=default_mime_type,
    )


def _guess_mime_type(path: Path, fallback: str | None = None) -> str | None:
    """Guess a MIME type from a filename, with an optional fallback."""
    return mimetypes.guess_type(path.name)[0] or fallback


def _cleanup_paths(cleanup_paths: list[Path] | None) -> None:
    """Best-effort cleanup for temporary files created by the resolver."""
    for cleanup_path in cleanup_paths or []:
        try:
            cleanup_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed to cleanup %s: %s", cleanup_path, exc)


async def _materialize_media_ref(
    media_ref: MediaRefStr,
    *,
    media_type: str = "file",
    default_suffix: str | None = None,
) -> _LocalMediaFile:
    """Resolve a plugin-facing media reference to a local file.

    Supported references: local paths, file:// URIs, http(s) URLs, base64://,
    and data:*;base64,... URIs.

    Args:
        media_ref: Original media reference from a platform, plugin, or history.
        media_type: Logical media family used for temp filenames and defaults.
        default_suffix: Suffix to use when the reference does not carry one.
    """

    cleanup_paths: list[Path] = []
    suffix = default_suffix or DEFAULT_MEDIA_SUFFIXES.get(media_type, ".bin")

    if media_ref.startswith(("http://", "https://")):
        parsed = urlparse(media_ref)
        source_suffix = Path(parsed.path).suffix
        target_suffix = source_suffix or suffix
        target_path = _temp_media_path(media_type, target_suffix)
        cleanup_paths.append(target_path)
        try:
            await download_file(media_ref, str(target_path))
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise
        mime_type = _guess_mime_type(target_path)
        if media_type == "image" and not source_suffix:
            detected_mime_type = detect_image_mime_type(
                target_path,
                default_mime_type=None,
            )
            detected_suffix = _extension_from_mime_type(detected_mime_type)
            if detected_suffix and detected_suffix != target_path.suffix.lower():
                detected_path = target_path.with_suffix(detected_suffix)
                target_path.replace(detected_path)
                cleanup_paths[-1] = detected_path
                target_path = detected_path
            if detected_mime_type:
                mime_type = detected_mime_type
        return _LocalMediaFile(
            path=target_path,
            mime_type=mime_type,
            cleanup_paths=cleanup_paths,
        )

    if is_file_uri(media_ref):
        path = Path(file_uri_to_path(media_ref))
        return _LocalMediaFile(path=path, mime_type=_guess_mime_type(path))

    if media_ref.startswith("data:"):
        mime_type, media_bytes = _parse_base64_data_uri(media_ref)
        target_suffix = _extension_from_mime_type(mime_type) or suffix
        target_path = _temp_media_path(media_type, target_suffix)
        cleanup_paths.append(target_path)
        try:
            target_path.write_bytes(media_bytes)
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise
        return _LocalMediaFile(
            path=target_path,
            mime_type=mime_type,
            cleanup_paths=cleanup_paths,
        )

    if media_ref.startswith("base64://"):
        media_bytes = _decode_base64_payload(
            media_ref.removeprefix("base64://"),
            error_message="invalid base64 media payload",
        )
        mime_type = None
        target_suffix = suffix
        if media_type == "image":
            mime_type = detect_image_mime_type(media_bytes, default_mime_type=None)
            target_suffix = _extension_from_mime_type(mime_type) or suffix
        target_path = _temp_media_path(media_type, target_suffix)
        cleanup_paths.append(target_path)
        try:
            target_path.write_bytes(media_bytes)
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise
        return _LocalMediaFile(
            path=target_path,
            mime_type=mime_type,
            cleanup_paths=cleanup_paths,
        )

    path = Path(media_ref)
    path_exists = False
    try:
        path_exists = path.exists()
    except OSError:
        pass
    if path_exists:
        mime_type = _guess_mime_type(path)
        if media_type == "image" and mime_type is None:
            mime_type = detect_image_mime_type(path, default_mime_type=None)
        return _LocalMediaFile(path=path, mime_type=mime_type)

    compact_media_ref = "".join(media_ref.split())
    if compact_media_ref:
        try:
            _decode_base64_payload(
                compact_media_ref,
                error_message="invalid bare base64 media payload",
                validate=True,
            )
        except ValueError:
            pass
        else:
            raise ValueError(
                "bare base64 media payload is no longer supported; "
                "use base64:// or a data URI instead"
            )

    return _LocalMediaFile(path=path, mime_type=_guess_mime_type(path))


class MediaResolver:
    """Resolve, convert, and export media references.

    The resolver accepts local paths, file:// URIs, http(s) URLs, base64:// payloads,
    and data:*;base64,... URIs. Temporary paths are
    cleaned when using as_path(), while to_path() intentionally leaves returned
    paths alive for callers that need to hand them to platform SDKs.

    Args:
        media_ref: Source media reference. It may be a local path, ``file://`` URI,
            HTTP(S) URL, ``base64://`` payload, or base64 data URI.
        media_type: Logical media family. ``audio`` enables format conversion and
            defaults to WAV output; ``image`` enables image MIME detection.
        default_suffix: Fallback suffix for temporary files when the source does
            not expose one.
    """

    def __init__(
        self,
        media_ref: MediaRefStr,
        *,
        media_type: str = "file",
        default_suffix: str | None = None,
    ) -> None:
        self.media_ref = media_ref
        self.media_type = media_type
        self.default_suffix = default_suffix

    async def _resolve_path(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> ResolvedMediaFile:
        """Materialize the source and apply media-type-specific conversion.

        For audio, ``target_format`` controls the output format, including the
        QQ / Wechat / Wecom ``tencent_silk`` upload format. When it is not set, audio
        resolves to WAV unless ``preserve_mp3`` is true and the source already
        appears to be MP3.
        """
        local_file = await _materialize_media_ref(
            self.media_ref,
            media_type=self.media_type,
            default_suffix=self.default_suffix,
        )
        cleanup_paths = list(local_file.cleanup_paths)
        resolved_path = local_file.path
        mime_type = local_file.mime_type or _guess_mime_type(resolved_path)
        resolved_format = resolved_path.suffix.lower().lstrip(".") or None

        try:
            if self.media_type == "audio":
                audio_format = target_format
                if not audio_format:
                    audio_format = (
                        "mp3" if preserve_mp3 and resolved_format == "mp3" else "wav"
                    )

                if audio_format == "tencent_silk":
                    intermediate_cleanup_paths = list(cleanup_paths)
                    silk_path = _temp_media_path("audio", ".silk")
                    try:
                        wav_path = Path(await ensure_wav(str(resolved_path)))
                        if wav_path != resolved_path:
                            intermediate_cleanup_paths.append(wav_path)
                        duration = await wav_to_tencent_silk(
                            str(wav_path), str(silk_path)
                        )
                        if duration <= 0:
                            raise ValueError(
                                "Tencent Silk conversion returned empty duration"
                            )
                    except Exception:
                        _cleanup_paths([*intermediate_cleanup_paths, silk_path])
                        raise

                    _cleanup_paths(intermediate_cleanup_paths)
                    cleanup_paths = [silk_path]
                    resolved_path = silk_path
                    resolved_format = audio_format
                    mime_type = AUDIO_FORMAT_MIME_TYPES[resolved_format]
                else:
                    if audio_format == "wav":
                        converted_audio_path = Path(
                            await ensure_wav(str(resolved_path))
                        )
                    elif resolved_format == audio_format:
                        converted_audio_path = resolved_path
                    else:
                        converted_audio_path = Path(
                            await convert_audio_format(
                                str(resolved_path),
                                output_format=audio_format,
                            )
                        )

                    if converted_audio_path != resolved_path:
                        cleanup_paths.append(converted_audio_path)
                    resolved_path = converted_audio_path
                    resolved_format = audio_format
                    mime_type = AUDIO_FORMAT_MIME_TYPES.get(
                        resolved_format, "audio/wav"
                    )
        except Exception:
            _cleanup_paths(cleanup_paths)
            raise

        return ResolvedMediaFile(
            source_ref=self.media_ref,
            media_type=self.media_type,
            path=resolved_path,
            mime_type=mime_type,
            format=resolved_format,
            cleanup_paths=cleanup_paths,
        )

    @asynccontextmanager
    async def as_path(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> AsyncIterator[ResolvedMediaFile]:
        """Yield a resolved local file and clean resolver-owned temp files on exit.

        Use this when the consumer only needs the file during the context manager.
        For audio, pass ``target_format`` to force a format such as ``wav`` or
        ``tencent_silk``.
        """
        resolved = await self._resolve_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        )
        try:
            yield resolved
        finally:
            resolved.cleanup()

    async def to_path(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> str:
        """Return a resolved local path and keep temporary files alive.

        This is for message components and platform SDK calls that need a path
        after the resolver method returns. Callers or event cleanup should remove
        the returned temp file later.
        """
        resolved = await self._resolve_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        )
        resolved.detach()
        return str(resolved.path.resolve())

    async def to_bytes(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> bytes:
        """Resolve media, read bytes, and clean resolver-owned temp files."""
        async with self.as_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        ) as resolved:
            return resolved.read_bytes()

    async def to_base64(
        self,
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ) -> str:
        """Resolve media to raw base64 data without a data URI prefix."""
        return base64.b64encode(
            await self.to_bytes(
                target_format=target_format,
                preserve_mp3=preserve_mp3,
            )
        ).decode("utf-8")

    async def to_base64_data(
        self,
        *,
        strict: bool = False,
        target_format: str | None = None,
        preserve_mp3: bool = False,
        default_mime_type: str | None = "image/jpeg",
    ) -> ResolvedMediaData | None:
        """Resolve media to base64 data plus MIME metadata.

        Args:
            strict: Raise on invalid or unreadable media instead of returning
                ``None`` where the resolver can safely ignore the reference.
            target_format: Optional output format for audio conversion.
            preserve_mp3: Keep existing MP3 audio as MP3 when no target format is
                provided; otherwise audio defaults to WAV.
            default_mime_type: Fallback MIME type for base64:// image payloads
                whose bytes cannot be identified.
        """
        if self.media_type == "image":
            try:
                resolved_context = self.as_path(target_format=target_format)
                async with resolved_context as resolved:
                    try:
                        media_bytes = resolved.read_bytes()
                    except OSError:
                        if strict:
                            raise
                        return None

                    mime_type = detect_image_mime_type(
                        media_bytes,
                        default_mime_type=None,
                    )
                    if (
                        not mime_type
                        and resolved.mime_type
                        and resolved.mime_type.startswith("image/")
                    ):
                        mime_type = resolved.mime_type
                    if not mime_type and self.media_ref.startswith("base64://"):
                        mime_type = default_mime_type
                    if not mime_type:
                        if strict:
                            raise ValueError(
                                f"Invalid image file: {describe_media_ref(self.media_ref)}"
                            )
                        return None

                    return ResolvedMediaData(
                        base64_data=base64.b64encode(media_bytes).decode("utf-8"),
                        mime_type=mime_type,
                    )
            except ValueError:
                if strict:
                    raise
                return None

        async with self.as_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        ) as resolved:
            try:
                media_bytes = resolved.read_bytes()
            except OSError:
                if strict:
                    raise
                return None

            mime_type = resolved.mime_type or "application/octet-stream"
            return ResolvedMediaData(
                base64_data=base64.b64encode(media_bytes).decode("utf-8"),
                mime_type=mime_type,
                format=resolved.format,
            )

    async def to_data_url(
        self,
        *,
        strict: bool = False,
        target_format: str | None = None,
        preserve_mp3: bool = False,
        default_mime_type: str | None = "image/jpeg",
    ) -> str | None:
        """Resolve media directly to a provider-ready data URL."""
        resolved = await self.to_base64_data(
            strict=strict,
            target_format=target_format,
            preserve_mp3=preserve_mp3,
            default_mime_type=default_mime_type,
        )
        return resolved.to_data_url() if resolved else None

    @asynccontextmanager
    async def open(
        self,
        mode: str = "rb",
        *,
        target_format: str | None = None,
        preserve_mp3: bool = False,
    ):
        """Open resolved media as a file object inside a cleanup context."""
        async with self.as_path(
            target_format=target_format,
            preserve_mp3=preserve_mp3,
        ) as resolved:
            with resolved.open(mode) as file_obj:
                yield file_obj


async def resolve_image_ref_to_base64_data(
    image_ref: MediaRefStr,
    *,
    strict: bool = False,
    default_mime_type: str | None = "image/jpeg",
) -> ResolvedMediaData | None:
    """Resolve an image reference to base64 data and a detected MIME type.

    ``strict=False`` returns ``None`` for invalid images so provider payload
    assembly can skip bad image refs without failing the whole request.
    """

    return await MediaResolver(
        image_ref,
        media_type="image",
        default_suffix=".bin",
    ).to_base64_data(
        strict=strict,
        default_mime_type=default_mime_type,
    )


async def resolve_audio_ref_to_base64_data(
    audio_ref: MediaRefStr,
    *,
    preserve_mp3: bool = False,
    target_format: str | None = None,
) -> ResolvedMediaData:
    """Resolve an audio reference to base64 data.

    Audio is converted to WAV by default. Pass preserve_mp3=True for legacy
    provider payloads that intentionally keep MP3 input unchanged.
    ``target_format`` overrides both defaults when provided.
    """

    audio_data = await MediaResolver(
        audio_ref,
        media_type="audio",
        default_suffix=".wav",
    ).to_base64_data(
        target_format=target_format,
        preserve_mp3=preserve_mp3,
        strict=True,
    )
    if audio_data is None:
        raise ValueError(f"Invalid audio data: {describe_media_ref(audio_ref)}")
    return audio_data


async def resolve_media_ref_to_base64_data(
    media_ref: MediaRefStr,
    *,
    media_type: str,
    strict: bool = False,
) -> ResolvedMediaData | None:
    """Resolve a media reference to base64 data through one shared entrypoint.

    This helper keeps provider sources from knowing whether a reference is local,
    HTTP(S), ``base64://``, or a data URI.
    """

    if media_type == "image":
        return await resolve_image_ref_to_base64_data(media_ref, strict=strict)
    if media_type == "audio":
        return await resolve_audio_ref_to_base64_data(media_ref)

    return await MediaResolver(
        media_ref,
        media_type=media_type,
    ).to_base64_data(
        strict=strict,
    )


async def get_media_duration(file_path: str) -> int | None:
    """Probe media duration with ffprobe.

    Args:
        file_path: Local media file path.

    Returns:
        Duration in milliseconds, or ``None`` when probing fails.
    """
    try:
        # Probe duration with ffprobe.
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            duration_seconds = float(stdout.decode().strip())
            duration_ms = int(duration_seconds * 1000)
            logger.debug("Media duration detected: %sms", duration_ms)
            return duration_ms
        else:
            logger.warning("Failed to get media duration: %s", file_path)
            return None

    except FileNotFoundError:
        logger.warning(
            "ffprobe is not installed or not in PATH. "
            "Install ffmpeg: https://ffmpeg.org/"
        )
        return None
    except Exception as e:
        logger.warning("Error while probing media duration: %s", e)
        return None


async def convert_audio_to_opus(audio_path: str, output_path: str | None = None) -> str:
    """Convert an audio file to Opus format.

    Args:
        audio_path: Source audio file path.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted Opus file path.
    """
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="opus",
        output_path=output_path,
    )


async def convert_video_format(
    video_path: str, output_format: str = "mp4", output_path: str | None = None
) -> str:
    """Convert a video file with ffmpeg.

    Args:
        video_path: Source video file path.
        output_format: Target format, such as ``mp4``.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted video file path.

    Raises:
        Exception: Raised when ffmpeg is unavailable or conversion fails.
    """
    # Return early when the source already appears to be in the target format.
    if video_path.lower().endswith(f".{output_format}"):
        return video_path

    # Create an output path when the caller does not provide one.
    if output_path is None:
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(
            temp_dir,
            f"media_video_{uuid.uuid4().hex}.{output_format}",
        )

    try:
        # Convert the video with ffmpeg.
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # Remove a partial output file created by a failed ffmpeg run.
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logger.debug(
                        "Removed failed %s output file: %s",
                        output_format,
                        output_path,
                    )
                except OSError as e:
                    logger.warning(
                        "Failed to remove failed %s output file: %s",
                        output_format,
                        e,
                    )

            error_msg = stderr.decode() if stderr else "unknown error"
            logger.error("ffmpeg video conversion failed: %s", error_msg)
            raise Exception(f"ffmpeg conversion failed: {error_msg}")

        logger.debug(
            "Video converted successfully: %s -> %s",
            video_path,
            output_path,
        )
        return output_path

    except FileNotFoundError:
        logger.error(
            "ffmpeg is not installed or not in PATH. "
            "Install ffmpeg: https://ffmpeg.org/"
        )
        raise Exception("ffmpeg not found")
    except Exception as e:
        logger.error("Error while converting video format: %s", e)
        raise


async def convert_audio_format(
    audio_path: str,
    output_format: str = "amr",
    output_path: str | None = None,
) -> str:
    """Convert an audio file to the requested format with ffmpeg.

    Args:
        audio_path: Source audio file path.
        output_format: Target format, such as ``amr``, ``ogg``, ``opus``, or
            ``wav``.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted audio file path.

    Raises:
        Exception: Raised when ffmpeg is unavailable or conversion fails.
    """
    source_path = Path(audio_path)
    if source_path.suffix.lower() == f".{output_format}" and (
        not source_path.exists() or _get_audio_magic_type(audio_path) == output_format
    ):
        return audio_path

    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_audio_{uuid.uuid4().hex}.{output_format}")

    args = ["ffmpeg", "-y", "-i", audio_path]
    if output_format == "amr":
        args.extend(
            [
                "-ac",
                "1",
                "-ar",
                "8000",
                "-ab",
                "12.2k",
                "-af",
                (
                    "highpass=f=310:poles=2,"
                    "lowpass=f=3720:poles=2,"
                    "equalizer=f=3150:width_type=h:width=1000:g=7.5,"
                    "loudnorm=I=-18.5:TP=-1.5:LRA=6,"
                    "aresample=8000"
                ),
            ]
        )
    elif output_format == "ogg":
        args.extend(["-acodec", "libopus", "-ac", "1", "-ar", "16000"])
    elif output_format == "opus":
        args.extend(["-acodec", "libopus", "-ac", "1", "-ar", "16000"])
    args.append(output_path)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as e:
                    logger.warning(
                        "Failed to remove failed audio output file: %s",
                        e,
                    )
            error_msg = stderr.decode() if stderr else "unknown error"
            raise Exception(f"ffmpeg conversion failed: {error_msg}")
        logger.debug(
            "Audio converted successfully: %s -> %s",
            audio_path,
            output_path,
        )
        return output_path
    except FileNotFoundError:
        raise Exception("ffmpeg not found")


async def convert_audio_to_amr(audio_path: str, output_path: str | None = None) -> str:
    """Convert an audio file to AMR format.

    Args:
        audio_path: Source audio file path.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted AMR file path.
    """
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="amr",
        output_path=output_path,
    )


async def convert_audio_to_wav(audio_path: str, output_path: str | None = None) -> str:
    """Convert an audio file to WAV format.

    Args:
        audio_path: Source audio file path.
        output_path: Optional output file path. When omitted, a temporary path is
            created under AstrBot's temp directory.

    Returns:
        The converted WAV file path.
    """
    return await convert_audio_format(
        audio_path=audio_path,
        output_format="wav",
        output_path=output_path,
    )


async def ensure_wav(audio_path: str, output_path: str | None = None) -> str:
    """Ensure the audio path points to wav format by extension/guess and convert when needed.

    If the file appears to already be WAV, return it directly to avoid extra
    conversion. If the file does not exist yet, return the original path so
    upstream retry logic can handle platform races.

    Args:
        audio_path: Local audio path to inspect and convert when needed.
        output_path: Optional destination path. When omitted, conversion helpers
            create a temporary file under AstrBot's temp directory.

    Returns:
        The original path when it is already WAV or unavailable; otherwise the
        converted WAV path.

    Raises:
        Exception: Raised by the underlying conversion helper when conversion
            fails.
    """

    if not audio_path:
        return audio_path

    if not os.path.exists(audio_path):
        # File not available yet (e.g. napcat race condition);
        # return the path as-is so upstream retry logic can handle it later.
        return audio_path

    audio_type = _get_audio_magic_type(audio_path)
    if audio_type == "wav":
        return audio_path

    if audio_type == "silk":
        if output_path is None:
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            output_path = os.path.join(temp_dir, f"media_audio_{uuid.uuid4().hex}.wav")
        return await tencent_silk_to_wav(audio_path, output_path)

    return await convert_audio_to_wav(audio_path, output_path)


async def ensure_jpeg(image_path: str, output_path: str | None = None) -> str:
    """Ensure the image path points to a JPEG file.

    Args:
        image_path: Local image path to inspect and convert when needed.
        output_path: Optional destination path. When omitted, a temporary file under
            AstrBot's temp directory is created for converted JPEG output.

    Returns:
        The original path when the source is already a JPEG file with a jpg/jpeg
        suffix or cannot be found; otherwise the converted JPEG path.

    Raises:
        Exception: Raised by Pillow when the source file cannot be opened or saved as
            an image.
    """

    if not image_path:
        return image_path

    source_path = Path(image_path)
    if not source_path.exists():
        return image_path

    with PILImage.open(source_path) as opened_img:
        image_format = str(opened_img.format or "").upper()
        has_alpha = opened_img.mode in {"RGBA", "LA"} or (
            opened_img.mode == "P" and "transparency" in opened_img.info
        )
        is_animated = bool(
            getattr(opened_img, "is_animated", False)
            or getattr(opened_img, "n_frames", 1) > 1
        )

    if image_format == "JPEG" and source_path.suffix.lower() in {".jpg", ".jpeg"}:
        return image_path
    if has_alpha or is_animated:
        return image_path

    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_image_{uuid.uuid4().hex}.jpg")
    jpeg_output_path = output_path

    def convert_image_to_jpeg() -> str:
        converted_img: PILImage.Image | None = None
        flattened_img: PILImage.Image | None = None

        with PILImage.open(image_path) as opened_img:
            try:
                working_img: PILImage.Image = opened_img
                if opened_img.mode in {"RGBA", "LA"} or (
                    opened_img.mode == "P" and "transparency" in opened_img.info
                ):
                    flattened = PILImage.new("RGB", opened_img.size, (255, 255, 255))
                    flattened_img = flattened
                    alpha_source = opened_img.convert("RGBA")
                    try:
                        flattened.paste(alpha_source, mask=alpha_source.getchannel("A"))
                    finally:
                        alpha_source.close()
                    working_img = flattened
                elif opened_img.mode != "RGB":
                    converted_img = opened_img.convert("RGB")
                    working_img = converted_img

                working_img.save(jpeg_output_path, "JPEG")
                return jpeg_output_path
            finally:
                if converted_img is not None:
                    converted_img.close()
                if flattened_img is not None:
                    flattened_img.close()

    try:
        return await asyncio.to_thread(convert_image_to_jpeg)
    except Exception:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as e:
                logger.warning(
                    "Failed to remove failed image output file: %s",
                    e,
                )
        raise


def _get_audio_magic_type(audio_path: str) -> str:
    """Detect common audio formats from magic bytes.

    Args:
        audio_path: Local audio path to inspect.

    Returns:
        A normalized format name such as ``wav``, ``mp3``, ``opus``, ``silk``, or
        an empty string when the type cannot be detected.
    """
    try:
        with open(audio_path, "rb") as f:
            header = f.read(64)
    except FileNotFoundError:
        logger.warning("WAV probe file not found: %s", audio_path)
        return ""
    except Exception as e:
        logger.warning(
            "WAV probe failed: %s, error: %s",
            audio_path,
            e,
        )
        return ""

    if len(header) < 12:
        return ""

    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"

    if header[:4] == b"#!AM":
        return "amr"

    if header[:4] == b"OggS":
        if b"OpusHead" in header:
            return "opus"
        return "ogg"

    if header[:3] == b"fLa":
        return "flac"

    if header[:3] == b"ID3" or header[:2] == b"\xff\xfb":
        return "mp3"

    if header[:4] == b"ftyp" and b"mp4" in header[:8]:
        return "mp4"

    if header.startswith(b"#!SILK_V3"):
        return "silk"

    # Tencent SILK: leading \x02 byte before #!SILK_V3
    if header.startswith(b"\x02#!SILK_V3"):
        return "silk"

    return ""


async def extract_video_cover(
    video_path: str,
    output_path: str | None = None,
) -> str:
    """Extract a JPEG cover frame from a video.

    Args:
        video_path: Source video file path.
        output_path: Optional output image path. When omitted, a temporary JPEG
            path is created under AstrBot's temp directory.

    Returns:
        The extracted JPEG cover path.

    Raises:
        Exception: Raised when ffmpeg is unavailable or cover extraction fails.
    """
    if output_path is None:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(temp_dir / f"media_cover_{uuid.uuid4().hex}.jpg")

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-ss",
            "00:00:00",
            "-frames:v",
            "1",
            output_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as e:
                    logger.warning(
                        "Failed to remove failed video cover file: %s",
                        e,
                    )
            error_msg = stderr.decode() if stderr else "unknown error"
            raise Exception(f"ffmpeg extract cover failed: {error_msg}")
        return output_path
    except FileNotFoundError:
        raise Exception("ffmpeg not found")


def _dhash64(image: PILImage.Image) -> int:
    """Return a 64-bit difference hash of ``image``."""
    gray = image.convert("L").resize((9, 8), PILImage.Resampling.LANCZOS)
    try:
        pixels = gray.tobytes()
        value = 0
        for row in range(8):
            offset = row * 9
            for column in range(8):
                left = pixels[offset + column]
                right = pixels[offset + column + 1]
                value = (value << 1) | int(left > right)
        return value
    finally:
        if gray is not image:
            gray.close()


def _mean_rgb_pack(image: PILImage.Image) -> int:
    sample = image.convert("RGB").resize((1, 1), PILImage.Resampling.BOX)
    try:
        pixel = sample.getpixel((0, 0))
        if not isinstance(pixel, tuple) or len(pixel) < 3:
            return 0
        red, green, blue = int(pixel[0]), int(pixel[1]), int(pixel[2])
        return (red << 16) | (green << 8) | blue
    finally:
        if sample is not image:
            sample.close()


def _color_distance(left: int, right: int) -> int:
    delta = (
        abs(((left >> 16) & 255) - ((right >> 16) & 255))
        + abs(((left >> 8) & 255) - ((right >> 8) & 255))
        + abs((left & 255) - (right & 255))
    )
    return min(delta * PROVIDER_JPEG_HAMMING_CAP // 765, PROVIDER_JPEG_HAMMING_CAP)


def _max_channel_delta(left: int, right: int) -> int:
    red = abs(((left >> 16) & 255) - ((right >> 16) & 255))
    green = abs(((left >> 8) & 255) - ((right >> 8) & 255))
    blue = abs((left & 255) - (right & 255))
    return min(max(red, green, blue), PROVIDER_JPEG_HAMMING_CAP)


def _quadrant_boxes(image: PILImage.Image) -> tuple[tuple[int, int, int, int], ...]:
    width, height = image.size
    mid_w = max(width // 2, 1)
    mid_h = max(height // 2, 1)
    return (
        (0, 0, mid_w, mid_h),
        (width - mid_w, 0, width, mid_h),
        (0, height - mid_h, mid_w, height),
        (width - mid_w, height - mid_h, width, height),
    )


def _tile_color_packs(image: PILImage.Image) -> tuple[int, int, int, int]:
    packs: list[int] = []
    for box in _quadrant_boxes(image):
        tile = image.crop(box)
        try:
            packs.append(_mean_rgb_pack(tile))
        finally:
            tile.close()
    return packs[0], packs[1], packs[2], packs[3]


def _tile_dhashes(image: PILImage.Image) -> tuple[int, int, int, int]:
    hashes: list[int] = []
    for box in _quadrant_boxes(image):
        tile = image.crop(box)
        try:
            hashes.append(_dhash64(tile))
        finally:
            tile.close()
    return hashes[0], hashes[1], hashes[2], hashes[3]


def _flatten_alpha_on_white(image: PILImage.Image) -> PILImage.Image:
    if image.mode == "RGB":
        return image.copy()
    rgba = image.convert("RGBA")
    try:
        background = PILImage.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    finally:
        if rgba is not image:
            rgba.close()


def _is_blank_frame(image: PILImage.Image) -> bool:
    gray = image.convert("L")
    try:
        histogram = gray.histogram()
        total = sum(histogram)
        if total == 0:
            return True
        mean = sum(index * count for index, count in enumerate(histogram)) / total
        variance = (
            sum(count * (index - mean) ** 2 for index, count in enumerate(histogram))
            / total
        )
        if variance >= PROVIDER_JPEG_BLANK_VARIANCE:
            return False
        return mean < PROVIDER_JPEG_BLANK_VARIANCE or mean > (
            255 - PROVIDER_JPEG_BLANK_VARIANCE
        )
    finally:
        if gray is not image:
            gray.close()


def _frame_hamming(left: ComposedFrame, right: ComposedFrame) -> tuple[int, int]:
    global_h = (left.global_hash ^ right.global_hash).bit_count()
    tile_h = max(
        (left_tile ^ right_tile).bit_count()
        for left_tile, right_tile in zip(
            left.tile_hashes, right.tile_hashes, strict=True
        )
    )
    color_h = _color_distance(left.color_hash, right.color_hash)
    tile_color_h = max(
        _max_channel_delta(left_color, right_color)
        for left_color, right_color in zip(
            left.tile_colors, right.tile_colors, strict=True
        )
    )
    return global_h, max(tile_h, color_h, tile_color_h)


def _is_near_static(frame: ComposedFrame, first: ComposedFrame) -> bool:
    global_h, tile_h = _frame_hamming(frame, first)
    return (
        global_h < PROVIDER_JPEG_STATIC_HAMMING
        and tile_h < PROVIDER_JPEG_STATIC_HAMMING
    )


def _adjacent_changes(frames: Sequence[ComposedFrame]) -> list[int]:
    return [
        min(
            max(*_frame_hamming(frames[index], frames[index - 1])),
            PROVIDER_JPEG_HAMMING_CAP,
        )
        for index in range(1, len(frames))
    ]


def _non_blank_frames(frames: Sequence[ComposedFrame]) -> list[ComposedFrame]:
    return [frame for frame in frames if not _is_blank_frame(frame.image)]


def animated_frame_budget(frames: Sequence[ComposedFrame]) -> float:
    """Return a sampling budget ``f`` in ``[0, 1]``.

    ``0`` means the source is static, blink-static, or blank-padded. Higher
    values mean more adjacent change and/or longer duration.

    Args:
        frames: Composed RGB frames with delays and dhashes.

    Returns:
        Sampling budget in ``[0, 1]``.
    """
    remaining = _non_blank_frames(frames)
    if len(remaining) <= 1:
        return 0.0
    first = remaining[0]
    if all(_is_near_static(frame, first) for frame in remaining):
        return 0.0
    total_ms = 0
    same_ms = 0
    for frame in remaining:
        duration = (
            frame.duration_ms
            if frame.duration_ms > 0
            else PROVIDER_JPEG_DEFAULT_DELAY_MS
        )
        total_ms += duration
        if _is_near_static(frame, first):
            same_ms += duration
    if total_ms > 0 and same_ms / total_ms >= PROVIDER_JPEG_BLINK_OCCUPANCY:
        return 0.0
    changes = _adjacent_changes(remaining)
    if not changes:
        return 0.0
    mu = statistics.fmean(changes) / 64.0
    t_seconds = total_ms / 1000.0
    ratio = (mu / PROVIDER_JPEG_MU_REF) ** 2 * (t_seconds / PROVIDER_JPEG_T_REF_SECONDS)
    return min(max(1.0 - math.exp(-ratio), 0.0), 1.0)


def _first_index_reaching(cumulative: Sequence[int], target: float) -> int:
    for index, value in enumerate(cumulative):
        if value >= target:
            return index
    return max(len(cumulative) - 1, 0)


def _cumulative_quantile_indices(changes: Sequence[int], count: int) -> list[int]:
    if count <= 1:
        return [0]
    cumulative = [0]
    for change in changes:
        cumulative.append(cumulative[-1] + change)
    total = cumulative[-1]
    if total <= 0:
        return [0]
    return [
        _first_index_reaching(cumulative, t * total / (count - 1)) for t in range(count)
    ]


def _pick_animated_frame_indices(frames: Sequence[ComposedFrame], k: int) -> list[int]:
    n_frames = len(frames)
    if n_frames == 0:
        return []
    if n_frames == 1 or k <= 1:
        return [0]
    k = min(k, n_frames, PROVIDER_JPEG_MAX_ANIMATED_FRAMES)
    changes = _adjacent_changes(frames)
    mean = statistics.fmean(changes) if changes else 0.0
    std = statistics.pstdev(changes) if len(changes) >= 2 else 0.0
    cuts: list[int] = []
    if std > 0:
        threshold = mean + std
        cuts = [index + 1 for index, change in enumerate(changes) if change > threshold]
    if 1 <= len(cuts) < k:
        selected = [0]
        for cut in cuts:
            if cut not in selected:
                selected.append(cut)
        if len(selected) < k:
            for index in _cumulative_quantile_indices(changes, k):
                if index not in selected:
                    selected.append(index)
                if len(selected) >= k:
                    break
        return sorted(selected)
    return _cumulative_quantile_indices(changes, k)


def _dedupe_frame_indices(
    frames: Sequence[ComposedFrame],
    indices: Sequence[int],
) -> list[int]:
    ordered = sorted({index for index in indices if 0 <= index < len(frames)})
    if not ordered:
        return []
    kept = [ordered[0]]
    for index in ordered[1:]:
        global_h, region_h = _frame_hamming(frames[index], frames[kept[-1]])
        if max(global_h, region_h) < PROVIDER_JPEG_DEDUP_HAMMING:
            continue
        kept.append(index)
    if len(kept) > 1:
        global_h, region_h = _frame_hamming(frames[kept[-1]], frames[kept[0]])
        if max(global_h, region_h) < PROVIDER_JPEG_DEDUP_HAMMING:
            kept.pop()
    return kept


def _compose_image_frames(image_path: str) -> list[ComposedFrame]:
    frames: list[ComposedFrame] = []
    with PILImage.open(image_path) as source:
        canvas = PILImage.new("RGBA", source.size, (0, 0, 0, 0))
        n_frames = min(
            getattr(source, "n_frames", 1) or 1,
            PROVIDER_JPEG_MAX_COMPOSE_FRAMES,
        )
        try:
            for index in range(n_frames):
                source.seek(index)
                duration = source.info.get("duration") or PROVIDER_JPEG_DEFAULT_DELAY_MS
                if duration <= 0:
                    duration = PROVIDER_JPEG_DEFAULT_DELAY_MS
                disposal = getattr(source, "disposal_method", None)
                if disposal is None:
                    disposal = source.info.get("disposal", 0) or 0
                frame_rgba = source.convert("RGBA")
                try:
                    if frame_rgba.size != canvas.size:
                        padded = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
                        padded.paste(frame_rgba, (0, 0))
                        frame_rgba.close()
                        frame_rgba = padded
                    composed = canvas.copy()
                    composed.paste(frame_rgba, (0, 0), frame_rgba)
                finally:
                    frame_rgba.close()
                rgb = _flatten_alpha_on_white(composed)
                frames.append(ComposedFrame.from_image(rgb, int(duration)))
                if disposal == 2:
                    composed.close()
                    canvas.close()
                    canvas = PILImage.new("RGBA", source.size, (0, 0, 0, 0))
                else:
                    canvas.close()
                    canvas = composed
        finally:
            canvas.close()
    return frames


def _save_provider_jpeg(
    image: PILImage.Image,
    *,
    max_size: int | None,
    quality: int,
) -> str:
    working = image if image.mode == "RGB" else _flatten_alpha_on_white(image)
    converted = working if working is not image else None
    resized = None
    try:
        if max_size is not None and max(working.size) > max_size:
            resized = working.copy()
            resized.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)
            working = resized
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / f"provider_jpeg_{uuid.uuid4().hex}.jpg"
        working.save(
            output_path,
            "JPEG",
            quality=quality,
            optimize=IMAGE_COMPRESS_DEFAULT_OPTIMIZE,
        )
        return str(output_path)
    finally:
        if resized is not None:
            resized.close()
        if converted is not None:
            converted.close()


def _prepare_images_for_provider_sync(
    url_or_path: str,
    max_size: int,
    quality: int,
    resize: bool,
) -> list[str]:
    source = Path(url_or_path)
    if not source.is_file():
        return []
    try:
        frames = _compose_image_frames(str(source))
    except OSError, ValueError, UnidentifiedImageError, SyntaxError:
        return []
    if not frames:
        return []
    try:
        remaining = _non_blank_frames(frames)
        work = remaining or frames[:1]
        budget = animated_frame_budget(frames)
        k = min(
            max(1 + round(7 * budget), 1),
            PROVIDER_JPEG_MAX_ANIMATED_FRAMES,
        )
        indices = _dedupe_frame_indices(work, _pick_animated_frame_indices(work, k))
        quality = min(max(int(quality), 1), 100)
        resize_to = max(int(max_size), 1) if resize else None
        return [
            _save_provider_jpeg(work[index].image, max_size=resize_to, quality=quality)
            for index in indices
        ]
    finally:
        for frame in frames:
            frame.image.close()


async def prepare_images_for_provider(
    url_or_path: str,
    *,
    max_size: int = IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    quality: int = IMAGE_COMPRESS_DEFAULT_QUALITY,
    resize: bool = True,
) -> list[str]:
    """Convert a local image into 0..8 JPEG files for a chat provider.

    Alpha is flattened onto white. Output is never enlarged. Animated GIF/WebP
    sources are dhash-sampled from at most 64 composed frames. Bytes that are
    not a decodable image yield an empty list.

    Args:
        url_or_path: Local filesystem path to the source image.
        max_size: Longest edge in pixels when ``resize`` is true.
        quality: JPEG quality from 1 to 100.
        resize: When true, thumbnail down if the long edge exceeds ``max_size``.

    Returns:
        Temporary JPEG paths in increasing source-frame order. Empty when the
        source cannot be decoded as an image.
    """
    try:
        return await asyncio.to_thread(
            _prepare_images_for_provider_sync,
            url_or_path,
            max_size,
            quality,
            resize,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to prepare provider JPEG: %s", exc)
        return []


def _compress_image_sync(
    data: bytes,
    temp_dir: Path,
    max_size: int,
    quality: int,
    optimize: bool,
) -> str | None:
    """Run image compression synchronously via ``asyncio.to_thread``."""
    with PILImage.open(io.BytesIO(data)) as opened_img:
        converted_img: PILImage.Image | None = None

        try:
            is_animated = bool(
                getattr(opened_img, "is_animated", False)
                or getattr(opened_img, "n_frames", 1) > 1
            )
            if is_animated:
                return None

            preserve_alpha = opened_img.mode in {"RGBA", "LA"} or (
                opened_img.mode == "P" and "transparency" in opened_img.info
            )

            working_img = opened_img
            if preserve_alpha:
                if opened_img.mode != "RGBA":
                    converted_img = opened_img.convert("RGBA")
                    working_img = converted_img
                save_path = temp_dir / f"compressed_{uuid.uuid4().hex}.png"
                save_kwargs: dict[str, object] = {"optimize": optimize}
                save_format = "PNG"
            else:
                if opened_img.mode != "RGB":
                    converted_img = opened_img.convert("RGB")
                    working_img = converted_img
                save_path = temp_dir / f"compressed_{uuid.uuid4().hex}.jpg"
                save_kwargs = {"quality": quality, "optimize": optimize}
                save_format = "JPEG"
            assert working_img is not None

            if max(working_img.size) > max_size:
                working_img.thumbnail((max_size, max_size), PILImage.Resampling.LANCZOS)

            working_img.save(save_path, save_format, **save_kwargs)
            logger.debug(f"Image compressed successfully: {save_path}")
            return str(save_path)
        finally:
            if converted_img is not None:
                converted_img.close()


async def compress_image(
    url_or_path: str,
    max_size: int = IMAGE_COMPRESS_DEFAULT_MAX_SIZE,
    quality: int = IMAGE_COMPRESS_DEFAULT_QUALITY,
) -> str:
    """Compress large user-uploaded images.

    Args:
        url_or_path: Image path or URL.
        max_size: Longest edge of the compressed image in pixels.
        quality: JPEG output quality in the range 1-100.

    Returns:
        The compressed image path. Returns the original path if compression
        fails or the source does not need compression.
    """
    max_size = max(int(max_size), 1)
    quality = min(max(int(quality), 1), 100)
    optimize = IMAGE_COMPRESS_DEFAULT_OPTIMIZE
    min_file_size_bytes = int(IMAGE_COMPRESS_DEFAULT_MIN_FILE_SIZE_MB * 1024 * 1024)
    data = None

    def _exceeds_max_size(source: bytes | Path) -> bool:
        try:
            fp = io.BytesIO(source) if isinstance(source, bytes) else source
            with PILImage.open(fp) as opened_img:
                return max(opened_img.size) > max_size
        except Exception:  # noqa: BLE001
            return False

    # Skip compression for remote images and return the original value.
    if url_or_path.startswith("http"):
        return url_or_path
    elif url_or_path.startswith("data:image"):
        _header, encoded = url_or_path.split(",", 1)
        data = _decode_base64_payload(
            encoded,
            error_message="invalid image data URI payload",
        )
        if len(data) < min_file_size_bytes and not _exceeds_max_size(data):
            return url_or_path
    else:
        local_path = Path(url_or_path)
        if not local_path.exists():
            return url_or_path
        if local_path.stat().st_size < min_file_size_bytes and not _exceeds_max_size(
            local_path
        ):
            return url_or_path
        with local_path.open("rb") as f:
            data = f.read()

    if not data:
        return url_or_path

    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Offload the blocking image processing task to a thread.
    compressed_path = await asyncio.to_thread(
        _compress_image_sync,
        data,
        temp_dir,
        max_size,
        quality,
        optimize,
    )
    return compressed_path or url_or_path
