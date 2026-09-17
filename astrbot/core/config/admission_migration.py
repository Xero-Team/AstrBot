"""Migrate ID-whitelist config into unlisted-session admission overlays."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from astrbot.core.auth.admission import (
    ADMISSION_LISTED_SESSIONS_KEY,
    ConversationKind,
    UnlistedPolicy,
    session_admission_key,
    session_admission_key_from_umo,
)
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
    session group UMOs unwrap to the group id.

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
    written to a data sidecar keyed by this config path. Empty or disabled
    lists become ``allow``. The sidecar is applied later, after shared
    preferences exist.

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
            _append_pending_session_allows(config_path, keys)
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


async def apply_pending_session_allows(
    preferences: Any,
    configs: Mapping[str, Any] | None = None,
) -> int:
    """Store pending listed-session keys per configuration profile.

    Keys stay scoped to the config file that produced them. They are not
    written as ``session_enabled`` overlays, so a later session-status stage
    still owns that field on UMO rows.

    Args:
        preferences: Shared preference store exposing ``global_get`` /
            ``global_put``.
        configs: ``config_id`` to config objects with ``config_path``. Missing
            mappings attach leftover sidecar paths to ``default``.

    Returns:
        Number of pending keys processed.
    """

    pending = _load_pending_session_allows()
    if not pending:
        return 0
    listed = await _listed_sessions_map(preferences)
    applied = 0
    for raw_path, keys in pending.items():
        if not keys:
            continue
        config_id = _config_id_for_path(configs, Path(raw_path))
        merged = list(listed.get(config_id, []))
        seen = set(merged)
        for key in keys:
            applied += 1
            if key in seen:
                continue
            seen.add(key)
            merged.append(key)
        listed[config_id] = merged
    await preferences.global_put(ADMISSION_LISTED_SESSIONS_KEY, listed)
    _clear_pending_session_allows()
    return applied


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
    from_umo = session_admission_key_from_umo(entry)
    if from_umo is not None:
        return [from_umo]
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


def _config_id_for_path(configs: Mapping[str, Any] | None, path: Path) -> str:
    if not configs:
        return "default"
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for config_id, conf in configs.items():
        conf_path = getattr(conf, "config_path", None)
        if not conf_path:
            continue
        try:
            other = Path(conf_path).resolve()
        except OSError:
            other = Path(conf_path)
        if other == resolved:
            return str(config_id)
    return "default"


async def _listed_sessions_map(preferences: Any) -> dict[str, list[str]]:
    raw = await preferences.global_get(ADMISSION_LISTED_SESSIONS_KEY, {})
    if not isinstance(raw, dict):
        return {}
    listed: dict[str, list[str]] = {}
    for config_id, values in raw.items():
        if not isinstance(config_id, str) or not isinstance(values, list):
            continue
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
        listed[config_id] = keys
    return listed


def _load_pending_session_allows() -> dict[str, list[str]]:
    path = pending_session_allows_sidecar_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to read pending session-allow sidecar %s: %s",
            path,
            exc,
        )
        return {}
    return _pending_from_raw(raw)


def _pending_from_raw(raw: object) -> dict[str, list[str]]:
    if isinstance(raw, list):
        keys = _dedupe_keys(raw)
        return {"default": keys} if keys else {}
    if not isinstance(raw, dict):
        return {}
    pending: dict[str, list[str]] = {}
    for config_path, values in raw.items():
        if not isinstance(config_path, str):
            continue
        keys = _dedupe_keys(values if isinstance(values, list) else [])
        if keys:
            pending[config_path] = keys
    return pending


def _dedupe_keys(values: Sequence[object]) -> list[str]:
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


def _append_pending_session_allows(config_path: Path, keys: Sequence[str]) -> None:
    pending = _load_pending_session_allows()
    path_key = str(config_path.resolve())
    merged = list(pending.get(path_key, []))
    seen = set(merged)
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
    pending[path_key] = merged
    _write_pending_session_allows(pending)


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
        _write_pending_session_allows({})


def _write_pending_session_allows(pending: Mapping[str, Sequence[str]]) -> None:
    path = pending_session_allows_sidecar_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {key: list(value) for key, value in pending.items()},
        ensure_ascii=False,
        indent=2,
    )
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
            # Best-effort cleanup of the unreplaced tempfile.
            pass
        raise
