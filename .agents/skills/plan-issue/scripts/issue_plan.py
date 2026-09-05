#!/usr/bin/env python3
"""Create and validate issue-plan workspaces for this checkout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
FORK_REPO = "Xero-Team/AstrBot"
UPSTREAM_HOST = "github.com/AstrBotDevs/AstrBot"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ISSUE_ID_RE = re.compile(r"^issue-\d+$")
LOCAL_ID_RE = re.compile(r"^local-[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_HEADINGS = (
    "Goal",
    "Architecture",
    "Constraints",
    "Current behavior",
    "Desired behavior",
    "Out of scope",
    "Tasks",
    "Verification",
)
RESEARCH_HEADINGS = (
    "Request",
    "Coverage ledger",
    "Current behavior",
    "Redundancy",
    "Prior rejection",
    "Owners and tests",
    "Docs",
    "Impact surface",
    "Hypotheses",
    "Open questions",
)
PLACEHOLDER_RE = re.compile(
    r"\bTBD\b|\bTODO\b|implement later|add appropriate|"
    r"similar to Task|fill in details|add tests for the above",
    re.IGNORECASE,
)
FORBIDDEN_RE = re.compile(
    r"https://docs\.astrbot\.app|soulter/astrbot|"
    r">=3\.1[0-3]\b",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
TASK_HEADING_RE = re.compile(r"^###\s+Task\b", re.IGNORECASE)
FILES_RE = re.compile(r"^\*{0,2}Files:\*{0,2}\s*$", re.IGNORECASE)
VERIFY_RE = re.compile(r"^\*{0,2}Verify:\*{0,2}\s*$", re.IGNORECASE)
COMMAND_RE = re.compile(
    r"```(?:bash|sh|zsh)?\s*$|^\s*(?:uv |make |pnpm |python |\./|cd )",
    re.IGNORECASE | re.MULTILINE,
)
ALIGN_FILES = ("RESEARCH.md", "BRIEF.md", "QUIZ.md", "REFLECT.md")
QUESTION_HEADING_RE = re.compile(r"^###\s+Question\b", re.IGNORECASE)
TOTAL_RE = re.compile(
    r"^\*{0,2}Total:\*{0,2}\s*(\d+)\s*/\s*10\s*$",
    re.IGNORECASE | re.MULTILINE,
)
VERDICT_RE = re.compile(
    r"^\*{0,2}Verdict:\*{0,2}\s*(pass|fail|override)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
STATUS_FILES = (
    "ISSUE.md",
    "RESEARCH.md",
    "BRIEF.md",
    "QUIZ.md",
    "REFLECT.md",
    "QUESTIONS.md",
    "PLAN.md",
)


class PlanError(RuntimeError):
    """User-facing validation or workspace error."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file():
            return parent
    raise PlanError("could not locate the AstrBot checkout root")


def run_git(root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git command failed"
        raise PlanError(detail) from exc


def default_runs_root(root: Path) -> Path:
    return root / ".tmp" / "issue-plan"


def latest_pointer(runs_root: Path) -> Path:
    return runs_root / "LATEST"


def run_id_for(*, issue: int | None, slug: str | None) -> str:
    if issue is not None and slug:
        raise PlanError("pass either --issue or --slug, not both")
    if issue is not None:
        if issue < 1:
            raise PlanError("issue number must be >= 1")
        return f"issue-{issue}"
    if slug:
        if not SLUG_RE.fullmatch(slug):
            raise PlanError("slug must be lowercase kebab-case")
        return f"local-{slug}"
    raise PlanError("pass --issue or --slug")


def validate_run_id(run_id: str) -> None:
    if not (ISSUE_ID_RE.fullmatch(run_id) or LOCAL_ID_RE.fullmatch(run_id)):
        raise PlanError(f"invalid run id: {run_id}")


def split_sections(markdown: str) -> list[tuple[int, str, str]]:
    lines = markdown.splitlines()
    starts: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match is None:
            continue
        starts.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[tuple[int, str, str]] = []
    for index, (start, level, title) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start + 1 : end])
        sections.append((level, title, body))
    return sections


def heading_titles(sections: list[tuple[int, str, str]], level: int) -> set[str]:
    return {title for sec_level, title, _body in sections if sec_level == level}


def validate_plan(markdown: str) -> list[str]:
    """Return mechanical errors for a PLAN.md body."""
    errors: list[str] = []
    text = markdown.strip()
    if not text:
        return ["PLAN.md is empty"]
    if not text.startswith("# "):
        errors.append("PLAN.md must start with a level-1 title")
    sections = split_sections(markdown)
    titles = heading_titles(sections, 2)
    for heading in REQUIRED_HEADINGS:
        if heading not in titles:
            errors.append(f"missing heading: {heading}")
    tasks = [
        (title, body)
        for level, title, body in sections
        if level == 3 and TASK_HEADING_RE.match(f"### {title}")
    ]
    if not tasks:
        errors.append("missing ### Task section")
    for title, body in tasks:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not any(FILES_RE.match(line) for line in lines):
            errors.append(f"{title}: missing Files")
        if not any(VERIFY_RE.match(line) for line in lines):
            errors.append(f"{title}: missing Verify")
        elif not COMMAND_RE.search(body):
            errors.append(f"{title}: Verify has no command")
    if PLACEHOLDER_RE.search(markdown):
        errors.append("placeholder text is not allowed")
    forbidden = FORBIDDEN_RE.search(markdown)
    if forbidden:
        errors.append(f"forbidden artifact: {forbidden.group(0)}")
    return errors


def validate_research(markdown: str) -> list[str]:
    """Return mechanical errors for a RESEARCH.md body."""
    errors: list[str] = []
    text = markdown.strip()
    if not text:
        return ["RESEARCH.md is empty"]
    titles = heading_titles(split_sections(markdown), 2)
    for heading in RESEARCH_HEADINGS:
        if heading not in titles:
            errors.append(f"RESEARCH.md missing heading: {heading}")
    return errors


def validate_quiz(markdown: str) -> list[str]:
    """Return mechanical errors for a QUIZ.md body."""
    errors: list[str] = []
    questions = [
        line for line in markdown.splitlines() if QUESTION_HEADING_RE.match(line)
    ]
    if len(questions) < 5:
        errors.append(
            f"QUIZ.md needs five ### Question sections, found {len(questions)}"
        )
    total = TOTAL_RE.search(markdown)
    if total is None:
        errors.append("QUIZ.md missing **Total:** n/10")
    elif int(total.group(1)) > 10:
        errors.append("QUIZ.md total exceeds 10")
    if VERDICT_RE.search(markdown) is None:
        errors.append("QUIZ.md missing **Verdict:** pass|fail|override")
    return errors


def resolve_run_dir(root: Path, explicit: str | None) -> Path:
    runs_root = default_runs_root(root)
    if explicit:
        target = Path(explicit)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()
        if not (target / "manifest.json").is_file():
            raise PlanError(f"missing manifest in {target}")
        return target
    pointer = latest_pointer(runs_root)
    if pointer.is_file():
        named = pointer.read_text(encoding="utf-8").strip()
        candidate = runs_root / named
        if (candidate / "manifest.json").is_file():
            return candidate
    if not runs_root.is_dir():
        raise PlanError("no issue-plan run exists; run init first")
    candidates = sorted(
        (path for path in runs_root.iterdir() if (path / "manifest.json").is_file()),
        key=lambda path: path.name,
    )
    if not candidates:
        raise PlanError("no issue-plan run exists; run init first")
    return candidates[-1]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise PlanError(f"missing {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PlanError("unsupported schema_version")
    return payload


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root()
    run_id = run_id_for(issue=args.issue, slug=args.slug)
    validate_run_id(run_id)
    run_dir = default_runs_root(root) / run_id
    if run_dir.exists() and not args.force:
        raise PlanError(f"{run_dir} already exists; pass --force to replace it")
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "issue": args.issue,
        "slug": args.slug,
        "repo": FORK_REPO,
        "sha": run_git(root, "rev-parse", "HEAD"),
        "branch": run_git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "created_at_utc": now_utc(),
        "status": "research",
    }
    write_json(run_dir / "manifest.json", manifest)
    latest_pointer(default_runs_root(root)).write_text(run_id + "\n", encoding="utf-8")
    print(run_dir)
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    root = repo_root()
    if args.url and UPSTREAM_HOST in args.url and not args.allow_upstream:
        raise PlanError(
            "refusing AstrBotDevs/AstrBot; pass --allow-upstream after explicit confirmation"
        )
    run_dir = resolve_run_dir(root, args.run_dir)
    manifest = load_manifest(run_dir)
    issue = args.issue if args.issue is not None else manifest.get("issue")
    if not isinstance(issue, int):
        raise PlanError("fetch requires --issue or a workspace created with --issue")
    expected = manifest.get("issue")
    if isinstance(expected, int) and expected != issue:
        raise PlanError(f"workspace is issue-{expected}, not {issue}")
    command = [
        "gh",
        "issue",
        "view",
        str(issue),
        "--repo",
        FORK_REPO,
        "--json",
        "number,title,body,labels,comments,url,state,author,createdAt",
    ]
    try:
        payload = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "gh issue view failed"
        raise PlanError(detail) from exc
    data = json.loads(payload)
    url = str(data.get("url", ""))
    if UPSTREAM_HOST in url and not args.allow_upstream:
        raise PlanError(
            "fetched URL is on AstrBotDevs/AstrBot; pass --allow-upstream after confirmation"
        )
    title = str(data.get("title", "")).strip() or f"Issue {issue}"
    body = str(data.get("body") or "").rstrip()
    labels = ", ".join(
        str(item.get("name", ""))
        for item in data.get("labels", [])
        if isinstance(item, dict)
    )
    issue_md = (
        f"# {title}\n\n"
        f"- URL: {url}\n"
        f"- State: {data.get('state')}\n"
        f"- Labels: {labels or 'none'}\n\n"
        f"{body}\n"
    )
    (run_dir / "ISSUE.md").write_text(issue_md, encoding="utf-8")
    (run_dir / "issue.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(run_dir / "ISSUE.md")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    plan_path = run_dir / "PLAN.md"
    if not plan_path.is_file():
        raise PlanError(f"missing {plan_path}")
    errors = validate_plan(plan_path.read_text(encoding="utf-8"))
    if not args.plan_only:
        for name in ALIGN_FILES:
            if not (run_dir / name).is_file():
                errors.append(f"missing {name}")
        research_path = run_dir / "RESEARCH.md"
        if research_path.is_file():
            errors.extend(validate_research(research_path.read_text(encoding="utf-8")))
        quiz_path = run_dir / "QUIZ.md"
        if quiz_path.is_file():
            errors.extend(validate_quiz(quiz_path.read_text(encoding="utf-8")))
    if errors:
        raise PlanError("\n".join(errors))
    print(f"ok\t{plan_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    manifest = load_manifest(run_dir)
    files = [name for name in STATUS_FILES if (run_dir / name).is_file()]
    print(
        f"{manifest['run_id']}\t{manifest.get('sha', '')}\t"
        f"{manifest.get('status', '')}\t{','.join(files) or 'none'}\t{run_dir}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="explicit workspace directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a workspace")
    init.add_argument("--issue", type=int)
    init.add_argument("--slug")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    fetch = sub.add_parser("fetch", help="write ISSUE.md from GitHub")
    fetch.add_argument("--issue", type=int)
    fetch.add_argument("--url")
    fetch.add_argument("--allow-upstream", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    validate = sub.add_parser("validate", help="check PLAN.md")
    validate.add_argument("--plan-only", action="store_true")
    validate.set_defaults(func=cmd_validate)

    status = sub.add_parser("status", help="print workspace status")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
