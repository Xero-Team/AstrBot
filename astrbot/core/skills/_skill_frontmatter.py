from dataclasses import dataclass

import yaml

from astrbot.core.skills._skill_inventory import (
    _extract_frontmatter_block,
    _load_frontmatter_payload,
)

MAX_SKILL_TOOL_NAME_LENGTH = 128
MAX_SKILL_TOOL_COUNT = 64


@dataclass(frozen=True, slots=True)
class SkillFrontmatter:
    name: str
    description: str
    tools: tuple[str, ...]
    warnings: tuple[str, ...]


def parse_skill_frontmatter(text: str) -> SkillFrontmatter:
    """Parse SKILL.md YAML frontmatter once into structured metadata."""
    frontmatter = _extract_frontmatter_block(text)
    if frontmatter is None:
        return SkillFrontmatter(name="", description="", tools=(), warnings=())
    try:
        payload = _load_frontmatter_payload(frontmatter)
    except yaml.YAMLError:
        return SkillFrontmatter(
            name="",
            description="",
            tools=(),
            warnings=("invalid_yaml",),
        )
    if not isinstance(payload, dict):
        return SkillFrontmatter(
            name="",
            description="",
            tools=(),
            warnings=("invalid_payload",),
        )
    return SkillFrontmatter(
        name=_extract_frontmatter_name(payload),
        description=_extract_frontmatter_description_value(payload),
        tools=_extract_frontmatter_tools(payload),
        warnings=_extract_frontmatter_warnings(payload),
    )


def _extract_frontmatter_name(payload: dict[object, object]) -> str:
    name = payload.get("name", "")
    if not isinstance(name, str):
        return ""
    return name.strip()


def _extract_frontmatter_description_value(payload: dict[object, object]) -> str:
    description = payload.get("description", "")
    if not isinstance(description, str):
        return ""
    return description.strip()


def _extract_frontmatter_tools(payload: dict[object, object]) -> tuple[str, ...]:
    raw_tools = payload.get("tools")
    if raw_tools is None:
        return ()
    if not isinstance(raw_tools, list):
        return ()
    seen: set[str] = set()
    tools: list[str] = []
    for item in raw_tools:
        if len(tools) >= MAX_SKILL_TOOL_COUNT:
            break
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or len(name) > MAX_SKILL_TOOL_NAME_LENGTH:
            continue
        if name in seen:
            continue
        seen.add(name)
        tools.append(name)
    return tuple(tools)


def _extract_frontmatter_warnings(payload: dict[object, object]) -> tuple[str, ...]:
    warnings: list[str] = []
    if "tools" in payload and not isinstance(payload.get("tools"), list | type(None)):
        warnings.append("tools_not_a_list")
    if "allowed-tools" in payload or "allowed_tools" in payload:
        warnings.append("ignored_allowed_tools")
    return tuple(warnings)
