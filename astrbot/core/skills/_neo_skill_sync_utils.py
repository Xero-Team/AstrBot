from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

MAP_VERSION = 1
MAP_FILE_NAME = "neo_skill_map.json"
SKILL_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def to_jsonable(model_like: Any) -> dict[str, Any]:
    if isinstance(model_like, dict):
        return model_like
    if hasattr(model_like, "model_dump"):
        dumped = model_like.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    frontmatter_lines, body = split_frontmatter_lines(text)
    if frontmatter_lines is None:
        return {}, text
    data: dict[str, str] = {}
    for line in frontmatter_lines:
        parsed_field = parse_frontmatter_field(line)
        if parsed_field is None or not is_supported_frontmatter_field(parsed_field):
            continue
        key, value = parsed_field
        data[key] = value
    return data, body


def split_frontmatter_lines(text: str) -> tuple[list[str] | None, str]:
    if not has_frontmatter_header(text):
        return None, text
    lines = text.splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return lines[1:index], body
    return None, text


def has_frontmatter_header(text: str) -> bool:
    if not text.startswith("---"):
        return False
    lines = text.splitlines()
    return bool(lines and lines[0].strip() == "---")


def parse_frontmatter_field(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    key, value = line.split(":", 1)
    return key.strip().lower(), value.strip().strip('"').strip("'")


def is_supported_frontmatter_field(parsed_field: tuple[str, str] | None) -> bool:
    return (
        parsed_field is not None
        and parsed_field[0] in {"name", "description"}
        and bool(parsed_field[1])
    )


def derive_description(markdown_body: str) -> str:
    lines = markdown_body.splitlines()
    heading_idx = find_description_heading_index(lines)
    if heading_idx is not None:
        return first_description_line(lines[heading_idx + 1 :], stop_at_heading=True)
    return first_description_line(lines, stop_at_heading=False)


def find_description_heading_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.strip().lower() in {"## 描述", "## description"}:
            return index
    return None


def first_description_line(lines: list[str], *, stop_at_heading: bool) -> str:
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            if stop_at_heading:
                return ""
            continue
        return text
    return ""


def ensure_skill_frontmatter(markdown: str, *, skill_name: str, skill_key: str) -> str:
    frontmatter, body = parse_frontmatter(markdown)

    name = frontmatter.get("name") or skill_name
    name = " ".join(str(name).split())
    description = frontmatter.get("description") or derive_description(body)
    if not description:
        description = f"Synced skill for `{skill_key}`."

    description = " ".join(description.split())

    header = f"---\nname: {name}\ndescription: {description}\n---\n\n"
    body = body.strip("\n")
    return f"{header}{body}\n"


@dataclass
class NeoSkillSyncResult:
    skill_key: str
    local_skill_name: str
    release_id: str
    candidate_id: str
    payload_ref: str
    map_path: str
    synced_at: str
