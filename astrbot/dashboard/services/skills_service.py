import os
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.datastructures import UploadFile

from astrbot import logger
from astrbot.core.computer.computer_client import ComputerRuntime
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.star.star import PluginRegistry
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.dashboard.upload_utils import save_upload_to_path

_SKILL_NAME_RE = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9._-]+$")
_SKILL_FILE_MAX_BYTES = 512 * 1024
_EDITABLE_SKILL_FILE_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
_EDITABLE_SKILL_FILENAMES = {"Dockerfile", "Makefile"}


class SkillsServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SkillsOperationResult:
    ok: bool = True
    data: dict | list | None = None
    message: str | None = None


@dataclass
class SkillArchive:
    path: Path
    filename: str


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _next_available_temp_path(temp_dir: str, filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = filename
    index = 1
    while os.path.exists(os.path.join(temp_dir, candidate)):
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return os.path.join(temp_dir, candidate)


class SkillsService:
    def __init__(
        self,
        config: AstrBotConfig,
        computer_runtime: ComputerRuntime,
        skill_manager: SkillManager,
        *,
        demo_mode: bool,
        plugins: PluginRegistry | None = None,
    ) -> None:
        self.config = config
        self.computer_runtime = computer_runtime
        self.skill_manager = skill_manager
        self.demo_mode = demo_mode
        self.plugins = plugins

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    def _ensure_mutation_allowed(self) -> None:
        if self.demo_mode:
            raise SkillsServiceError(
                "You are not permitted to do this operation in demo mode"
            )

    @staticmethod
    def _validate_skill_name(name: object) -> str:
        skill_name = str(name or "").strip()
        if not skill_name:
            raise SkillsServiceError("Missing skill name")
        if not _SKILL_NAME_RE.fullmatch(skill_name):
            raise SkillsServiceError("Invalid skill name")
        return skill_name

    def _is_readonly_skill(self, name: str) -> bool:
        return self.skill_manager.is_plugin_skill(
            name
        ) or self.skill_manager.is_builtin_skill(name)

    def _ensure_skill_mutable(self, name: str) -> None:
        if self._is_readonly_skill(name):
            raise SkillsServiceError(
                "Preset and plugin-provided skills are read-only.",
                status_code=403,
            )

    def resolve_local_skill_dir(self, name: str) -> Path:
        skill_name = self._validate_skill_name(name)

        skill_mgr = self.skill_manager
        plugin_skill_dir = skill_mgr._get_plugin_skill_dir(skill_name)
        if skill_mgr.is_plugin_skill(skill_name) and plugin_skill_dir is not None:
            try:
                return plugin_skill_dir.resolve(strict=True)
            except FileNotFoundError as exc:
                raise SkillsServiceError(
                    "Local skill not found",
                    status_code=404,
                ) from exc

        builtin_skill_dir = skill_mgr._get_builtin_skill_dir(skill_name)
        if skill_mgr.is_builtin_skill(skill_name) and builtin_skill_dir is not None:
            try:
                return builtin_skill_dir.resolve(strict=True)
            except FileNotFoundError as exc:
                raise SkillsServiceError(
                    "Local skill not found",
                    status_code=404,
                ) from exc

        try:
            skills_root = Path(skill_mgr.skills_root).resolve(strict=True)
        except FileNotFoundError as exc:
            raise SkillsServiceError("Local skill not found", status_code=404) from exc

        skill_dir: Path | None = None
        try:
            for entry in skills_root.iterdir():
                if os.path.normcase(entry.name) != os.path.normcase(skill_name):
                    continue
                resolved_entry = entry.resolve(strict=True)
                if not resolved_entry.is_relative_to(skills_root):
                    raise SkillsServiceError("Invalid skill path")
                skill_dir = resolved_entry
                break
        except FileNotFoundError as exc:
            raise SkillsServiceError("Local skill not found", status_code=404) from exc
        if skill_dir is None or not skill_dir.is_dir():
            raise SkillsServiceError("Local skill not found", status_code=404)
        if not (skill_dir / "SKILL.md").is_file():
            raise SkillsServiceError("Local skill not found", status_code=404)
        return skill_dir

    @staticmethod
    def resolve_skill_relative_path(
        skill_dir: Path,
        relative_path: str | None,
        *,
        expect_file: bool,
    ) -> Path:
        raw_path = str(relative_path or ".").strip() or "."
        normalized = Path(raw_path.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise SkillsServiceError("Invalid relative path")

        try:
            target = (skill_dir / normalized).resolve(strict=True)
        except FileNotFoundError as exc:
            message = (
                "Skill file not found" if expect_file else "Skill directory not found"
            )
            raise SkillsServiceError(message, status_code=404) from exc
        if not target.is_relative_to(skill_dir):
            raise SkillsServiceError("Path escapes skill directory")
        if expect_file and not target.is_file():
            raise SkillsServiceError("Skill file not found", status_code=404)
        if not expect_file and not target.is_dir():
            raise SkillsServiceError("Skill directory not found", status_code=404)
        return target

    @staticmethod
    def skill_relative_path(skill_dir: Path, target: Path) -> str:
        rel = target.relative_to(skill_dir).as_posix()
        return "" if rel == "." else rel

    @staticmethod
    def is_editable_skill_file(path: Path) -> bool:
        return (
            path.name in _EDITABLE_SKILL_FILENAMES
            or path.suffix.lower() in _EDITABLE_SKILL_FILE_SUFFIXES
        )

    def serialize_skill_file_entry(
        self,
        skill_dir: Path,
        path: Path,
        *,
        readonly: bool = False,
    ) -> dict:
        stat = path.stat()
        is_dir = path.is_dir()
        return {
            "name": path.name,
            "path": self.skill_relative_path(skill_dir, path),
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else stat.st_size,
            "editable": (
                not readonly
                and (not is_dir)
                and self.is_editable_skill_file(path)
                and stat.st_size <= _SKILL_FILE_MAX_BYTES
            ),
        }

    def get_skills(self) -> dict:
        """Return the Skill inventory with runtime plugin activation state."""
        provider_settings = self.config.get("provider_settings", {})
        runtime = provider_settings.get("computer_use_runtime", "none")
        skill_mgr = self.skill_manager
        skills = skill_mgr.list_skills(active_only=False)
        plugin_metadata = {}
        ambiguous_plugin_roots: set[str] = set()
        for metadata in self.plugins.all() if self.plugins is not None else ():
            root_dir_name = metadata.root_dir_name
            if not root_dir_name:
                continue
            if root_dir_name in plugin_metadata:
                ambiguous_plugin_roots.add(root_dir_name)
                continue
            plugin_metadata[root_dir_name] = metadata
        serialized_skills = []
        for skill in skills:
            data = dict(skill.__dict__)
            if skill.source_type == "plugin":
                metadata = (
                    None
                    if skill.plugin_name in ambiguous_plugin_roots
                    else plugin_metadata.get(skill.plugin_name)
                )
                data["plugin_active"] = bool(metadata and metadata.activated)
                data["plugin_display_name"] = (
                    str(metadata.display_name or metadata.name or "").strip()
                    if metadata is not None
                    else ""
                )
            serialized_skills.append(data)

        return {
            "skills": serialized_skills,
            "runtime": runtime,
        }

    async def upload_skill(self, file: UploadFile | None) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        temp_path = None
        if not file:
            raise SkillsServiceError("Missing file")

        filename = os.path.basename(file.filename or "skill.zip")
        if not filename.lower().endswith(".zip"):
            raise SkillsServiceError("Only .zip files are supported")

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        skill_mgr = self.skill_manager
        temp_path = _next_available_temp_path(temp_dir, filename)

        try:
            await save_upload_to_path(file, temp_path, root=temp_dir)
            skill_name = skill_mgr.install_skill_from_zip(
                temp_path,
                overwrite=False,
                skill_name_hint=Path(filename).stem,
            )

            return SkillsOperationResult(
                data={"name": skill_name},
                message="Skill uploaded successfully.",
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    logger.warning("Failed to remove temporary skill file.")

    async def batch_upload_skills(
        self, file_list: Sequence[UploadFile]
    ) -> SkillsOperationResult:
        self._ensure_mutation_allowed()

        if not file_list:
            raise SkillsServiceError("No files provided")

        succeeded = []
        failed = []
        skipped = []
        skill_mgr = self.skill_manager
        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)

        for file in file_list:
            filename = os.path.basename(file.filename or "unknown.zip")
            temp_path = None

            try:
                if not filename.lower().endswith(".zip"):
                    failed.append(
                        {
                            "filename": filename,
                            "error": "Only .zip files are supported",
                        }
                    )
                    continue

                temp_path = _next_available_temp_path(temp_dir, filename)
                await save_upload_to_path(file, temp_path, root=temp_dir)

                try:
                    skill_name = skill_mgr.install_skill_from_zip(
                        temp_path,
                        overwrite=False,
                        skill_name_hint=Path(filename).stem,
                    )
                except FileExistsError:
                    skipped.append(
                        {
                            "filename": filename,
                            "name": Path(filename).stem,
                            "error": "Skill already exists.",
                        }
                    )
                    skill_name = None

                if skill_name is None:
                    continue
                succeeded.append({"filename": filename, "name": skill_name})

            except Exception as exc:
                logger.error("Skill batch upload failed: %s", safe_error("", exc))
                failed.append({"filename": filename, "error": "Skill upload failed"})
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        total = len(file_list)
        success_count = len(succeeded)
        skipped_count = len(skipped)
        failed_count = len(failed)
        data = {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }

        if failed_count == 0 and success_count == total:
            return SkillsOperationResult(
                data=data,
                message=f"All {total} skill(s) uploaded successfully.",
            )
        if failed_count == 0 and success_count == 0:
            return SkillsOperationResult(
                data=data,
                message=f"All {total} file(s) were skipped.",
            )
        if success_count == 0 and skipped_count == 0:
            return SkillsOperationResult(
                ok=False,
                data=data,
                message=f"Upload failed for all {total} file(s).",
            )

        return SkillsOperationResult(
            data=data,
            message=f"Partial success: {success_count}/{total} skill(s) uploaded.",
        )

    def prepare_skill_archive(self, name: str) -> SkillArchive:
        skill_name = self._validate_skill_name(name)

        skill_mgr = self.skill_manager
        if skill_mgr.is_plugin_skill(skill_name):
            raise SkillsServiceError(
                "Plugin-provided skill cannot be downloaded from local skill files."
            )
        if skill_mgr.is_builtin_skill(skill_name):
            raise SkillsServiceError(
                "Builtin preset skill cannot be downloaded from local skill files.",
                status_code=403,
            )

        skill_dir = self.resolve_local_skill_dir(skill_name)
        skills_root = Path(skill_mgr.skills_root).resolve(strict=True)
        try:
            archive_base_dir = skill_dir.relative_to(skills_root).as_posix()
        except ValueError as exc:
            raise SkillsServiceError("Invalid skill path") from exc

        export_dir = Path(get_astrbot_temp_path()) / "skill_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        # ``skill_dir.name`` comes from the validated skills-root listing, not
        # from the request path, so the export path cannot be user-controlled.
        zip_base = export_dir / skill_dir.name
        zip_path = zip_base.with_name(f"{zip_base.name}.zip")

        shutil.make_archive(
            str(zip_base),
            "zip",
            root_dir=str(skills_root),
            base_dir=archive_base_dir,
        )
        return SkillArchive(path=zip_path, filename=f"{skill_name}.zip")

    def list_skill_files(self, name: str, relative_path: str | None = "") -> dict:
        skill_name = self._validate_skill_name(name)
        skill_dir = self.resolve_local_skill_dir(skill_name)
        readonly = self._is_readonly_skill(skill_name)
        target_dir = self.resolve_skill_relative_path(
            skill_dir,
            relative_path,
            expect_file=False,
        )

        entries = []
        for entry in sorted(
            target_dir.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        ):
            try:
                resolved = entry.resolve(strict=True)
            except OSError:
                continue
            if not resolved.is_relative_to(skill_dir):
                continue
            if not resolved.is_dir() and not resolved.is_file():
                continue
            entries.append(
                self.serialize_skill_file_entry(
                    skill_dir,
                    resolved,
                    readonly=readonly,
                )
            )

        return {
            "name": skill_name,
            "path": self.skill_relative_path(skill_dir, target_dir),
            "entries": entries,
        }

    def get_skill_file(self, name: str, relative_path: str | None = "SKILL.md") -> dict:
        skill_name = str(name or "").strip()
        skill_dir = self.resolve_local_skill_dir(skill_name)
        target_file = self.resolve_skill_relative_path(
            skill_dir,
            relative_path,
            expect_file=True,
        )
        if not self.is_editable_skill_file(target_file):
            raise SkillsServiceError("Unsupported file type")

        size = target_file.stat().st_size
        if size > _SKILL_FILE_MAX_BYTES:
            raise SkillsServiceError("File is too large")

        try:
            content = target_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SkillsServiceError("File is not valid UTF-8 text") from exc

        return {
            "name": skill_name,
            "path": self.skill_relative_path(skill_dir, target_file),
            "content": content,
            "size": size,
            "editable": not self._is_readonly_skill(skill_name),
        }

    async def update_skill_file(self, data: object) -> dict:
        self._ensure_mutation_allowed()
        payload = self._payload(data)
        skill_name = str(payload.get("name") or "").strip()
        relative_path = payload.get("path", "SKILL.md")
        content = payload.get("content")
        if not isinstance(content, str):
            raise SkillsServiceError("Missing file content")

        encoded = content.encode("utf-8")
        if len(encoded) > _SKILL_FILE_MAX_BYTES:
            raise SkillsServiceError("File content is too large")

        skill_dir = self.resolve_local_skill_dir(skill_name)
        self._ensure_skill_mutable(skill_name)
        target_file = self.resolve_skill_relative_path(
            skill_dir,
            relative_path,
            expect_file=True,
        )
        if not self.is_editable_skill_file(target_file):
            raise SkillsServiceError("Unsupported file type")

        target_file.write_text(content, encoding="utf-8")

        return {
            "name": skill_name,
            "path": self.skill_relative_path(skill_dir, target_file),
            "size": len(encoded),
        }

    def update_skill(self, data: object) -> dict:
        self._ensure_mutation_allowed()
        payload = self._payload(data)
        active = payload.get("active")
        skill_name = self._validate_skill_name(payload.get("name"))
        if not isinstance(active, bool):
            raise SkillsServiceError("Missing skill active state")
        self._ensure_skill_mutable(skill_name)
        self.skill_manager.set_skill_active(skill_name, active)
        return {"name": skill_name, "active": active}

    async def delete_skill(self, data: object) -> dict:
        self._ensure_mutation_allowed()
        payload = self._payload(data)
        skill_name = self._validate_skill_name(payload.get("name"))
        self._ensure_skill_mutable(skill_name)
        self.skill_manager.delete_skill(skill_name)
        return {"name": skill_name}
