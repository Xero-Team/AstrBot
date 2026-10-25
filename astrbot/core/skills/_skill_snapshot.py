from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from astrbot.core.skills._skill_frontmatter import (
    SkillFrontmatter,
    parse_skill_frontmatter,
)
from astrbot.core.skills._skill_fs import (
    MAX_SKILL_SNAPSHOT_BYTES,
    MAX_SKILL_SNAPSHOT_FILES,
    TRUNCATION_NOTE,
    list_regular_skill_files,
    read_nofollow_capped,
)
from astrbot.core.skills._skill_inventory import SkillInfo

SKILL_SNAPSHOT_EXTRA_KEY = "skill_snapshot"
PROMPT_TOOLS_EXTRA_KEY = "prompt_tools"


@dataclass(frozen=True, slots=True)
class FrozenSkill:
    name: str
    source_type: str
    source_label: str
    resolved_root: str
    runtime_copy: str
    identity: str
    description: str
    declared_tools: tuple[str, ...]
    plugin_name: str = ""
    skill_markdown: str | None = None
    file_bodies: tuple[tuple[str, str], ...] = ()

    def file_body(self, relative_path: str) -> str | None:
        if relative_path == "SKILL.md" and self.skill_markdown is not None:
            return self.skill_markdown
        for path, body in self.file_bodies:
            if path == relative_path:
                return body
        return None


@dataclass(frozen=True, slots=True)
class SkillSnapshot:
    skills: tuple[FrozenSkill, ...]
    runtime: str

    def get(self, name: str) -> FrozenSkill | None:
        for skill in self.skills:
            if skill.name == name:
                return skill
        return None

    def declared_tool_names(self) -> tuple[str, ...]:
        seen: set[str] = set()
        names: list[str] = []
        for skill in self.skills:
            for tool_name in skill.declared_tools:
                if tool_name in seen:
                    continue
                seen.add(tool_name)
                names.append(tool_name)
        return tuple(names)


def freeze_skill_snapshot(
    skills: Sequence[SkillInfo],
    *,
    runtime: str,
) -> SkillSnapshot:
    """Freeze the enabled Skill set for one request.

    Same-name precedence must already be resolved by the caller. The snapshot
    keeps only the winning source for each name.
    """
    frozen: list[FrozenSkill] = []
    seen: set[str] = set()
    for skill in skills:
        if skill.name in seen:
            continue
        seen.add(skill.name)
        frozen_skill = _freeze_host_skill(skill)
        if frozen_skill is not None:
            frozen.append(frozen_skill)
    return SkillSnapshot(skills=tuple(frozen), runtime=runtime)


def _freeze_host_skill(skill: SkillInfo) -> FrozenSkill | None:
    skill_md = Path(skill.host_path or skill.path)
    if skill_md.name != "SKILL.md":
        skill_md = skill_md / "SKILL.md"
    try:
        resolved_root = skill_md.parent.resolve()
    except OSError:
        return None
    if not resolved_root.is_dir() or resolved_root.is_symlink():
        return None
    bodies = _freeze_host_skill_files(resolved_root)
    text = dict(bodies).get("SKILL.md", "")
    digest = _digest(text.encode("utf-8"))
    frontmatter = (
        parse_skill_frontmatter(text)
        if text
        else SkillFrontmatter(
            name="",
            description=skill.description,
            tools=skill.declared_tools,
            warnings=(),
        )
    )
    description = frontmatter.description or skill.description
    declared_tools = frontmatter.tools or skill.declared_tools
    return FrozenSkill(
        name=skill.name,
        source_type=skill.source_type,
        source_label=skill.source_label,
        resolved_root=str(resolved_root),
        runtime_copy=str(skill_md),
        identity=digest,
        description=description,
        declared_tools=tuple(declared_tools),
        plugin_name=skill.plugin_name,
        skill_markdown=text or None,
        file_bodies=bodies,
    )


def _freeze_host_skill_files(root: Path) -> tuple[tuple[str, str], ...]:
    bodies: list[tuple[str, str]] = []
    total_bytes = 0
    for relative in list_regular_skill_files(root):
        if len(bodies) >= MAX_SKILL_SNAPSHOT_FILES:
            break
        try:
            text = read_nofollow_capped(root, relative)
        except OSError:
            continue
        encoded = text.encode("utf-8")
        if total_bytes + len(encoded) > MAX_SKILL_SNAPSHOT_BYTES and bodies:
            break
        bodies.append((relative, text))
        total_bytes += min(len(encoded), MAX_SKILL_SNAPSHOT_BYTES)
        if text.endswith(TRUNCATION_NOTE) and relative == "SKILL.md":
            continue
    return tuple(bodies)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
