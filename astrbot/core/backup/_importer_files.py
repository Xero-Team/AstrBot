from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from astrbot.core import logger
from astrbot.core.utils.io import ensure_dir
from astrbot.core.utils.version_comparator import VersionComparator

from .constants import get_backup_directories


def validate_path_within(target_path: Path, base_dir: Path) -> bool:
    """Validate that a resolved target path stays within its base directory.

    Args:
        target_path: Candidate extraction target.
        base_dir: Allowed root directory for the extracted file.

    Returns:
        True when the resolved target path is inside the resolved base directory.
    """

    try:
        resolved = target_path.resolve(strict=False)
        base_resolved = base_dir.resolve(strict=False)
        return resolved.is_relative_to(base_resolved)
    except (OSError, ValueError):
        return False


def import_attachments(
    zf: zipfile.ZipFile,
    attachments: list[dict[str, Any]],
    config_path: str,
) -> int:
    """Import attachment files from the archive.

    Args:
        zf: Backup archive.
        attachments: Attachment metadata rows from the main database backup.
        config_path: Runtime config file path used to locate the data directory.

    Returns:
        The number of successfully restored attachment files.
    """

    count = 0
    attachments_dir = Path(config_path).parent / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    attachment_targets = _build_attachment_targets(attachments)

    for name in list_directory_archive_files(zf, "files/attachments/"):
        try:
            target_path = attachment_targets.get(
                Path(name).stem,
                attachments_dir / Path(name).name,
            )
            if not validate_path_within(target_path, attachments_dir):
                logger.warning("附件路径越界，已跳过: %s", target_path)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target_path, "wb") as dst:
                dst.write(src.read())
            count += 1
        except Exception as exc:
            logger.warning("导入附件 %s 失败: %s", name, exc)

    return count


def import_directories(
    zf: zipfile.ZipFile,
    manifest: dict[str, Any],
    add_warning: Any,
) -> dict[str, int]:
    """Import backed-up directories such as plugins and plugin data.

    Args:
        zf: Backup archive.
        manifest: Backup manifest.
        add_warning: Callback used to record non-fatal import warnings.

    Returns:
        Per-directory imported file counts.
    """

    dir_stats: dict[str, int] = {}
    if VersionComparator.compare_version(manifest.get("version", "1.0"), "1.1") < 0:
        logger.info("备份版本不支持目录备份，跳过目录导入")
        return dir_stats

    backup_directories = get_backup_directories()
    for dir_name in manifest.get("directories", []):
        target_dir_str = backup_directories.get(dir_name)
        if target_dir_str is None:
            add_warning(f"未知的目录类型: {dir_name}")
            continue

        archive_prefix = f"directories/{dir_name}/"
        dir_files = list_directory_archive_files(zf, archive_prefix)
        if not dir_files:
            continue

        target_dir = Path(target_dir_str)
        try:
            backup_existing_directory(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            file_count = extract_directory_files(
                zf,
                dir_files,
                archive_prefix,
                target_dir,
                add_warning,
            )
            dir_stats[dir_name] = file_count
            logger.debug("导入目录 %s: %d 个文件", dir_name, file_count)
        except Exception as exc:
            add_warning(f"导入目录 {dir_name} 失败: {exc}")
            dir_stats[dir_name] = 0

    return dir_stats


def list_directory_archive_files(zf: zipfile.ZipFile, archive_prefix: str) -> list[str]:
    return [
        name
        for name in zf.namelist()
        if name.startswith(archive_prefix) and name != archive_prefix
    ]


def backup_existing_directory(target_dir: Path) -> None:
    if not target_dir.exists():
        return

    backup_path = Path(f"{target_dir}.bak")
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.move(str(target_dir), str(backup_path))
    logger.debug("已备份现有目录 %s 到 %s", target_dir, backup_path)


def extract_directory_files(
    zf: zipfile.ZipFile,
    dir_files: list[str],
    archive_prefix: str,
    target_dir: Path,
    add_warning: Any,
) -> int:
    file_count = 0
    for name in dir_files:
        try:
            rel_path = name[len(archive_prefix) :]
            if not rel_path:
                continue

            target_path = target_dir / rel_path
            if not validate_path_within(target_path, target_dir):
                add_warning(f"文件路径越界，已跳过: {name}")
                continue

            if zf.getinfo(name).is_dir():
                ensure_dir(target_path)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target_path, "wb") as dst:
                dst.write(src.read())
            file_count += 1
        except Exception as exc:
            add_warning(f"导入文件 {name} 失败: {exc}")
    return file_count


def _build_attachment_targets(
    attachments: list[dict[str, Any]],
) -> dict[str, Path]:
    targets: dict[str, Path] = {}
    for attachment in attachments:
        attachment_id = attachment.get("attachment_id")
        original_path = attachment.get("path")
        if (
            isinstance(attachment_id, str)
            and attachment_id
            and attachment_id not in targets
            and isinstance(original_path, str)
            and original_path
        ):
            targets[attachment_id] = Path(original_path)
    return targets
