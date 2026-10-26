"""Leaf Dashboard Extension Protocol v1 manifest value types.

This module intentionally depends only on the standard library so manifest
types can be referenced by plugin metadata without importing the extension
registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DashboardPageAsset:
    path: str
    resolved_path: Path
    sha256: str
    size: int
    content_type: str


@dataclass(frozen=True)
class DashboardPageManifest:
    id: str
    title: str
    module: str
    assets_manifest: str
    styles: tuple[str, ...]
    icon: str | None
    actions: tuple[str, ...]
    assets: Mapping[str, DashboardPageAsset]


@dataclass(frozen=True)
class DashboardExtensionManifest:
    extension_id: str
    pages: tuple[DashboardPageManifest, ...]
