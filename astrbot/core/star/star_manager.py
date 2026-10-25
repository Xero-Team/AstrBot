"""Composition root for the instance-owned plugin runtime collaborators."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_path,
    get_astrbot_plugin_path,
)
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.utils.shared_preferences import SharedPreferences

from .dashboard_extension import DashboardExtensionRegistry
from .plugin_catalog import PluginCatalog
from .plugin_context import PluginContext
from .plugin_extension_coordinator import PluginExtensionCoordinator
from .plugin_lifecycle import PluginLifecycle
from .plugin_package_installer import PluginPackageInstaller
from .plugin_runtime_loader import PluginRuntimeLoader


class PluginManager:
    """Compose the isolated plugin collaborators for one core runtime.

    This class deliberately owns no plugin declarations, failure records,
    package state, or lifecycle methods itself.  Consumers select the narrow
    collaborator matching their need instead of treating a manager as a
    service locator.
    """

    __slots__ = ("catalog", "extensions", "loader", "packages", "lifecycle")

    def __init__(
        self,
        execution_context: CoreExecutionContext,
        config: AstrBotConfig,
        preferences: SharedPreferences,
        pip_installer: PipInstaller,
        catalogs: RuntimeCatalogs,
    ) -> None:
        del config
        registry = execution_context.dashboard_extension_registry
        if not isinstance(registry, DashboardExtensionRegistry):
            raise RuntimeError(
                "CoreExecutionContext must own DashboardExtensionRegistry before "
                "PluginManager composition",
            )

        plugin_store_path = get_astrbot_plugin_path()
        plugin_config_path = get_astrbot_config_path()
        reserved_plugin_path = os.path.join(
            get_astrbot_path(),
            "astrbot",
            "builtin_stars",
        )
        background_tasks: set[asyncio.Task[Any]] = set()

        self.catalog = PluginCatalog(catalogs)
        self.extensions = PluginExtensionCoordinator(registry)
        plugin_context = PluginContext.from_execution_context(execution_context)
        self.packages = PluginPackageInstaller(
            execution_context=execution_context,
            catalogs=catalogs,
            pip_installer=pip_installer,
            plugin_store_path=plugin_store_path,
            plugin_config_path=plugin_config_path,
            background_tasks=background_tasks,
        )
        self.loader = PluginRuntimeLoader(
            execution_context=execution_context,
            catalog=self.catalog,
            extensions=self.extensions,
            plugin_context=plugin_context,
            preferences=preferences,
            packages=self.packages,
            plugin_store_path=plugin_store_path,
            plugin_config_path=plugin_config_path,
            reserved_plugin_path=reserved_plugin_path,
        )
        self.lifecycle = PluginLifecycle(
            refresh_platform_commands=execution_context.refresh_platform_commands,
            catalog=self.catalog,
            loader=self.loader,
            packages=self.packages,
            extensions=self.extensions,
            preferences=preferences,
            plugin_store_path=plugin_store_path,
            reserved_plugin_path=reserved_plugin_path,
            background_tasks=background_tasks,
        )
        plugin_context._bind_plugin_lifecycle_control(self.lifecycle)
        self.lifecycle.start()


__all__ = ["PluginManager"]
