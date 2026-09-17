"""Migrate ID-whitelist config into unlisted-session admission overlays."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from astrbot.core.auth.admission import (
    SESSION_SERVICE_CONFIG_KEY,
    ConversationKind,
    UnlistedPolicy,
    session_admission_key,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

logger = logging.getLogger("astrbot")

_REMOVED_WHITELIST_KEYS = (
    "enable_id_white_list",
    "id_whitelist",
    "id_whitelist_log",
    "wl_ignore_admin_on_group",
    "wl_ignore_admin_on_friend",
)
_PENDING_SIDECAR_NAME = "admission_pending_session_allows.json"


def pending_session_allows_sidecar_path() -> Path:
    """Return the data-root sidecar that stores pending listed-session keys.

    Returns:
        Path of ``admission_pending_session_allows.json`` under the runtime
        data directory.
    """

    return Path(get_astrbot_data_path()) / _PENDING_SIDECAR_NAME


def pending_session_allows_from_whitelist(
    entries: Sequence[object],
    platform_ids: Sequence[str],
) -> list[str]:
    """Convert old whitelist entries into canonical session admission keys.

    Bare IDs expand to one group key per configured platform instance. UMO
    entries mint a key from the platform instance and message type. Unique-
    session UMOs are not rewritten into per-person allows.

    Args:
        entries: Raw ``id_whitelist`` values.
        platform_ids: ``platform[].id`` values on the same profile.

    Returns:
        Deduplicated canonical session keys, preserving first-seen order.
    """

    keys: list[str] = []
    seen: set[str] = set()
    ids = [platform_id.strip() for platform_id in platform_ids if platform_id.strip()]
    for raw in entries:
        entry = str(raw).strip()
        if not entry:
            continue
        for key in _keys_for_whitelist_entry(entry, ids):
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def migrate_admission_on_load(config: dict[str, Any], config_path: Path) -> bool:
    """Replace ID-whitelist fields with ``admission.unlisted_sessions``.

    A non-empty enabled list becomes ``deny`` plus pending listed-session keys
    written to a data sidecar. Empty or disabled lists become ``allow``. The
    sidecar is applied later, after shared preferences exist.

    Args:
        config: Mutable configuration loaded from disk.
        config_path: Path of the configuration being loaded.

    Returns:
        Whether the configuration changed.
    """

    platform_settings = config.get("platform_settings")
    if not isinstance(platform_settings, dict):
        return False
    if not any(key in platform_settings for key in _REMOVED_WHITELIST_KEYS):
        return False

    enabled = platform_settings.get("enable_id_white_list", True)
    if not isinstance(enabled, bool):
        enabled = True
    raw_list = platform_settings.get("id_whitelist", [])
    entries = (
        [item for item in raw_list if str(item).strip()]
        if isinstance(raw_list, list)
        else []
    )

    admission = config.get("admission")
    if not isinstance(admission, dict):
        admission = {}
        config["admission"] = admission

    if enabled and entries:
        admission["unlisted_sessions"] = UnlistedPolicy.DENY.value
        keys = pending_session_allows_from_whitelist(
            entries,
            _platform_ids(config),
        )
        if keys:
            _append_pending_session_allows(keys)
            logger.info(
                "Migrated %s ID-whitelist entries from %s into listed "
                "session overlays.",
                len(keys),
                config_path,
            )
        else:
            logger.warning(
                "ID whitelist in %s was non-empty but produced no session keys.",
                config_path,
            )
    else:
        admission["unlisted_sessions"] = UnlistedPolicy.ALLOW.value

    for key in _REMOVED_WHITELIST_KEYS:
        platform_settings.pop(key, None)
    return True


async def apply_pending_session_allows(preferences: Any) -> int:
    """Merge pending listed-session overlays into shared preferences.

    Each pending canonical key receives ``session_enabled=true`` unless that
    field is already a bool. Existing ``llm_enabled``, TTS, persona, and
    ``session_enabled`` values on that key are kept. The sidecar is cleared
    after a successful pass.

    Args:
        preferences: Shared preference store exposing ``session_get`` /
            ``session_put``.

    Returns:
        Number of pending keys processed.
    """

    keys = _load_pending_session_allows()
    if not keys:
        return 0
    for key in keys:
        raw = await preferences.session_get(key, SESSION_SERVICE_CONFIG_KEY, {})
        config = dict(raw) if isinstance(raw, dict) else {}
        if not isinstance(config.get("session_enabled"), bool):
            config["session_enabled"] = True
            await preferences.session_put(key, SESSION_SERVICE_CONFIG_KEY, config)
    _clear_pending_session_allows()
    return len(keys)


def _platform_ids(config: dict[str, Any]) -> list[str]:
    platforms = config.get("platform")
    if not isinstance(platforms, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for item in platforms:
        if not isinstance(item, dict):
            continue
        platform_id = item.get("id")
        if not isinstance(platform_id, str):
            continue
        platform_id = platform_id.strip()
        if not platform_id or platform_id in seen:
            continue
        seen.add(platform_id)
        ids.append(platform_id)
    return ids


def _keys_for_whitelist_entry(entry: str, platform_ids: Sequence[str]) -> list[str]:
    if entry.startswith("session:"):
        return [entry]
    if ":" in entry:
        try:
            session = MessageSession.from_str(entry)
        except TypeError, ValueError:
            session = None
        if session is not None:
            kind = (
                ConversationKind.GROUP
                if session.message_type is MessageType.GROUP_MESSAGE
                else ConversationKind.PRIVATE
            )
            return [
                session_admission_key(
                    platform_instance=session.platform_id,
                    conversation_kind=kind,
                    conversation_id=session.session_id,
                )
            ]
    if not platform_ids:
        logger.warning(
            "Skipping bare whitelist ID %s: this profile has no platform instances.",
            entry,
        )
        return []
    return [
        session_admission_key(
            platform_instance=platform_id,
            conversation_kind=ConversationKind.GROUP,
            conversation_id=entry,
        )
        for platform_id in platform_ids
    ]


def _load_pending_session_allows() -> list[str]:
    path = pending_session_allows_sidecar_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to read pending session-allow sidecar %s: %s",
            path,
            exc,
        )
        return []
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = []
        for item in raw.values():
            if isinstance(item, list):
                values.extend(item)
    else:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _append_pending_session_allows(keys: Sequence[str]) -> None:
    merged = _load_pending_session_allows()
    seen = set(merged)
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
    _write_pending_session_allows(merged)


def _clear_pending_session_allows() -> None:
    path = pending_session_allows_sidecar_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning(
            "Failed to remove pending session-allow sidecar %s: %s",
            path,
            exc,
        )
        _write_pending_session_allows([])


def _write_pending_session_allows(keys: Sequence[str]) -> None:
    path = pending_session_allows_sidecar_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(list(keys), ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
