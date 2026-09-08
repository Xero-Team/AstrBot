import re
from collections.abc import Iterable, Mapping
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def interpolate_placeholders(template: str, values: Mapping[str, object]) -> str:
    """Replace ``{{identifier}}`` for keys present in ``values``.

    Unknown ``{{identifier}}`` stays literal. ``{name}`` is not a placeholder.
    Values are inserted once and are not scanned for further placeholders.
    ``None`` becomes ``""``; other values use ``str(value)``. Identifiers are
    ``[A-Za-z_][A-Za-z0-9_]*`` with no whitespace inside the braces.

    Args:
        template: Prompt text that may contain ``{{identifier}}`` slots.
        values: Allow-list of names to substitute.

    Returns:
        The interpolated string.
    """

    def replacer(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            return match.group(0)
        value = values[name]
        if value is None:
            return ""
        return str(value)

    return _PLACEHOLDER_RE.sub(replacer, template)


def normalize_and_dedupe_strings(items: Iterable[Any] | None) -> list[str]:
    if items is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized
