"""Dashboard Extension Protocol v1 short-lived file tickets."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import mimetypes
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from astrbot.core.star.dashboard_extension import (
    DashboardExtensionLifecycleEvent,
    DashboardExtensionRegistry,
    DashboardExtensionSnapshot,
    DashboardFile,
    DashboardFileAction,
    DashboardLifecycleEventKind,
)
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.auth_service import (
    DashboardSessionPrincipal,
    derive_dashboard_secret,
)

FILE_TICKET_COOKIE_NAME = "astrbot_plugin_file"
FILE_TICKET_TTL = timedelta(seconds=60)
FILE_TICKET_SECRET_PURPOSE = b"dashboard-plugin-file-ticket-secret-v1"
_UNSAFE_FILENAME = re.compile(r"[\x00-\x1f\x7f/\\]+")
_CONTENT_TYPE_RE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_UNSAFE_INLINE_CONTENT_TYPES = frozenset(
    {
        "application/xhtml+xml",
        "application/xml",
        "image/svg+xml",
        "text/html",
        "text/xml",
    }
)


def normalize_content_type(content_type: str) -> str:
    """Validate an already-lowercased ``type/subtype`` media type."""
    if not _CONTENT_TYPE_RE.fullmatch(content_type):
        raise ValueError("Invalid media type")
    return content_type


def resolve_disposition(
    content_type: str,
    disposition: str,
) -> str:
    """Force document-like media to download instead of inline rendering."""
    if content_type in _UNSAFE_INLINE_CONTENT_TYPES:
        return "attachment"
    return disposition


class RawFileError(Exception):
    """Minimal raw file protocol failure."""

    def __init__(self, status_code: int) -> None:
        super().__init__("File unavailable")
        self.status_code = status_code


@dataclass(frozen=True)
class CreatedFileTicket:
    data: dict[str, object]
    cookie_secret: str
    cookie_path: str
    cookie_max_age: int


@dataclass(frozen=True)
class RedeemedFile:
    path: Path
    file_handle: BinaryIO
    filename: str
    content_type: str
    size: int
    disposition: str
    clear_cookie: bool


@dataclass
class _FileTicketRecord:
    handle: str
    secret_hash: bytes
    auth_session_id: str
    username: str
    extension_id: str
    action_id: str
    generation: str
    path: Path
    filename: str
    content_type: str
    size: int
    disposition: str
    remaining_uses: int
    expires_at: datetime


def sanitize_download_filename(filename: str) -> str:
    """Return a header-safe display filename."""
    cleaned = _UNSAFE_FILENAME.sub("_", filename).strip(" .")
    encoded = cleaned.encode("utf-8")[:255]
    while encoded:
        try:
            cleaned = encoded.decode("utf-8")
            break
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return cleaned or "download"


def content_disposition_header(disposition: str, filename: str) -> str:
    """Build an RFC 6266 Content-Disposition value."""
    safe = sanitize_download_filename(filename)
    fallback = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in {'"', "\\"} else "_" for ch in safe
    )
    fallback = fallback or "download"
    encoded = quote(safe, safe="!#$&+-.^_`|~")
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


class PluginFileTicketService:
    """Issue and redeem owner-bound file capabilities."""

    def __init__(
        self,
        registry: DashboardExtensionRegistry,
        jwt_secret: str,
    ) -> None:
        self.registry = registry
        self._secret_key = derive_dashboard_secret(
            jwt_secret,
            FILE_TICKET_SECRET_PURPOSE,
        )
        self._tickets: dict[str, _FileTicketRecord] = {}
        self._lock = asyncio.Lock()
        self._unsubscribe = registry.subscribe(self._on_registry_event)

    def _digest_secret(self, secret: str) -> bytes:
        return hmac.new(self._secret_key, secret.encode(), hashlib.sha256).digest()

    @staticmethod
    def _resolve_file(
        snapshot: DashboardExtensionSnapshot,
        file: DashboardFile,
    ) -> Path:
        try:
            root = snapshot.plugin_root.resolve(strict=True)
            resolved = (root / file.relative_path).resolve(strict=True)
        except OSError as exc:
            raise ApiError("Plugin operation failed", status_code=500) from exc
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ApiError("Plugin operation failed", status_code=500)
        return resolved

    async def create_ticket(
        self,
        snapshot: DashboardExtensionSnapshot,
        action_id: str,
        action: DashboardFileAction,
        file: DashboardFile,
        principal: DashboardSessionPrincipal,
    ) -> CreatedFileTicket:
        resolved = self._resolve_file(snapshot, file)
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            raise ApiError("Plugin operation failed", status_code=500) from exc
        if size > action.max_file_bytes:
            raise ApiError("File is too large", status_code=413)
        content_type = (
            file.content_type
            or mimetypes.guess_type(resolved.name)[0]
            or "application/octet-stream"
        ).lower()
        try:
            content_type = normalize_content_type(content_type)
        except ValueError as exc:
            raise ApiError("File media type is not allowed", status_code=415) from exc
        if (
            action.allowed_content_types
            and content_type not in action.allowed_content_types
        ):
            raise ApiError("File media type is not allowed", status_code=415)
        disposition = resolve_disposition(content_type, action.disposition)
        filename = sanitize_download_filename(file.filename or resolved.name)
        handle = secrets.token_urlsafe(48)
        secret = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + FILE_TICKET_TTL
        record = _FileTicketRecord(
            handle=handle,
            secret_hash=self._digest_secret(secret),
            auth_session_id=principal.sid,
            username=principal.username,
            extension_id=snapshot.extension_id,
            action_id=action_id,
            generation=snapshot.generation,
            path=resolved,
            filename=filename,
            content_type=content_type,
            size=size,
            disposition=disposition,
            remaining_uses=3 if disposition == "inline" else 1,
            expires_at=expires_at,
        )
        async with self._lock:
            self._purge_expired_locked(datetime.now(UTC))
            self._tickets[handle] = record
        path = f"/api/plugin-files/v1/{handle}"
        return CreatedFileTicket(
            data={
                "ticket_url": path,
                "filename": filename,
                "content_type": content_type,
                "size": size,
                "disposition": action.disposition,
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            },
            cookie_secret=secret,
            cookie_path=path,
            cookie_max_age=int(FILE_TICKET_TTL.total_seconds()),
        )

    async def redeem(
        self,
        handle: str,
        cookie_secret: str | None,
    ) -> RedeemedFile:
        if not cookie_secret:
            raise RawFileError(401)
        now = datetime.now(UTC)
        async with self._lock:
            self._purge_expired_locked(now)
            record = self._tickets.get(handle)
            if record is None or not hmac.compare_digest(
                record.secret_hash,
                self._digest_secret(cookie_secret),
            ):
                raise RawFileError(404)
            snapshot = self.registry.get_snapshot(record.extension_id)
            if snapshot is None or snapshot.generation != record.generation:
                self._tickets.pop(handle, None)
                raise RawFileError(404)
            try:
                root = snapshot.plugin_root.resolve(strict=True)
                resolved = record.path.resolve(strict=True)
                validated_stat = resolved.stat()
                if (
                    not resolved.is_relative_to(root)
                    or not resolved.is_file()
                    or validated_stat.st_size != record.size
                ):
                    raise OSError
            except OSError as exc:
                self._tickets.pop(handle, None)
                raise RawFileError(404) from exc
            if record.remaining_uses <= 0:
                self._tickets.pop(handle, None)
                raise RawFileError(404)
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(resolved, flags)
            except OSError as exc:
                self._tickets.pop(handle, None)
                raise RawFileError(404) from exc
            try:
                opened_stat = os.fstat(fd)
                if (
                    opened_stat.st_dev != validated_stat.st_dev
                    or opened_stat.st_ino != validated_stat.st_ino
                    or opened_stat.st_size != record.size
                ):
                    raise OSError
            except OSError as exc:
                os.close(fd)
                self._tickets.pop(handle, None)
                raise RawFileError(404) from exc
            file_handle = os.fdopen(fd, "rb")
            record.remaining_uses -= 1
            clear_cookie = record.disposition == "attachment"
            if record.remaining_uses == 0:
                self._tickets.pop(handle, None)
            return RedeemedFile(
                path=resolved,
                file_handle=file_handle,
                filename=record.filename,
                content_type=record.content_type,
                size=record.size,
                disposition=record.disposition,
                clear_cookie=clear_cookie,
            )

    async def revoke_by_auth_session_id(self, auth_session_id: str) -> None:
        async with self._lock:
            for handle, record in tuple(self._tickets.items()):
                if record.auth_session_id == auth_session_id:
                    self._tickets.pop(handle, None)

    async def revoke_generation(self, extension_id: str, generation: str) -> None:
        async with self._lock:
            for handle, record in tuple(self._tickets.items()):
                if (
                    record.extension_id == extension_id
                    and record.generation == generation
                ):
                    self._tickets.pop(handle, None)

    async def _on_registry_event(
        self,
        event: DashboardExtensionLifecycleEvent,
    ) -> None:
        if event.kind in {
            DashboardLifecycleEventKind.DRAINING,
            DashboardLifecycleEventKind.INACTIVE,
        }:
            await self.revoke_generation(event.extension_id, event.generation)

    def _purge_expired_locked(self, now: datetime) -> None:
        for handle, record in tuple(self._tickets.items()):
            if record.expires_at <= now:
                self._tickets.pop(handle, None)

    async def shutdown(self) -> None:
        self._unsubscribe()
        async with self._lock:
            self._tickets.clear()
