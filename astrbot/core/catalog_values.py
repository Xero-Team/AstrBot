"""Immutable configuration values used by runtime catalog descriptors."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


def freeze_catalog_value(value: Any) -> Any:
    """Recursively freeze JSON-like descriptor data.

    Adapter declarations are class metadata, so a caller must not be able to
    mutate a declaration after its decorator has run.
    """

    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: freeze_catalog_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(freeze_catalog_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_catalog_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze_catalog_value(item) for item in value)
    return copy.deepcopy(value)


def thaw_catalog_value(value: Any) -> Any:
    """Return an isolated mutable copy suitable for a response or config."""

    if isinstance(value, Mapping):
        return {key: thaw_catalog_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_catalog_value(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_hashable(item) for item in value}
    return copy.deepcopy(value)


def _thaw_hashable(value: Any) -> Any:
    if isinstance(value, tuple):
        return tuple(_thaw_hashable(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_thaw_hashable(item) for item in value)
    if isinstance(value, (list, dict, set)):
        return tuple(sorted(map(str, value)))
    return copy.deepcopy(value)
