"""AstrBot 数据导入器

负责从 ZIP 备份文件恢复所有数据。
导入时进行版本校验：
- 主版本（前两位）不同时直接拒绝导入
- 小版本（第三位）不同时提示警告，用户可选择强制导入
- 版本匹配时也需要用户确认
"""

import asyncio
import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from inspect import isawaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete

from astrbot import logger
from astrbot.core.config.default import VERSION
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
)
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error

from ._importer_datetime import convert_datetime_fields
from ._importer_files import (
    backup_existing_directory,
    extract_directory_files,
    import_attachments,
    import_directories,
    list_directory_archive_files,
    validate_path_within,
)
from ._importer_kb import clear_kb_data, import_kb_metadata_tables
from ._importer_platform_stats import (
    PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT,
    InvalidCountWarnLimiter,
    merge_platform_stats_rows,
    normalize_platform_stats_entry,
    normalize_platform_stats_timestamp,
)
from ._importer_versioning import (
    ManifestLoadError,
    build_backup_summary,
    check_version_compatibility,
    get_major_version,
    load_manifest,
)

# 从共享常量模块导入
from .constants import (
    MAIN_DB_MODELS,
)

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager


def _get_major_version(version_str: str) -> str:
    return get_major_version(version_str)


def _validate_path_within(target_path: Path, base_dir: Path) -> bool:
    return validate_path_within(target_path, base_dir)


CMD_CONFIG_FILE_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")
KB_PATH = get_astrbot_knowledge_base_path()
DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT = 5
PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV = (
    "ASTRBOT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT"
)
_IMPORT_ERROR = "Backup import failed"
_PRE_CHECK_ERROR = "Backup pre-check failed"


def _load_platform_stats_invalid_count_warn_limit() -> int:
    return PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT


class _InvalidCountWarnLimiter:
    """Rate-limit warnings for invalid platform_stats count values."""

    def __init__(self, limit: int) -> None:
        self._inner = InvalidCountWarnLimiter(limit)

    def warn_invalid_count(self, value: Any, key_for_log: tuple[Any, ...]) -> None:
        self._inner.warn_invalid_count(value, key_for_log)


@dataclass
class ImportPreCheckResult:
    """导入预检查结果

    用于在实际导入前检查备份文件的版本兼容性，
    并返回确认信息让用户决定是否继续导入。
    """

    # 检查是否通过（文件有效且版本可导入）
    valid: bool = False
    # 是否可以导入（版本兼容）
    can_import: bool = False
    # 版本状态: match（完全匹配）, minor_diff（小版本差异）, major_diff（主版本不同，拒绝）
    version_status: str = ""
    # 备份文件中的 AstrBot 版本
    backup_version: str = ""
    # 当前运行的 AstrBot 版本
    current_version: str = VERSION
    # 备份创建时间
    backup_time: str = ""
    # 确认消息（显示给用户）
    confirm_message: str = ""
    # 警告消息列表
    warnings: list[str] = field(default_factory=list)
    # 错误消息（如果检查失败）
    error: str = ""
    # 备份包含的内容摘要
    backup_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "can_import": self.can_import,
            "version_status": self.version_status,
            "backup_version": self.backup_version,
            "current_version": self.current_version,
            "backup_time": self.backup_time,
            "confirm_message": self.confirm_message,
            "warnings": self.warnings,
            "error": self.error,
            "backup_summary": self.backup_summary,
        }


class ImportResult:
    """导入结果"""

    def __init__(self) -> None:
        self.success = True
        self.imported_tables: dict[str, int] = {}
        self.imported_files: dict[str, int] = {}
        self.imported_directories: dict[str, int] = {}
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def add_warning(self, msg: str) -> None:
        safe_message = redact_sensitive_text(msg)
        self.warnings.append(safe_message)
        logger.warning("%s", safe_message)

    def add_error(self, msg: str) -> None:
        safe_message = redact_sensitive_text(msg)
        self.errors.append(safe_message)
        self.success = False
        logger.error("%s", safe_message)

    def add_internal_warning(self, message: str, exc: BaseException) -> None:
        """Record a stable warning while logging the internal cause safely."""
        self.warnings.append(message)
        logger.warning("%s: %s", message, safe_error("", exc))

    def add_internal_error(self, message: str, exc: BaseException) -> None:
        """Record a stable error while logging the internal cause safely."""
        self.errors.append(message)
        self.success = False
        logger.error("%s: %s", message, safe_error("", exc))

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "imported_tables": self.imported_tables,
            "imported_files": self.imported_files,
            "imported_directories": self.imported_directories,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class DatabaseClearError(RuntimeError):
    """Raised when clearing the main database in replace mode fails."""


class AstrBotImporter:
    """AstrBot 数据导入器

    导入备份文件中的所有数据，包括：
    - 主数据库所有表
    - 知识库元数据和文档
    - 配置文件
    - 附件文件
    - 知识库多媒体文件
    - 插件目录（data/plugins）
    - 插件数据目录（data/plugin_data）
    - 配置目录（data/config）
    - T2I 模板目录（data/t2i_templates）
    - WebChat 数据目录（data/webchat）
    - 临时文件目录（data/temp）
    """

    def __init__(
        self,
        main_db: BaseDatabase,
        kb_manager: KnowledgeBaseManager | None = None,
        config_path: str = CMD_CONFIG_FILE_PATH,
        kb_root_dir: str = KB_PATH,
    ) -> None:
        self.main_db = main_db
        self.kb_manager = kb_manager
        self.config_path = config_path
        self.kb_root_dir = kb_root_dir

    async def _report_progress(
        self,
        progress_callback: Any | None,
        stage: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if progress_callback:
            await progress_callback(stage, current, total, message)

    def _load_manifest_from_backup(
        self,
        zf: zipfile.ZipFile,
        result: ImportResult,
    ) -> dict[str, Any] | None:
        try:
            return load_manifest(zf)
        except ManifestLoadError as exc:
            result.add_error(str(exc))
        return None

    async def _import_main_database_stage(
        self,
        zf: zipfile.ZipFile,
        mode: str,
        result: ImportResult,
    ) -> dict[str, list[dict]] | None:
        try:
            main_data = json.loads(zf.read("databases/main_db.json"))
            if mode == "replace":
                await self._clear_main_db()
            imported = await self._import_main_database(main_data)
            result.imported_tables.update(imported)
            return main_data
        except asyncio.CancelledError:
            raise
        except DatabaseClearError as exc:
            result.add_internal_error("清空主数据库失败", exc)
        except Exception as exc:
            result.add_internal_error("导入主数据库失败", exc)
        return None

    async def _import_knowledge_bases_stage(
        self,
        zf: zipfile.ZipFile,
        mode: str,
        result: ImportResult,
    ) -> None:
        if not self.kb_manager or "databases/kb_metadata.json" not in zf.namelist():
            return

        try:
            kb_meta_data = json.loads(zf.read("databases/kb_metadata.json"))
            if mode == "replace":
                await self._clear_kb_data()
            await self._import_knowledge_bases(zf, kb_meta_data, result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result.add_internal_warning("导入知识库失败", exc)

    def _import_config_stage(self, zf: zipfile.ZipFile, result: ImportResult) -> None:
        if "config/cmd_config.json" not in zf.namelist():
            return

        try:
            config_content = zf.read("config/cmd_config.json")
            if os.path.exists(self.config_path):
                shutil.copy2(self.config_path, f"{self.config_path}.bak")
            with open(self.config_path, "wb") as f:
                f.write(config_content)
            result.imported_files["config"] = 1
        except Exception as exc:
            result.add_internal_warning("导入配置文件失败", exc)

    async def _import_attachments_stage(
        self,
        zf: zipfile.ZipFile,
        main_data: dict[str, list[dict]],
        result: ImportResult,
    ) -> None:
        result.imported_files["attachments"] = await self._import_attachments(
            zf, main_data.get("attachments", [])
        )

    async def _import_directories_stage(
        self,
        zf: zipfile.ZipFile,
        manifest: dict[str, Any],
        result: ImportResult,
    ) -> None:
        result.imported_directories = await self._import_directories(
            zf, manifest, result
        )

    def _prepare_manifest_for_import(
        self,
        zf: zipfile.ZipFile,
        result: ImportResult,
    ) -> dict[str, Any] | None:
        manifest = self._load_manifest_from_backup(zf, result)
        if manifest is None:
            return None

        try:
            self._validate_version(manifest)
        except ValueError as exc:
            result.add_error(str(exc))
            return None

        return manifest

    async def _run_import_stage(
        self,
        progress_callback: Any | None,
        stage: str,
        start_message: str,
        end_message: str,
        action: Any,
    ) -> Any:
        await self._report_progress(progress_callback, stage, 0, 100, start_message)
        stage_result = action()
        if isawaitable(stage_result):
            stage_result = await stage_result
        await self._report_progress(progress_callback, stage, 100, 100, end_message)
        return stage_result

    def pre_check(self, zip_path: str) -> ImportPreCheckResult:
        """预检查备份文件

        在实际导入前检查备份文件的有效性和版本兼容性。
        返回检查结果供前端显示确认对话框。

        Args:
            zip_path: ZIP 备份文件路径

        Returns:
            ImportPreCheckResult: 预检查结果
        """
        result = ImportPreCheckResult()
        result.current_version = VERSION

        if not os.path.exists(zip_path):
            result.error = "备份文件不存在"
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                try:
                    manifest = load_manifest(zf)
                except ManifestLoadError as exc:
                    result.error = redact_sensitive_text(str(exc))
                    return result

                result.backup_version = manifest.get("astrbot_version", "未知")
                result.backup_time = manifest.get("exported_at", "未知")
                result.valid = True
                result.backup_summary = build_backup_summary(manifest)
                version_check = self._check_version_compatibility(result.backup_version)
                result.version_status = version_check["status"]
                result.can_import = version_check["can_import"]
                return result

        except zipfile.BadZipFile:
            result.error = "无效的 ZIP 文件"
            return result
        except Exception as exc:
            logger.warning("%s: %s", _PRE_CHECK_ERROR, safe_error("", exc))
            result.error = _PRE_CHECK_ERROR
            return result

    def _check_version_compatibility(self, backup_version: str) -> dict:
        """检查版本兼容性

        规则：
        - 主版本（前两位，如 4.9）必须一致，否则拒绝
        - 小版本（第三位，如 4.9.1 vs 4.9.2）不同时，警告但允许导入

        Returns:
            dict: {status, can_import, message}
        """
        return check_version_compatibility(backup_version, VERSION).to_dict()

    async def import_all(
        self,
        zip_path: str,
        mode: str = "replace",  # "replace" 清空后导入
        progress_callback: Any | None = None,
    ) -> ImportResult:
        """从 ZIP 文件导入所有数据

        Args:
            zip_path: ZIP 备份文件路径
            mode: 导入模式，目前仅支持 "replace"（清空后导入）
            progress_callback: 进度回调函数，接收参数 (stage, current, total, message)

        Returns:
            ImportResult: 导入结果
        """
        result = ImportResult()

        if not os.path.exists(zip_path):
            result.add_error("备份文件不存在")
            return result

        logger.info("开始导入备份")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                manifest = await self._run_import_stage(
                    progress_callback,
                    "validate",
                    "正在验证备份文件...",
                    "验证完成",
                    lambda: self._prepare_manifest_for_import(zf, result),
                )
                if manifest is None:
                    return result
                main_data = await self._run_import_stage(
                    progress_callback,
                    "main_db",
                    "正在导入主数据库...",
                    "主数据库导入完成",
                    lambda: self._import_main_database_stage(zf, mode, result),
                )
                if main_data is None:
                    return result
                await self._run_import_stage(
                    progress_callback,
                    "kb",
                    "正在导入知识库...",
                    "知识库导入完成",
                    lambda: self._import_knowledge_bases_stage(zf, mode, result),
                )
                await self._run_import_stage(
                    progress_callback,
                    "config",
                    "正在导入配置文件...",
                    "配置文件导入完成",
                    lambda: self._import_config_stage(zf, result),
                )
                await self._run_import_stage(
                    progress_callback,
                    "attachments",
                    "正在导入附件...",
                    "附件导入完成",
                    lambda: self._import_attachments_stage(zf, main_data, result),
                )
                await self._run_import_stage(
                    progress_callback,
                    "directories",
                    "正在导入插件和数据目录...",
                    "目录导入完成",
                    lambda: self._import_directories_stage(zf, manifest, result),
                )

            logger.info(
                "备份导入完成: tables=%d, files=%d, directories=%d, warnings=%d",
                len(result.imported_tables),
                len(result.imported_files),
                len(result.imported_directories),
                len(result.warnings),
            )
            return result

        except zipfile.BadZipFile:
            result.add_error("无效的 ZIP 文件")
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result.add_internal_error(_IMPORT_ERROR, exc)
            return result

    def _validate_version(self, manifest: dict) -> None:
        """验证版本兼容性 - 仅允许相同主版本导入

        注意：此方法仅在 import_all 中调用，用于双重校验。
        前端应先调用 pre_check 获取详细的版本信息并让用户确认。
        """
        backup_version = manifest.get("astrbot_version")
        if not backup_version:
            raise ValueError("备份文件缺少版本信息")

        # 使用新的版本兼容性检查
        version_check = self._check_version_compatibility(backup_version)

        if version_check["status"] == "major_diff":
            raise ValueError(version_check["message"])

        # minor_diff 和 match 都允许导入
        if version_check["status"] == "minor_diff":
            logger.warning("备份版本存在差异")

    async def _clear_main_db(self) -> None:
        """清空主数据库所有表"""
        async with self.main_db.get_db() as session:
            async with session.begin():
                for table_name, model_class in MAIN_DB_MODELS.items():
                    try:
                        await session.execute(delete(model_class))
                        logger.debug(f"已清空表 {table_name}")
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        raise DatabaseClearError("清空主数据库失败") from exc

    async def _clear_kb_data(self) -> None:
        """清空知识库数据"""
        await clear_kb_data(self.kb_manager)

    async def _import_main_database(
        self, data: dict[str, list[dict]]
    ) -> dict[str, int]:
        """导入主数据库数据"""
        imported: dict[str, int] = {}

        async with self.main_db.get_db() as session:
            async with session.begin():
                for table_name, rows in data.items():
                    model_class = MAIN_DB_MODELS.get(table_name)
                    if not model_class:
                        logger.warning("未知的备份数据表，已跳过")
                        continue
                    normalized_rows = self._preprocess_main_table_rows(table_name, rows)

                    count = 0
                    for row in normalized_rows:
                        try:
                            # 转换 datetime 字符串为 datetime 对象
                            row = self._convert_datetime_fields(row, model_class)
                            obj = model_class(**row)
                            session.add(obj)
                            count += 1
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.warning(
                                "导入记录到 %s 失败: %s",
                                table_name,
                                safe_error("", exc),
                            )

                    imported[table_name] = count
                    logger.debug(f"导入表 {table_name}: {count} 条记录")

        return imported

    def _preprocess_main_table_rows(
        self, table_name: str, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if table_name == "platform_stats":
            normalized_rows = self._merge_platform_stats_rows(rows)
            duplicate_count = len(rows) - len(normalized_rows)
            if duplicate_count > 0:
                logger.warning(
                    "检测到 %s 重复键 %d 条，已在导入前聚合",
                    table_name,
                    duplicate_count,
                )
            return normalized_rows
        return rows

    def _merge_platform_stats_rows(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return merge_platform_stats_rows(rows)

    def _normalize_platform_stats_entry(
        self,
        row: dict[str, Any],
        warn_limiter: _InvalidCountWarnLimiter,
    ) -> tuple[dict[str, Any], str | None, int]:
        normalized_row, merge_key, count = normalize_platform_stats_entry(
            row,
            warn_limiter._inner,
        )
        normalized_timestamp = None if merge_key is None else merge_key[0]
        return normalized_row, normalized_timestamp, count

    def _normalize_platform_stats_timestamp(self, value: Any) -> str | None:
        return normalize_platform_stats_timestamp(value)

    async def _import_knowledge_bases(
        self,
        zf: zipfile.ZipFile,
        kb_meta_data: dict[str, list[dict]],
        result: ImportResult,
    ) -> None:
        """导入知识库数据"""
        if not self.kb_manager:
            return

        await self._import_kb_metadata_tables(kb_meta_data, result)

        for kb_data in kb_meta_data.get("knowledge_bases", []):
            await self._import_single_knowledge_base(zf, kb_data, result)

        await self.kb_manager.load_kbs()

    async def _import_kb_metadata_tables(
        self,
        kb_meta_data: dict[str, list[dict]],
        result: ImportResult,
    ) -> None:
        await import_kb_metadata_tables(
            self.kb_manager,
            kb_meta_data,
            result.imported_tables,
            self._convert_datetime_fields,
        )

    async def _import_single_knowledge_base(
        self,
        zf: zipfile.ZipFile,
        kb_data: dict[str, Any],
        result: ImportResult,
    ) -> None:
        kb_id = kb_data.get("kb_id")
        if not kb_id:
            return

        kb_dir = Path(self.kb_root_dir) / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)

        await self._import_single_kb_documents(zf, kb_id, result)
        await self._import_single_kb_faiss_index(zf, kb_id, kb_dir, result)
        await self._import_single_kb_media_files(zf, kb_id, kb_dir, result)

    async def _import_single_kb_documents(
        self,
        zf: zipfile.ZipFile,
        kb_id: str,
        result: ImportResult,
    ) -> None:
        doc_path = f"databases/kb_{kb_id}/documents.json"
        if doc_path not in zf.namelist():
            return

        try:
            await self._import_kb_documents(kb_id, json.loads(zf.read(doc_path)))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result.add_internal_warning("导入知识库文档失败", exc)

    async def _import_single_kb_faiss_index(
        self,
        zf: zipfile.ZipFile,
        kb_id: str,
        kb_dir: Path,
        result: ImportResult,
    ) -> None:
        faiss_path = f"databases/kb_{kb_id}/index.faiss"
        if faiss_path not in zf.namelist():
            return

        try:
            with zf.open(faiss_path) as src, open(kb_dir / "index.faiss", "wb") as dst:
                dst.write(src.read())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result.add_internal_warning("导入知识库 FAISS 索引失败", exc)

    async def _import_single_kb_media_files(
        self,
        zf: zipfile.ZipFile,
        kb_id: str,
        kb_dir: Path,
        result: ImportResult,
    ) -> None:
        media_prefix = f"files/kb_media/{kb_id}/"
        for name in zf.namelist():
            if not name.startswith(media_prefix):
                continue
            try:
                rel_path = name[len(media_prefix) :]
                target_path = kb_dir / rel_path
                if not _validate_path_within(target_path, kb_dir):
                    logger.warning("媒体文件路径越界，已跳过")
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target_path, "wb") as dst:
                    dst.write(src.read())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result.add_internal_warning("导入知识库媒体文件失败", exc)

    async def _import_kb_documents(self, kb_id: str, doc_data: dict) -> None:
        """导入知识库文档到向量数据库"""
        from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage

        kb_dir = Path(self.kb_root_dir) / kb_id
        doc_db_path = kb_dir / "doc.db"

        # 初始化文档存储
        doc_storage = DocumentStorage(str(doc_db_path))
        await doc_storage.initialize()

        try:
            documents = doc_data.get("documents", [])
            for doc in documents:
                try:
                    await doc_storage.insert_document(
                        doc_id=doc.get("doc_id", ""),
                        text=doc.get("text", ""),
                        metadata=json.loads(doc.get("metadata", "{}")),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("导入文档块失败: %s", safe_error("", exc))
        finally:
            await doc_storage.close()

    async def _import_attachments(
        self,
        zf: zipfile.ZipFile,
        attachments: list[dict],
    ) -> int:
        """导入附件文件"""
        return import_attachments(zf, attachments, self.config_path)

    async def _import_directories(
        self,
        zf: zipfile.ZipFile,
        manifest: dict,
        result: ImportResult,
    ) -> dict[str, int]:
        """导入插件和其他数据目录

        Args:
            zf: ZIP 文件对象
            manifest: 备份清单
            result: 导入结果对象

        Returns:
            dict: 每个目录导入的文件数量
        """
        return import_directories(zf, manifest, result.add_warning)

    def _list_directory_archive_files(
        self, zf: zipfile.ZipFile, archive_prefix: str
    ) -> list[str]:
        return list_directory_archive_files(zf, archive_prefix)

    def _backup_existing_directory(self, target_dir: Path) -> None:
        backup_existing_directory(target_dir)

    def _extract_directory_files(
        self,
        zf: zipfile.ZipFile,
        dir_files: list[str],
        archive_prefix: str,
        target_dir: Path,
        result: ImportResult,
    ) -> int:
        return extract_directory_files(
            zf,
            dir_files,
            archive_prefix,
            target_dir,
            result.add_warning,
        )

    def _convert_datetime_fields(self, row: dict, model_class: type) -> dict:
        """转换 datetime 字符串字段为 datetime 对象"""
        return convert_datetime_fields(row, model_class)
