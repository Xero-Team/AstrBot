import os
import re
import shlex
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

SANDBOX_SKILLS_ROOT = "skills"
SANDBOX_WORKSPACE_ROOT = "/workspace"
WORKSPACE_SKILLS_ROOT = "skills"
WORKSPACE_SKILL_FRONTMATTER_MAX_CHARS = 64 * 1024

_SKILL_NAME_RE = re.compile(r"^[\w.-]+$")
_SAFE_PATH_RE = re.compile(r"[^\w./ ,()'\-]", re.UNICODE)
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:(?:/|\\)")
_WINDOWS_UNC_PATH_RE = re.compile(r"^(//|\\\\)[^/\\]+[/\\][^/\\]+")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F-\x9F]")


def _normalize_skill_name(name: str | None) -> str:
    raw = str(name or "")
    return re.sub(r"\s+", "_", raw.strip())


def _default_sandbox_skill_path(name: str) -> str:
    return f"{SANDBOX_WORKSPACE_ROOT}/{SANDBOX_SKILLS_ROOT}/{name}/SKILL.md"


def _normalize_cached_sandbox_skill_path(name: str, path: str) -> str:
    normalized = str(path or "").strip().replace("\\", "/")
    if not normalized:
        return _default_sandbox_skill_path(name)

    pure_path = PurePosixPath(normalized)
    if _is_invalid_cached_sandbox_skill_path(name, pure_path):
        return _default_sandbox_skill_path(name)

    return str(pure_path)


def _is_invalid_cached_sandbox_skill_path(name: str, path: PurePosixPath) -> bool:
    return ".." in path.parts or path.name != "SKILL.md" or path.parent.name != name


def _is_ignored_zip_entry(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if not parts:
        return True
    return parts[0] == "__MACOSX"


def _normalize_skill_markdown_path(skill_dir: Path) -> Path | None:
    """Return the canonical `SKILL.md` path for a skill directory."""
    canonical = skill_dir / "SKILL.md"
    return canonical if canonical.exists() else None


def _get_archive_names(
    zf: zipfile.ZipFile,
) -> tuple[list[str], list[str], bool]:
    """Normalize ZIP entry names and detect root-mode archives."""
    names = _normalize_archive_entry_names(zf.namelist())
    file_names = [name for name in names if not name.endswith("/")]
    if not file_names:
        raise ValueError("Zip archive is empty.")
    return names, file_names, _has_root_skill_markdown(file_names)


def _normalize_archive_entry_names(names: list[str]) -> list[str]:
    return [
        name
        for name in (entry.replace("\\", "/") for entry in names)
        if name and not _is_ignored_zip_entry(name)
    ]


def _has_root_skill_markdown(file_names: list[str]) -> bool:
    return any(
        len(parts := PurePosixPath(name).parts) == 1 and parts[0] == "SKILL.md"
        for name in file_names
    )


def _normalize_archive_skill_name(skill_name_hint: str | None) -> str | None:
    """Validate and normalize an optional skill name override."""
    if skill_name_hint is None:
        return None

    archive_skill_name = _normalize_skill_name(skill_name_hint)
    if archive_skill_name and not _SKILL_NAME_RE.fullmatch(archive_skill_name):
        raise ValueError("Invalid skill name.")
    return archive_skill_name


def _validate_archive_paths(names: list[str]) -> None:
    """Reject ZIP entries with unsafe paths."""
    for name in names:
        if _CONTROL_CHARS_RE.search(name):
            raise ValueError("Zip archive contains control characters in paths.")
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise ValueError("Zip archive contains absolute paths.")
        parts = PurePosixPath(name).parts
        if ".." in parts:
            raise ValueError("Zip archive contains invalid relative paths.")


def _get_archive_top_dirs(file_names: list[str]) -> set[str]:
    """Return top-level directories referenced by ZIP file entries."""
    return {PurePosixPath(name).parts[0] for name in file_names if name.strip()}


@dataclass
class SkillInfo:
    name: str
    description: str
    path: str
    active: bool
    source_type: str = "local_only"
    source_label: str = "local"
    local_exists: bool = True
    sandbox_exists: bool = False
    plugin_name: str = ""
    readonly: bool = False


def _parse_frontmatter_description(text: str) -> str:
    """Extract the ``description`` value from YAML frontmatter."""
    frontmatter = _extract_frontmatter_block(text)
    if frontmatter is None:
        return ""
    try:
        payload = _load_frontmatter_payload(frontmatter)
    except yaml.YAMLError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return _extract_frontmatter_description_value(payload)


def _extract_frontmatter_block(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_index = _find_frontmatter_end_index(lines)
    if end_index is None:
        return None
    return "\n".join(lines[1:end_index])


def _find_frontmatter_end_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return index
    return None


def _load_frontmatter_payload(frontmatter: str) -> object:
    return yaml.safe_load(frontmatter) or {}


def _extract_frontmatter_description_value(payload: dict[object, object]) -> str:
    description = payload.get("description", "")
    if not isinstance(description, str):
        return ""
    return description.strip()


def _read_skill_description(skill_md: Path) -> str:
    try:
        return _parse_frontmatter_description(skill_md.read_text(encoding="utf-8"))
    except Exception:
        return ""


def _is_windows_prompt_path(path: str) -> bool:
    if os.name != "nt":
        return False
    return bool(_WINDOWS_DRIVE_PATH_RE.match(path) or _WINDOWS_UNC_PATH_RE.match(path))


def _sanitize_prompt_path_for_prompt(path: str) -> str:
    if not path:
        return ""

    if _WINDOWS_DRIVE_PATH_RE.match(path) or _WINDOWS_UNC_PATH_RE.match(path):
        path = path.replace("\\", "/")

    drive_prefix = ""
    if _WINDOWS_DRIVE_PATH_RE.match(path):
        drive_prefix = path[:2]
        path = path[2:]

    path = path.replace("`", "")
    path = _CONTROL_CHARS_RE.sub("", path)
    sanitized = _SAFE_PATH_RE.sub("", path)
    return f"{drive_prefix}{sanitized}"


def _sanitize_prompt_description(description: str) -> str:
    description = description.replace("`", "")
    description = _CONTROL_CHARS_RE.sub(" ", description)
    description = " ".join(description.split())
    return description


def _sanitize_skill_display_name(name: str) -> str:
    if _SKILL_NAME_RE.fullmatch(name):
        return name
    return "<invalid_skill_name>"


def _build_skill_read_command_example(path: str) -> str:
    if path == "<skills_root>/<skill_name>/SKILL.md":
        return f"cat {path}"
    if _is_windows_prompt_path(path):
        command = "type"
        normalized_path = path.replace("\\", "/")
        path_arg = f'"{normalized_path}"'
    else:
        command = "cat"
        path_arg = shlex.quote(path)
    return f"{command} {path_arg}"


def build_skills_prompt(skills: list[SkillInfo]) -> str:
    """Build the skills section of the system prompt."""
    skills_lines: list[str] = []
    example_path = ""
    for skill in skills:
        display_name = _sanitize_skill_display_name(skill.name)
        description = _render_skill_prompt_description(skill)
        rendered_path = _render_skill_prompt_path(skill)
        skills_lines.append(
            f"- **{display_name}**: {description}\n  File: `{rendered_path}`"
        )
        if not example_path:
            example_path = rendered_path
    skills_block = "\n".join(skills_lines)
    example_command = _build_skill_read_command_example(
        _normalize_prompt_example_path(example_path)
    )

    return (
        "## Skills\n\n"
        "You have specialized skills — reusable instruction bundles stored "
        "in `SKILL.md` files. Each skill has a **name** and a **description** "
        "that tells you what it does and when to use it.\n\n"
        "### Available skills\n\n"
        f"{skills_block}\n\n"
        "### Skill rules\n\n"
        "1. **Discovery** — The list above is the complete skill inventory "
        "for this session. Full instructions are in the referenced "
        "`SKILL.md` file.\n"
        "2. **When to trigger** — Use a skill if the user names it "
        "explicitly, or if the task clearly matches the skill's description. "
        "*Never silently skip a matching skill* — either use it or briefly "
        "explain why you chose not to.\n"
        "3. **Mandatory grounding** — Before executing any skill you MUST "
        "first read its `SKILL.md` by running a shell command compatible "
        "with the current runtime shell and using the **absolute path** "
        f"shown above (e.g. `{example_command}`). "
        "Never rely on memory or assumptions about a skill's content.\n"
        "4. **Progressive disclosure** — Load only what is directly "
        "referenced from `SKILL.md`:\n"
        "   - If `scripts/` exist, prefer running or patching them over "
        "rewriting code from scratch.\n"
        "   - If `assets/` or templates exist, reuse them.\n"
        "   - Do NOT bulk-load every file in the skill directory.\n"
        "5. **Coordination** — When multiple skills apply, pick the minimal "
        "set needed. Announce which skill(s) you are using and why "
        "(one short line). Prefer `astrbot_*` tools when running skill "
        "scripts.\n"
        "6. **Context hygiene** — Avoid deep reference chasing; open only "
        "files that are directly linked from `SKILL.md`.\n"
        "7. **Failure handling** — If a skill cannot be applied, state the "
        "issue clearly and continue with the best alternative.\n"
    )


def _render_skill_prompt_description(skill: SkillInfo) -> str:
    description = skill.description or "No description"
    if skill.source_type not in {"sandbox_only", "workspace"}:
        return description
    sanitized = _sanitize_prompt_description(description)
    return sanitized or "Read SKILL.md for details."


def _render_skill_prompt_path(skill: SkillInfo) -> str:
    rendered_path = _sanitize_prompt_path_for_prompt(skill.path)
    if rendered_path:
        return rendered_path
    if skill.source_type == "sandbox_only":
        return _default_sandbox_skill_path(skill.name)
    return "<skills_root>/<skill_name>/SKILL.md"


def _normalize_prompt_example_path(example_path: str) -> str:
    if example_path == "<skills_root>/<skill_name>/SKILL.md":
        return example_path
    sanitized = _sanitize_prompt_path_for_prompt(example_path)
    return sanitized or "<skills_root>/<skill_name>/SKILL.md"


def _normalize_archive_skill_dir_name(dir_name: str) -> str | None:
    if dir_name in {".", "..", ""}:
        return None
    normalized_name = _normalize_skill_name(dir_name)
    if not _SKILL_NAME_RE.fullmatch(normalized_name):
        return None
    return normalized_name
