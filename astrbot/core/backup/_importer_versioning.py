import json
import zipfile
from dataclasses import dataclass
from typing import Any

from astrbot.core.config.default import VERSION
from astrbot.core.utils.version_comparator import VersionComparator


@dataclass(frozen=True)
class VersionCheckResult:
    status: str
    can_import: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "can_import": self.can_import,
            "message": self.message,
        }


class ManifestLoadError(ValueError):
    """Raised when the backup manifest is missing or invalid."""


def get_major_version(version_str: str) -> str:
    """Extract the major.minor portion of a version string.

    Args:
        version_str: Version string such as ``4.9.1`` or ``v4.10.0-beta``.

    Returns:
        The normalized major version string.
    """

    if not version_str:
        return "0.0"

    version = version_str.lower().replace("v", "").split("-")[0].split("+")[0]
    parts = [part for part in version.split(".") if part]
    if not parts:
        return "0.0"

    major = parts[0]
    minor = parts[1] if len(parts) > 1 else "0"
    return f"{major}.{minor}"


def load_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    """Load and parse the backup manifest.

    Args:
        zf: Backup archive.

    Returns:
        The decoded manifest payload.

    Raises:
        ManifestLoadError: If the manifest is missing or malformed.
    """

    try:
        return json.loads(zf.read("manifest.json"))
    except KeyError as exc:
        raise ManifestLoadError(
            "备份文件缺少 manifest.json，不是有效的 AstrBot 备份"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ManifestLoadError(f"manifest.json 格式错误: {exc}") from exc


def build_backup_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    """Build the summary shown by the pre-check endpoint.

    Args:
        manifest: Parsed backup manifest.

    Returns:
        A frontend-friendly summary of the backup content.
    """

    tables = manifest.get("tables", {})
    return {
        "tables": list(tables.keys()) if isinstance(tables, dict) else [],
        "has_knowledge_bases": bool(manifest.get("has_knowledge_bases", False)),
        "has_config": bool(manifest.get("has_config", False)),
        "directories": manifest.get("directories", []),
    }


def check_version_compatibility(
    backup_version: str,
    current_version: str = VERSION,
) -> VersionCheckResult:
    """Check whether a backup version can be imported.

    Args:
        backup_version: Version recorded in the backup manifest.
        current_version: Current AstrBot version.

    Returns:
        A structured compatibility result.
    """

    if not backup_version:
        return VersionCheckResult(
            status="major_diff",
            can_import=False,
            message="备份文件缺少版本信息",
        )

    backup_major = get_major_version(backup_version)
    current_major = get_major_version(current_version)
    if VersionComparator.compare_version(backup_major, current_major) != 0:
        return VersionCheckResult(
            status="major_diff",
            can_import=False,
            message=(
                f"主版本不兼容: 备份版本 {backup_version}, 当前版本 {current_version}。"
                "跨主版本导入可能导致数据损坏，请使用相同主版本的 AstrBot。"
            ),
        )

    if VersionComparator.compare_version(backup_version, current_version) != 0:
        return VersionCheckResult(
            status="minor_diff",
            can_import=True,
            message=f"小版本差异: 备份版本 {backup_version}, 当前版本 {current_version}。",
        )

    return VersionCheckResult(
        status="match",
        can_import=True,
        message="版本匹配",
    )
