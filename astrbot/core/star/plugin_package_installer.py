"""Download, stage, validate, and update plugin packages."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from astrbot import logger
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path
from astrbot.core.utils.io import remove_dir
from astrbot.core.utils.metrics import MetricsSink
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.utils.task_utils import create_tracked_task

from .plugin_runtime_common import ensure_plugin_requirements
from .updator import PluginUpdator

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext

    from .star import StarMetadata


class PluginLoaderPort(Protocol):
    """Minimal loader surface needed while staging a plugin package."""

    @staticmethod
    def plugin_dir_name_from_metadata(plugin_path: str) -> str: ...

    @staticmethod
    def load_metadata(plugin_path: str) -> StarMetadata: ...

    def record_failed_install(
        self,
        *,
        dir_name: str,
        plugin_path: str,
        error: Exception,
    ) -> None: ...


LoadPlugin = Callable[..., Awaitable[tuple[bool, str | None]]]
ReloadPlugin = Callable[[str | None], Awaitable[tuple[bool, str | None]]]
TerminatePlugin = Callable[["StarMetadata"], Awaitable[None]]
STAGED_PLUGIN_DIR_PREFIXES = (
    ".plugin-install-",
    ".plugin-upload-",
    ".plugin-backup-",
)


class PluginPackageInstaller:
    """Own package-file mutations for one runtime's plugin store."""

    def __init__(
        self,
        *,
        execution_context: CoreExecutionContext,
        catalogs: RuntimeCatalogs,
        pip_installer: PipInstaller,
        plugin_store_path: str,
        plugin_config_path: str,
        background_tasks: set[asyncio.Task[Any]],
        metrics: MetricsSink,
    ) -> None:
        self._execution_context = execution_context
        self._catalogs = catalogs
        self._pip_installer = pip_installer
        self._plugin_store_path = plugin_store_path
        self._plugin_config_path = plugin_config_path
        self._background_tasks = background_tasks
        self._metrics = metrics
        self._updator = PluginUpdator()

    @property
    def store_path(self) -> str:
        """Return the user-plugin root owned by this package installer."""
        return self._plugin_store_path

    @property
    def config_path(self) -> str:
        """Return the plugin configuration root owned by this installer."""
        return self._plugin_config_path

    async def ensure_requirements(
        self,
        plugin_dir_path: str,
        plugin_label: str,
    ) -> None:
        """Install the requirement set for a staged or installed plugin."""
        await ensure_plugin_requirements(
            plugin_dir_path=plugin_dir_path,
            plugin_label=plugin_label,
            pip_installer=self._pip_installer,
        )

    def prefer_installed_dependencies(self, requirements_path: str) -> None:
        """Prioritize already installed plugin dependencies during import recovery."""
        self._pip_installer.prefer_installed_dependencies(
            requirements_path=requirements_path,
        )

    @staticmethod
    def _read_plugin_info(plugin_path: str, plugin) -> dict[str, str | None] | None:
        readme_content = None
        readme_path = Path(plugin_path, "README.md")
        if not readme_path.exists():
            readme_path = Path(plugin_path, "readme.md")
        if readme_path.exists():
            try:
                readme_content = readme_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("读取插件 README.md 失败 %s: %s", plugin_path, exc)
        if plugin is None:
            return None
        return {
            "repo": plugin.repo,
            "readme": readme_content,
            "name": plugin.name,
        }

    def _plugin_for_directory(self, dir_name: str):
        return next(
            (
                plugin
                for plugin in self._catalogs.plugins.all()
                if plugin.root_dir_name == dir_name
            ),
            None,
        )

    def _plugin_for_name(self, name: str):
        return self._catalogs.plugins.get_by_name(name)

    def _staging_root(self) -> Path:
        temp_root = Path(get_astrbot_system_tmp_path())
        temp_root.mkdir(parents=True, exist_ok=True)
        return temp_root

    @staticmethod
    def _is_within_root(fullpath: str, base_path: str) -> bool:
        """Return True when `fullpath` is `base_path` or a child of it."""
        if not fullpath.startswith(base_path):
            return False
        return fullpath == base_path or fullpath.startswith(base_path + os.sep)

    @staticmethod
    def _join_under_root(base_path: str, *parts: str) -> str:
        """Join `parts` onto `base_path` and reject values that escape it."""
        base_path = os.path.normpath(base_path)
        fullpath = os.path.normpath(os.path.join(base_path, *parts))
        if not fullpath.startswith(base_path):
            raise Exception("插件路径不合法。")
        if not PluginPackageInstaller._is_within_root(fullpath, base_path):
            raise Exception("插件路径不合法。")
        return fullpath

    @staticmethod
    def _confine_path(path: str | Path, *roots: Path) -> str:
        """Normalize `path` and reject values that escape every allowed root."""
        fullpath = os.path.normpath(str(path))
        for root in roots:
            base_path = os.path.normpath(str(root))
            if not fullpath.startswith(base_path):
                continue
            if PluginPackageInstaller._is_within_root(fullpath, base_path):
                return fullpath
        raise Exception("插件路径不合法。")

    @staticmethod
    def _log_token(value: str) -> str:
        return value.replace("\r", "").replace("\n", "")

    async def install_from_repository(
        self,
        *,
        repo_url: str,
        proxy: str,
        ignore_version_check: bool,
        download_url: str,
        loader: PluginLoaderPort,
        load_plugin: LoadPlugin,
        reload_plugin: ReloadPlugin | None = None,
        terminate_plugin: TerminatePlugin | None = None,
    ) -> dict[str, str | None] | None:
        """Download a plugin and publish it only after loading succeeds."""
        create_tracked_task(
            self._background_tasks,
            self._metrics.upload(et="install_star", repo=repo_url),
            name="metric:install-star",
        )
        with tempfile.TemporaryDirectory(
            dir=self._staging_root(),
            prefix=".plugin-install-",
        ) as staging_dir:
            plugin_path = await self._updator.install(
                repo_url,
                proxy,
                download_url=download_url,
                target_dir=Path(staging_dir) / "plugin",
            )
            return await self._install_from_staged_directory(
                plugin_path,
                ignore_version_check=ignore_version_check,
                loader=loader,
                load_plugin=load_plugin,
                reload_plugin=reload_plugin,
                terminate_plugin=terminate_plugin,
            )

    async def install_from_file(
        self,
        *,
        zip_file_path: str,
        ignore_version_check: bool,
        loader: PluginLoaderPort,
        load_plugin: LoadPlugin,
        reload_plugin: ReloadPlugin | None = None,
        terminate_plugin: TerminatePlugin | None = None,
    ) -> dict[str, str | None] | None:
        """Extract a plugin upload and publish or replace the same installed plugin."""
        with tempfile.TemporaryDirectory(
            dir=self._staging_root(),
            prefix=".plugin-upload-",
        ) as staging_dir:
            plugin_path = Path(staging_dir) / "plugin"
            self._updator.unzip_file(zip_file_path, str(plugin_path))
            plugin_info = await self._install_from_staged_directory(
                str(plugin_path),
                ignore_version_check=ignore_version_check,
                loader=loader,
                load_plugin=load_plugin,
                reload_plugin=reload_plugin,
                terminate_plugin=terminate_plugin,
            )
        try:
            Path(zip_file_path).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("删除插件压缩包失败: %s", exc)
        if plugin_info and plugin_info.get("repo"):
            create_tracked_task(
                self._background_tasks,
                self._metrics.upload(et="install_star_f", repo=plugin_info["repo"]),
                name="metric:install-star-success",
            )
        return plugin_info

    async def _install_from_staged_directory(
        self,
        plugin_path: str,
        *,
        ignore_version_check: bool,
        loader: PluginLoaderPort,
        load_plugin: LoadPlugin,
        reload_plugin: ReloadPlugin | None,
        terminate_plugin: TerminatePlugin | None,
    ) -> dict[str, str | None] | None:
        """Install a staged plugin directory, restoring old code on update failure."""
        plugin_path = self._confine_path(
            plugin_path,
            self._staging_root(),
            Path(self._plugin_store_path),
        )
        desti_dir = plugin_path
        dir_name = Path(plugin_path).name
        track_failed_install = False
        try:
            metadata_dir_name = loader.plugin_dir_name_from_metadata(plugin_path)
            plugin = self._plugin_for_name(metadata_dir_name)
            target_plugin_path = self._join_under_root(
                self._plugin_store_path,
                plugin.root_dir_name
                if plugin and plugin.root_dir_name
                else metadata_dir_name,
            )
            target = Path(target_plugin_path)
            if plugin and plugin.reserved:
                raise Exception("该插件是 AstrBot 保留插件，无法更新。")
            if target.exists():
                if (
                    target.is_symlink()
                    or not target.is_dir()
                    or loader.plugin_dir_name_from_metadata(target_plugin_path)
                    != metadata_dir_name
                ):
                    raise Exception(f"安装失败：目录 {target.name} 已存在。")
                return await self._replace_installed_plugin(
                    plugin_path=plugin_path,
                    target_plugin_path=target_plugin_path,
                    plugin=plugin,
                    ignore_version_check=ignore_version_check,
                    loader=loader,
                    load_plugin=load_plugin,
                    reload_plugin=reload_plugin,
                    terminate_plugin=terminate_plugin,
                )

            track_failed_install = True
            dir_name = target.name
            desti_dir = target_plugin_path
            store_root = os.path.normpath(self._plugin_store_path)
            if not desti_dir.startswith(store_root):
                raise Exception("插件路径不合法。")
            if not self._is_within_root(desti_dir, store_root):
                raise Exception("插件路径不合法。")
            shutil.move(plugin_path, desti_dir)
            loader.load_metadata(plugin_path=desti_dir)
            await self.ensure_requirements(desti_dir, dir_name)
            success, error_message = await load_plugin(
                specified_dir_name=dir_name,
                ignore_version_check=ignore_version_check,
            )
            if not success:
                raise Exception(
                    error_message
                    or f"安装插件 {dir_name} 失败，请检查插件依赖或兼容性。"
                )
            return self._read_plugin_info(
                desti_dir, self._plugin_for_directory(dir_name)
            )
        except Exception as exc:
            if track_failed_install:
                loader.record_failed_install(
                    dir_name=dir_name,
                    plugin_path=desti_dir,
                    error=exc,
                )
            logger.warning(
                "安装插件 %s 失败，插件安装目录：%s",
                self._log_token(dir_name),
                self._log_token(desti_dir),
            )
            raise

    async def _replace_installed_plugin(
        self,
        *,
        plugin_path: str,
        target_plugin_path: str,
        plugin,
        ignore_version_check: bool,
        loader: PluginLoaderPort,
        load_plugin: LoadPlugin,
        reload_plugin: ReloadPlugin | None,
        terminate_plugin: TerminatePlugin | None,
    ) -> dict[str, str | None] | None:
        """Replace an installed plugin directory and restore it if loading fails."""
        dir_name = Path(target_plugin_path).name
        loader.load_metadata(plugin_path=plugin_path)
        await self.ensure_requirements(plugin_path, dir_name)
        backup_dir = Path(
            tempfile.mkdtemp(
                dir=self._staging_root(),
                prefix=".plugin-backup-",
            )
        )
        backup_path = Path(self._join_under_root(str(backup_dir), dir_name))
        backup_complete = False
        keep_backup = False
        try:
            if plugin is not None and terminate_plugin is not None:
                try:
                    await terminate_plugin(plugin)
                except Exception:
                    logger.warning("插件 %s 未能干净终止", dir_name, exc_info=True)
            shutil.copytree(target_plugin_path, backup_path, symlinks=True)
            backup_complete = True
            keep_backup = True
            store_root = os.path.normpath(self._plugin_store_path)
            if not target_plugin_path.startswith(store_root):
                raise Exception("插件路径不合法。")
            if not self._is_within_root(target_plugin_path, store_root):
                raise Exception("插件路径不合法。")
            remove_dir(target_plugin_path)
            shutil.move(plugin_path, target_plugin_path)
            success, error_message = await self._load_replaced_plugin(
                plugin,
                dir_name,
                ignore_version_check=ignore_version_check,
                load_plugin=load_plugin,
                reload_plugin=reload_plugin,
            )
            if not success:
                raise Exception(error_message or f"更新插件 {dir_name} 失败。")
            keep_backup = False
            return self._read_plugin_info(
                target_plugin_path,
                self._plugin_for_directory(dir_name) or plugin,
            )
        except BaseException:
            try:
                if backup_complete:
                    if Path(target_plugin_path).exists():
                        remove_dir(target_plugin_path)
                    shutil.copytree(backup_path, target_plugin_path, symlinks=True)
                restored, restore_error = await self._load_replaced_plugin(
                    plugin,
                    dir_name,
                    ignore_version_check=True,
                    load_plugin=load_plugin,
                    reload_plugin=reload_plugin,
                )
                if not restored:
                    logger.error(
                        "恢复插件 %s 失败: %s",
                        dir_name,
                        restore_error,
                    )
                else:
                    keep_backup = False
            except Exception:
                logger.exception(
                    "恢复插件 %s 失败；备份目录: %s",
                    dir_name,
                    backup_path,
                )
            raise
        finally:
            if not keep_backup:
                try:
                    remove_dir(str(backup_dir))
                except Exception:
                    logger.warning("删除插件备份失败: %s", backup_dir, exc_info=True)
            else:
                logger.warning("保留插件备份以便恢复: %s", backup_path)

    async def _load_replaced_plugin(
        self,
        plugin,
        dir_name: str,
        *,
        ignore_version_check: bool,
        load_plugin: LoadPlugin,
        reload_plugin: ReloadPlugin | None,
    ) -> tuple[bool, str | None]:
        if plugin is not None and reload_plugin is not None:
            return await reload_plugin(plugin.name)
        return await load_plugin(
            specified_dir_name=dir_name,
            ignore_version_check=ignore_version_check,
        )

    async def update(
        self,
        plugin_name: str,
        *,
        proxy: str = "",
        download_url: str = "",
        repo_url: str = "",
        loader: PluginLoaderPort,
        reload_plugin: ReloadPlugin,
    ) -> None:
        """Update an installed non-bundled plugin and reload it."""
        plugin = self._catalogs.plugins.get_by_name(plugin_name)
        if not plugin:
            raise Exception("插件不存在。")
        if plugin.reserved:
            raise Exception("该插件是 AstrBot 保留插件，无法更新。")

        await self._updator.update(
            plugin,
            proxy=proxy,
            download_url=download_url,
            repo_url=repo_url,
        )
        if plugin.root_dir_name:
            plugin_dir_path = os.path.join(
                self._plugin_store_path, plugin.root_dir_name
            )
            loader.load_metadata(plugin_path=plugin_dir_path)
            await self.ensure_requirements(plugin_dir_path, plugin_name)
        await reload_plugin(plugin_name)

    async def cleanup_optional_artifacts(
        self,
        *,
        root_dir_name: str,
        plugin_label: str,
        plugin_id: str | None,
        delete_config: bool,
        delete_data: bool,
    ) -> None:
        """Delete optional configuration, files, and KV state for an uninstall."""
        if delete_config:
            config_file = os.path.join(
                self._plugin_config_path,
                f"{root_dir_name}_config.json",
            )
            if os.path.exists(config_file):
                try:
                    os.remove(config_file)
                    logger.info("已删除插件 %s 的配置文件", plugin_label)
                except OSError as exc:
                    logger.warning("删除插件配置文件失败 (%s): %s", plugin_label, exc)

        if not delete_data:
            return
        data_base_dir = os.path.dirname(self._plugin_store_path)
        for data_dir_name in ("plugin_data", "plugins_data"):
            plugin_data_dir = os.path.join(data_base_dir, data_dir_name, root_dir_name)
            if os.path.exists(plugin_data_dir):
                try:
                    remove_dir(plugin_data_dir)
                    logger.info(
                        "已删除插件 %s 的持久化数据 (%s)",
                        plugin_label,
                        data_dir_name,
                    )
                except OSError as exc:
                    logger.warning(
                        "删除插件持久化数据失败 (%s, %s): %s",
                        data_dir_name,
                        plugin_label,
                        exc,
                    )
        if plugin_id:
            try:
                await self._execution_context.database.clear_preferences(
                    "plugin",
                    plugin_id,
                )
                logger.info("已删除插件 %s 的偏好设置 (%s)", plugin_label, plugin_id)
            except Exception as exc:
                logger.warning("删除插件偏好设置失败 (%s): %s", plugin_label, exc)
