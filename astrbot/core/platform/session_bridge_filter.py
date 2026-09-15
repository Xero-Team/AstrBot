"""Match/except evaluation for one session-bridge directed edge."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from astrbot.core.auth.models import Role

from .message_protocol import NativeContent, PortablePart

FILTER_DIMENSIONS = ("subjects", "roles", "text")
FILTER_SIDES = ("match", "except")
MAX_FILTER_ITEMS = 16
MAX_PATTERN_LENGTH = 256
FILTER_ROLES = frozenset(role.value for role in Role)
COMMAND_DIMENSIONS = {
    "subject": "subjects",
    "role": "roles",
    "text": "text",
}

_RULE_ID_CHARS = frozenset("0123456789abcdef")


def coerce_filter_side(payload: object) -> dict[str, list[str]]:
    """Return a copy of one match or except document with known list keys."""
    if not isinstance(payload, Mapping):
        return {}
    out: dict[str, list[str]] = {}
    for key in FILTER_DIMENSIONS:
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        values = [item for item in raw if isinstance(item, str) and item]
        if values:
            out[key] = list(values)
    return out


def compact_filter_side(payload: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """Drop empty dimensions so an empty document stays ``{}``."""
    out: dict[str, list[str]] = {}
    for key in FILTER_DIMENSIONS:
        values = [item for item in payload.get(key, ()) if item]
        if values:
            out[key] = list(values)
    return out


def has_filter_constraints(payload: Mapping[str, Sequence[str]]) -> bool:
    """Return True when at least one dimension has a value."""
    return any(payload.get(key) for key in FILTER_DIMENSIONS)


def portable_text(content: Sequence[object]) -> str:
    """Concatenate PortablePart string values; ignore media and NativeContent."""
    parts: list[str] = []
    for item in content:
        if isinstance(item, NativeContent):
            continue
        if not isinstance(item, PortablePart):
            continue
        if isinstance(item.value, str):
            parts.append(item.value)
    return "".join(parts)


def compile_text_pattern(pattern: str) -> re.Pattern[str]:
    """Compile one stdlib ``re`` pattern at save time.

    Args:
        pattern: Caller-supplied search pattern.

    Returns:
        The compiled pattern. Matching is Unicode and case-sensitive unless
        the pattern itself enables ``(?i)``.

    Raises:
        ValueError: Pattern is empty, longer than 256 characters, or invalid.
    """
    if not pattern or len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError("Invalid filter pattern")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError("Invalid filter pattern") from exc


def validate_filter_value(dimension: str, value: str) -> str:
    """Normalize one appended filter value.

    Args:
        dimension: ``subjects``, ``roles``, or ``text``.
        value: Raw command value.

    Returns:
        The stored value.

    Raises:
        ValueError: The value is empty, an unknown role, or an invalid pattern.
    """
    text = value.strip() if dimension != "text" else value
    if dimension == "text":
        compile_text_pattern(text)
        return text
    if not text:
        raise ValueError("Invalid filter arguments")
    if dimension == "roles":
        if text not in FILTER_ROLES:
            raise ValueError("Invalid filter role")
        return text
    if dimension != "subjects":
        raise ValueError("Invalid filter arguments")
    return text


def append_filter_value(
    payload: Mapping[str, Sequence[str]],
    dimension: str,
    value: str,
) -> dict[str, list[str]]:
    """Append one value onto a dimension, rejecting a 17th distinct item.

    Args:
        payload: Current match or except document.
        dimension: ``subjects``, ``roles``, or ``text``.
        value: Already-validated value.

    Returns:
        Compacted document including the new value.

    Raises:
        ValueError: The dimension already has 16 values and ``value`` is new.
    """
    current = coerce_filter_side(payload)
    items = list(current.get(dimension, []))
    if value in items:
        return compact_filter_side(current)
    if len(items) >= MAX_FILTER_ITEMS:
        raise ValueError("Filter limit exceeded")
    items.append(value)
    current[dimension] = items
    return compact_filter_side(current)


def parse_rule_id(token: str) -> str:
    """Return a 12-character lowercase hex rule id."""
    if len(token) != 12 or any(char not in _RULE_ID_CHARS for char in token):
        raise ValueError("Invalid filter arguments")
    return token


def _patterns_match(patterns: Sequence[str], text: str) -> bool:
    for pattern in patterns:
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        if compiled.search(text) is not None:
            return True
    return False


def _dimension_hits(
    payload: Mapping[str, Sequence[str]],
    dimension: str,
    *,
    subject_id: str | None,
    has_sender: bool,
    role: str,
    text: str,
) -> bool:
    values = list(payload.get(dimension, ()))
    if not values:
        return True
    if dimension == "subjects":
        if not has_sender or subject_id is None:
            return False
        return subject_id in values
    if dimension == "roles":
        return role in values
    if not text:
        return False
    return _patterns_match(values, text)


def side_matches(
    payload: Mapping[str, Sequence[str]],
    *,
    subject_id: str | None,
    has_sender: bool,
    role: str,
    text: str,
) -> bool:
    """Return whether every set dimension on one side hits.

    Empty documents hit. Dimensions AND; values in one dimension OR.
    Missing sender fails ``subjects``. Empty body fails ``text``.
    """
    if not has_filter_constraints(payload):
        return True
    return all(
        _dimension_hits(
            payload,
            dimension,
            subject_id=subject_id,
            has_sender=has_sender,
            role=role,
            text=text,
        )
        for dimension in FILTER_DIMENSIONS
    )


def evaluate_filter(
    match: Mapping[str, Sequence[str]] | None,
    except_: Mapping[str, Sequence[str]] | None,
    *,
    subject_id: str | None,
    has_sender: bool,
    role: str,
    text: str,
) -> bool:
    """Return True when the snapshot should be forwarded.

    Empty match and except forward. Match dimensions AND; except hit drops.
    """
    match_doc = coerce_filter_side(match)
    except_doc = coerce_filter_side(except_)
    kwargs: dict[str, Any] = {
        "subject_id": subject_id,
        "has_sender": has_sender,
        "role": role,
        "text": text,
    }
    if not side_matches(match_doc, **kwargs):
        return False
    if not has_filter_constraints(except_doc):
        return True
    return not side_matches(except_doc, **kwargs)
