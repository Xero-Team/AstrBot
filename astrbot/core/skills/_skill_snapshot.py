from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from astrbot.core.skills._skill_frontmatter import (
    SkillFrontmatter,
    parse_skill_frontmatter,
)
from astrbot.core.skills._skill_inventory import (
    SANDBOX_WORKSPACE_ROOT,
    SkillInfo,
    _default_sandbox_skill_path,
    _normalize_cached_sandbox_skill_path,
)

SKILL_SNAPSHOT_EXTRA_KEY = "skill_snapshot"
PERSONA_TOOLS_EXTRA_KEY = "persona_tools"


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
    host_readable: bool = True
    skill_markdown: str | None = None


@dataclass(frozen=True, slots=True)
class SkillSnapshot:
    skills: tuple[FrozenSkill, ...]
    runtime: str
    sandbox_root: str = SANDBOX_WORKSPACE_ROOT

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
    sandbox_root: str = SANDBOX_WORKSPACE_ROOT,
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
        frozen_skill = _freeze_one_skill(
            skill,
            runtime=runtime,
            sandbox_root=sandbox_root,
        )
        if frozen_skill is not None:
            frozen.append(frozen_skill)
    return SkillSnapshot(
        skills=tuple(frozen),
        runtime=runtime,
        sandbox_root=sandbox_root,
    )


def _freeze_one_skill(
    skill: SkillInfo,
    *,
    runtime: str,
    sandbox_root: str,
) -> FrozenSkill | None:
    if _uses_sandbox_copy(skill, runtime):
        return _freeze_sandbox_skill(skill, sandbox_root=sandbox_root)
    return _freeze_host_skill(skill)


def _uses_sandbox_copy(skill: SkillInfo, runtime: str) -> bool:
    if runtime != "sandbox":
        return False
    return skill.source_type in {"sandbox_only", "both"} or skill.sandbox_exists


def _freeze_sandbox_skill(
    skill: SkillInfo,
    *,
    sandbox_root: str,
) -> FrozenSkill | None:
    runtime_copy = _validated_sandbox_skill_path(
        skill.name,
        skill.path,
        sandbox_root=sandbox_root,
    )
    if runtime_copy is None:
        return None
    root = str(PurePosixPath(runtime_copy).parent)
    frontmatter = _host_frontmatter_if_available(skill)
    declared_tools = (
        frontmatter.tools if frontmatter is not None else skill.declared_tools
    )
    description = (
        frontmatter.description
        if frontmatter is not None and frontmatter.description
        else skill.description
    )
    identity = _sandbox_identity(skill, runtime_copy, declared_tools)
    return FrozenSkill(
        name=skill.name,
        source_type=skill.source_type,
        source_label=skill.source_label,
        resolved_root=root,
        runtime_copy=runtime_copy,
        identity=identity,
        description=description,
        declared_tools=tuple(declared_tools),
        plugin_name=skill.plugin_name,
        host_readable=False,
        skill_markdown=None,
    )


def _freeze_host_skill(skill: SkillInfo) -> FrozenSkill | None:
    skill_md = Path(skill.host_path or skill.path)
    if skill_md.name != "SKILL.md":
        skill_md = skill_md / "SKILL.md"
    try:
        resolved_root = skill_md.parent.resolve()
    except OSError:
        return None
    if not resolved_root.is_dir():
        return None
    text, digest = _read_host_skill_markdown(skill_md)
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
        host_readable=True,
        skill_markdown=text or None,
    )


def _host_frontmatter_if_available(skill: SkillInfo) -> SkillFrontmatter | None:
    if not skill.local_exists:
        return None
    path = Path(skill.host_path or skill.path)
    if path.name != "SKILL.md":
        return None
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_skill_frontmatter(text)


def _read_host_skill_markdown(path: Path) -> tuple[str, str]:
    try:
        data = path.read_bytes()
    except OSError:
        return "", _digest(b"")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    return text, _digest(data)


def _sandbox_identity(
    skill: SkillInfo,
    runtime_copy: str,
    declared_tools: Iterable[str],
) -> str:
    payload = "\n".join(
        (
            skill.name,
            skill.source_type,
            runtime_copy,
            skill.description,
            ",".join(declared_tools),
        )
    )
    return _digest(payload.encode("utf-8"))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validated_sandbox_skill_path(
    name: str,
    path: str,
    *,
    sandbox_root: str,
) -> str | None:
    normalized = _normalize_cached_sandbox_skill_path(name, path)
    if not _sandbox_path_under_root(normalized, sandbox_root):
        fallback = _default_sandbox_skill_path(name)
        if not _sandbox_path_under_root(fallback, sandbox_root):
            return None
        return fallback
    return normalized


def _sandbox_path_under_root(path: str, sandbox_root: str) -> bool:
    pure = PurePosixPath(path)
    root = PurePosixPath(sandbox_root)
    if ".." in pure.parts or ".." in root.parts:
        return False
    try:
        pure.relative_to(root)
    except ValueError:
        return False
    return True
