from pathlib import Path

from astrbot import logger
from astrbot.core.skills._skill_inventory import (
    SkillInfo,
    _normalize_skill_markdown_path,
    _read_skill_frontmatter,
)


class SkillManagerListingMixin:
    skills_root: str

    def _load_config(self) -> dict: ...
    def _save_config(self, config: dict) -> None: ...
    def _get_plugin_skill_dir(self, name: str) -> Path | None: ...
    def _iter_plugin_skill_dirs(self) -> list[tuple[str, str, Path]]: ...
    def _get_builtin_skill_dir(self, name: str) -> Path | None: ...
    def _iter_builtin_skill_dirs(self) -> list[tuple[str, str, Path]]: ...

    def _ensure_skill_config(
        self, skill_configs: dict[str, dict], skill_name: str
    ) -> tuple[bool, bool]:
        active = skill_configs.get(skill_name, {}).get("active", True)
        if skill_name in skill_configs:
            return active, False
        skill_configs[skill_name] = {"active": active}
        return active, True

    def _build_listed_skill_info(
        self,
        *,
        skill_name: str,
        description: str,
        active: bool,
        source_type: str,
        source_label: str,
        skill_md: Path,
        plugin_name: str = "",
        readonly: bool = False,
    ) -> SkillInfo:
        declared_tools = ()
        frontmatter = _read_skill_frontmatter(skill_md)
        description = frontmatter.description or description
        declared_tools = frontmatter.tools
        return SkillInfo(
            name=skill_name,
            description=description,
            path=str(skill_md).replace("\\", "/"),
            active=active,
            source_type=source_type,
            source_label=source_label,
            plugin_name=plugin_name,
            readonly=readonly,
            declared_tools=declared_tools,
            host_path=str(skill_md).replace("\\", "/"),
        )

    def _add_markdown_backed_skill(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        skill_configs: dict[str, dict],
        skill_name: str,
        skill_md: Path,
        active_only: bool,
        source_type: str,
        source_label: str,
        plugin_name: str = "",
        readonly: bool = False,
    ) -> bool:
        active, added = self._ensure_skill_config(skill_configs, skill_name)
        if active_only and not active:
            return added

        skills_by_name[skill_name] = self._build_listed_skill_info(
            skill_name=skill_name,
            description="",
            active=active,
            source_type=source_type,
            source_label=source_label,
            skill_md=skill_md,
            plugin_name=plugin_name,
            readonly=readonly,
        )
        return added

    def _add_local_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        skill_configs: dict[str, dict],
        active_only: bool,
    ) -> bool:
        modified = False
        try:
            local_entries = sorted(Path(self.skills_root).iterdir())
        except OSError as exc:
            # An unreadable skills root must not kill the whole agent request;
            # mirror list_workspace_skills and continue with other sources.
            logger.warning(
                f"Skill root {self.skills_root} is not readable, "
                f"skipping local skills: {exc}"
            )
            local_entries = []
        for entry in local_entries:
            try:
                if not entry.is_dir():
                    continue
                skill_name = entry.name
                skill_md = _normalize_skill_markdown_path(entry)
                if skill_md is None:
                    continue
            except OSError as exc:
                logger.warning(f"Skip unreadable skill directory {entry}: {exc}")
                continue
            modified = (
                self._add_markdown_backed_skill(
                    skills_by_name=skills_by_name,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    skill_md=skill_md,
                    active_only=active_only,
                    source_type="local_only",
                    source_label="local",
                )
                or modified
            )
        return modified

    def _add_plugin_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        skill_configs: dict[str, dict],
        active_only: bool,
    ) -> bool:
        modified = False
        for skill_name, plugin_name, skill_dir in self._iter_plugin_skill_dirs():
            if skill_name in skills_by_name:
                continue
            try:
                skill_md = _normalize_skill_markdown_path(skill_dir)
            except OSError as exc:
                logger.warning(
                    f"Skip unreadable plugin skill directory {skill_dir}: {exc}"
                )
                continue
            if skill_md is None:
                continue
            modified = (
                self._add_markdown_backed_skill(
                    skills_by_name=skills_by_name,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    skill_md=skill_md,
                    active_only=active_only,
                    source_type="plugin",
                    source_label=plugin_name,
                    plugin_name=plugin_name,
                    readonly=True,
                )
                or modified
            )
        return modified

    def _add_builtin_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        skill_configs: dict[str, dict],
        active_only: bool,
    ) -> bool:
        modified = False
        for skill_name, source_label, skill_dir in self._iter_builtin_skill_dirs():
            if skill_name in skills_by_name:
                continue
            try:
                skill_md = _normalize_skill_markdown_path(skill_dir)
            except OSError as exc:
                logger.warning(
                    f"Skip unreadable builtin skill directory {skill_dir}: {exc}"
                )
                continue
            if skill_md is None:
                continue
            modified = (
                self._add_markdown_backed_skill(
                    skills_by_name=skills_by_name,
                    skill_configs=skill_configs,
                    skill_name=skill_name,
                    skill_md=skill_md,
                    active_only=active_only,
                    source_type="builtin_preset",
                    source_label=source_label,
                    readonly=True,
                )
                or modified
            )
        return modified

    def list_skills(self, *, active_only: bool = False) -> list[SkillInfo]:
        """List all skills."""
        config = self._load_config()
        skill_configs = config.get("skills", {})
        skills_by_name: dict[str, SkillInfo] = {}

        modified = self._populate_listed_skills(
            skills_by_name=skills_by_name,
            skill_configs=skill_configs,
            active_only=active_only,
        )
        self._save_skill_config_if_modified(
            config=config,
            skill_configs=skill_configs,
            modified=modified,
        )
        return [skills_by_name[name] for name in sorted(skills_by_name)]

    def _populate_listed_skills(
        self,
        *,
        skills_by_name: dict[str, SkillInfo],
        skill_configs: dict[str, dict],
        active_only: bool,
    ) -> bool:
        modified = False
        for adder in (
            self._add_local_listed_skills,
            self._add_plugin_listed_skills,
            self._add_builtin_listed_skills,
        ):
            modified = (
                adder(
                    skills_by_name=skills_by_name,
                    skill_configs=skill_configs,
                    active_only=active_only,
                )
                or modified
            )
        return modified

    def _save_skill_config_if_modified(
        self,
        *,
        config: dict,
        skill_configs: dict[str, dict],
        modified: bool,
    ) -> None:
        if not modified:
            return
        config["skills"] = skill_configs
        self._save_config(config)

    def is_plugin_skill(self, name: str) -> bool:
        skill_dir = Path(self.skills_root) / name
        if _normalize_skill_markdown_path(skill_dir) is not None:
            return False
        return self._get_plugin_skill_dir(name) is not None

    def is_builtin_skill(self, name: str) -> bool:
        skill_dir = Path(self.skills_root) / name
        if _normalize_skill_markdown_path(skill_dir) is not None:
            return False
        if self._get_plugin_skill_dir(name) is not None:
            return False
        return self._get_builtin_skill_dir(name) is not None

    def set_skill_active(self, name: str, active: bool) -> None:
        if self.is_plugin_skill(name):
            raise PermissionError(
                "Plugin-provided skill cannot be enabled/disabled from local skill management."
            )
        if self.is_builtin_skill(name):
            raise PermissionError(
                "Builtin preset skill cannot be enabled/disabled from local skill management."
            )
        config = self._load_config()
        config.setdefault("skills", {})
        config["skills"][name] = {"active": bool(active)}
        self._save_config(config)
