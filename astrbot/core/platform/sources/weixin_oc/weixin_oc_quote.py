"""Helpers for reconstructing Weixin OC quoted messages."""

from __future__ import annotations

import hashlib
from typing import Any


def build_ilink_client_version(version: str) -> str:
    """Encode `major.minor.patch` as the iLink uint32 client version string.

    Args:
        version: Dotted version string such as ``4.28.0``.

    Returns:
        Decimal string of ``0x00MMNNPP``.
    """
    parts = version.split(".")
    major = _non_negative_int(parts[0] if parts else "0")
    minor = _non_negative_int(parts[1] if len(parts) > 1 else "0")
    patch = _non_negative_int(parts[2] if len(parts) > 2 else "0")
    encoded = ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)
    return str(encoded)


def ref_message_id(ref_msg: dict[str, Any] | None) -> str:
    """Return the server message id carried by a quote payload."""
    if not isinstance(ref_msg, dict):
        return ""
    svr_id = str(ref_msg.get("svr_id") or "").strip()
    if svr_id:
        return svr_id
    message_item = ref_msg.get("message_item")
    if not isinstance(message_item, dict):
        return ""
    return str(
        message_item.get("msg_id") or message_item.get("message_id") or ""
    ).strip()


def resolve_partial_quote(full_text: str, partial: dict[str, Any] | None) -> str | None:
    """Resolve a selected substring from a quoted message body.

    Newer Weixin clients may send ``partial_text`` instead of the quoted span.
    When ``quotemd5`` is present it disambiguates global vs relative end indexes.

    Args:
        full_text: Cached full quoted body.
        partial: ``partial_text`` object from ``ref_msg``.

    Returns:
        Resolved substring, or ``None`` when the quote cannot be reconstructed.
    """
    if not full_text or not isinstance(partial, dict):
        return None
    start = str(partial.get("start") or "")
    end = str(partial.get("end") or "")
    if not start or not end:
        return None
    start_index = _as_int(partial.get("startindex"))
    end_index = _as_int(partial.get("endindex"))
    candidates: list[str] = []
    for mode in ("global", "relative"):
        resolved = _candidate(full_text, start, end, start_index, end_index, mode)
        if resolved and resolved not in candidates:
            candidates.append(resolved)
    expected_md5 = str(partial.get("quotemd5") or "").strip().lower()
    if not expected_md5:
        return candidates[0] if candidates else None
    for value in candidates:
        digest = hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()
        if digest == expected_md5:
            return value
    return None


def _non_negative_int(value: object) -> int:
    return max(0, _as_int(value))


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        return int(value)
    except TypeError, ValueError:
        return 0


def _nth_index(text: str, value: str, occurrence: int, from_index: int = 0) -> int:
    if not value or occurrence < 0:
        return -1
    position = from_index
    for current in range(occurrence + 1):
        position = text.find(value, position)
        if position < 0:
            return -1
        if current < occurrence:
            position += len(value)
    return position


def _candidate(
    full_text: str,
    start: str,
    end: str,
    start_index: int,
    end_index: int,
    end_search_mode: str,
) -> str | None:
    start_at = _nth_index(full_text, start, start_index)
    if start_at < 0:
        return None
    if end_search_mode == "global":
        end_at = _nth_index(full_text, end, end_index)
    else:
        end_at = _nth_index(full_text, end, end_index, start_at + len(start))
    if end_at < start_at:
        return None
    return full_text[start_at : end_at + len(end)]
