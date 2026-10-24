#!/usr/bin/env python3
"""Track an upstream sync interval and render its review report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from upstream_decisions import latest_by_commit, load_events

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DISPOSITIONS = {"cherry-pick", "adapt", "skip", "replay", "revisit"}
VERDICTS = {"pass", "fix", "revisit"}
SEVERITIES = {"critical", "high", "medium", "low", "blocker", "major", "minor"}
CATEGORIES = {
    "bug",
    "security",
    "performance",
    "maintainability",
    "test",
    "documentation",
    "provenance",
    "architecture",
    "generated",
    "other",
}
STATUSES = {"pending", "in_progress", "needs_fix", "reviewed", "complete", "revisit"}
SCHEMA_VERSION = 1


class StateError(ValueError):
    """Raised for invalid run state or input."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_sha(value: str) -> str:
    value = value.strip().lower()
    if not SHA_RE.fullmatch(value):
        raise StateError(f"expected a full 40-character SHA: {value!r}")
    return value


def run_git(repo: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise StateError(exc.stderr.strip() or "git command failed") from exc


def read_marker(sync_file: Path) -> str:
    text = sync_file.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s+commit:\s*([0-9a-f]{40})\s*$", text)
    if not match:
        raise StateError(f"could not find a full sync marker in {sync_file}")
    return match.group(1)


def default_state_path(repo: Path, marker: str, head: str) -> Path:
    return repo / ".tmp" / "sync-run" / f"{marker[:12]}-{head[:12]}.json"


def new_state(marker: str, head: str) -> dict[str, Any]:
    timestamp = now_utc()
    return {
        "schema_version": SCHEMA_VERSION,
        "marker": marker,
        "head": head,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "commits": {},
    }


def new_entry() -> dict[str, Any]:
    return {
        "status": "pending",
        "disposition": None,
        "integration_commits": [],
        "tests": [],
        "review": None,
        "residual_risk": "",
    }


def validate_review(review: Any) -> None:
    if not isinstance(review, dict):
        raise StateError("review must be an object")
    if review.get("verdict") not in VERDICTS:
        raise StateError("review.verdict must be pass, fix, or revisit")
    if not str(review.get("reviewer", "")).strip():
        raise StateError("review.reviewer is required")
    findings = str(review.get("findings", ""))
    if review["verdict"] != "pass" and not findings.strip():
        raise StateError("review.findings is required unless the verdict is pass")
    summary = review.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise StateError("review.summary must be a string")
    for key in ("reviewed_files", "skipped_files"):
        values = review.get(key, [])
        if not isinstance(values, list):
            raise StateError(f"review.{key} must be an array")
    for value in review.get("reviewed_files", []):
        if not isinstance(value, str) or not value.strip():
            raise StateError("review.reviewed_files must contain non-empty paths")
    for value in review.get("skipped_files", []):
        if not isinstance(value, dict) or not str(value.get("path", "")).strip():
            raise StateError("review.skipped_files must contain path objects")
        if not isinstance(value.get("reason", ""), str):
            raise StateError("review.skipped_files reasons must be strings")
    rounds = review.get("rounds")
    if not isinstance(rounds, int) or rounds < 1:
        raise StateError("review.rounds must be a positive integer")
    reviewed = review.get("reviewed_at_utc")
    if not isinstance(reviewed, str) or not ISO_RE.fullmatch(reviewed):
        raise StateError("review.reviewed_at_utc must be UTC ISO format")


def validate_entry(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise StateError("commit entry must be an object")
    if entry.get("status") not in STATUSES:
        raise StateError("invalid commit status")
    disposition = entry.get("disposition")
    if disposition is not None and disposition not in DISPOSITIONS:
        raise StateError("invalid disposition")
    for key in ("integration_commits", "tests"):
        values = entry.get(key, [])
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise StateError(f"{key} must be a string array")
    for value in entry.get("integration_commits", []):
        normalize_sha(value)
    for value in entry.get("tests", []):
        if not value.strip():
            raise StateError("tests cannot contain empty values")
    review = entry.get("review")
    if review is not None:
        validate_review(review)
    risk = entry.get("residual_risk", "")
    if not isinstance(risk, str):
        raise StateError("residual_risk must be a string")


def validate_state(state: Any) -> None:
    if not isinstance(state, dict):
        raise StateError("run state must be a JSON object")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise StateError("unsupported run state schema_version")
    normalize_sha(str(state.get("marker", "")))
    normalize_sha(str(state.get("head", "")))
    for key in ("created_at_utc", "updated_at_utc"):
        value = state.get(key)
        if not isinstance(value, str) or not ISO_RE.fullmatch(value):
            raise StateError(f"{key} must be UTC ISO format")
    commits = state.get("commits")
    if not isinstance(commits, dict):
        raise StateError("commits must be an object")
    for commit, entry in commits.items():
        normalize_sha(commit)
        validate_entry(entry)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise StateError(f"run state does not exist: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateError(f"invalid run state JSON: {exc}") from exc
    validate_state(state)
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = now_utc()
    validate_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def ensure_entry(state: dict[str, Any], commit: str) -> dict[str, Any]:
    commits = state["commits"]
    entry = commits.setdefault(commit, new_entry())
    validate_entry(entry)
    return entry


def git_commits(repo: Path, marker: str, head: str) -> list[tuple[str, str]]:
    raw = run_git(
        repo,
        "log",
        "--reverse",
        "--topo-order",
        "--format=%H%x1f%s",
        f"{marker}..{head}",
    )
    commits: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if "\x1f" not in line:
            continue
        commit, subject = line.split("\x1f", 1)
        commits.append((commit, subject))
    return commits


def print_result(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(value)


def add_state_argument(
    parser: argparse.ArgumentParser, *, required: bool = True
) -> None:
    parser.add_argument("--state", type=Path, required=required)


def cmd_init(args: argparse.Namespace) -> None:
    repo = args.repo.resolve()
    marker = normalize_sha(args.marker or read_marker(repo / args.sync_file))
    head = normalize_sha(
        run_git(repo, "rev-parse", "--verify", f"{args.head}^{{commit}}")
    )
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", marker, head],
        capture_output=True,
    )
    if ancestor.returncode:
        raise StateError(f"sync marker {marker} is not an ancestor of {head}")
    state_path = args.state or default_state_path(repo, marker, head)
    if state_path.exists() and not args.force:
        raise StateError(f"run state already exists: {state_path}")
    save_state(state_path, new_state(marker, head))
    print_result(state_path, args.json)


def cmd_start(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    commit = normalize_sha(args.commit)
    entry = ensure_entry(state, commit)
    if entry["status"] == "complete":
        raise StateError(f"{commit} is already complete")
    entry["status"] = "in_progress"
    entry["started_at_utc"] = now_utc()
    save_state(args.state, state)
    print_result({"commit": commit, "status": entry["status"]}, args.json)


def normalize_path(value: Any) -> str:
    if not isinstance(value, str):
        raise StateError("review paths must be strings")
    path = value.strip()
    if path.startswith("./"):
        path = path[2:]
    if not path:
        raise StateError("review paths cannot be empty")
    return path


def normalize_paths(items: Any) -> list[str]:
    if not isinstance(items, list):
        raise StateError("reviewed_files must be an array")
    return list(dict.fromkeys(normalize_path(item) for item in items))


def normalize_skipped(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        raise StateError("skipped_files must be an array")
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, str):
            path, reason = item, ""
        elif isinstance(item, dict):
            path = item.get("path")
            reason = str(item.get("reason", "")).strip()
        else:
            raise StateError("each skipped file must be a path or an object")
        result.append({"path": normalize_path(path), "reason": reason})
    return result


def changed_files(repo: Path, ref: str) -> list[str]:
    raw = run_git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", ref)
    return [line for line in raw.splitlines() if line]


def render_findings(items: Any) -> str:
    if not isinstance(items, list):
        raise StateError("review JSON findings must be an array")
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise StateError("each review JSON finding must be an object")
        severity = str(item.get("severity", "")).strip()
        category = str(item.get("category", "")).strip()
        if severity not in SEVERITIES:
            raise StateError(f"review severity must be one of {sorted(SEVERITIES)}")
        if category and category not in CATEGORIES:
            raise StateError(f"review category must be one of {sorted(CATEGORIES)}")
        path = str(item.get("path", "")).strip()
        line = item.get("line")
        summary = str(item.get("summary", "")).strip()
        instruction = str(item.get("instruction", "")).strip()
        if not summary:
            raise StateError("each review JSON finding needs a summary")
        location = f"{path}:{line}" if path and line else path
        prefix = "/".join(part for part in (severity, category) if part)
        lines.append(f"[{prefix}] {location}: {summary} -> {instruction}".strip())
    return "\n".join(lines)


def review_tests(items: Any) -> list[str]:
    if not isinstance(items, list):
        raise StateError("review JSON tests must be an array")
    tests: list[str] = []
    for item in items:
        if isinstance(item, str):
            tests.append(item)
        elif isinstance(item, dict) and item.get("command"):
            command = str(item["command"])
            result = str(item.get("result", "")).strip()
            tests.append(f"{command}: {result}" if result else command)
        else:
            raise StateError("each review JSON test needs a command")
    return tests


def cmd_review(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    commit = normalize_sha(args.commit)
    entry = state["commits"].get(commit)
    if entry is None:
        raise StateError(f"{commit} has not been started")
    if entry.get("status") == "complete":
        raise StateError(f"{commit} is already complete; run start to reopen it")
    review_json = getattr(args, "review_json", None)
    risk: str | None = None
    summary = ""
    reviewed_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    if review_json is not None:
        try:
            payload = json.loads(review_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(f"invalid review JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise StateError("review JSON must be an object")
        verdict = payload.get("verdict")
        if verdict not in VERDICTS:
            raise StateError("review JSON verdict must be pass, fix, or revisit")
        if args.verdict and args.verdict != verdict:
            raise StateError("--verdict does not match the review JSON")
        summary = str(payload.get("summary", "")).strip()
        if not summary:
            raise StateError("review JSON needs a one-paragraph summary")
        reviewed_files = normalize_paths(payload.get("reviewed_files", []))
        skipped_files = normalize_skipped(payload.get("skipped_files", []))
        changed_ref = getattr(args, "changed_files_from", None)
        if changed_ref:
            repo = Path(getattr(args, "repo", Path("."))).resolve()
            expected = set(changed_files(repo, changed_ref))
            covered = set(reviewed_files) | {item["path"] for item in skipped_files}
            missing = sorted(expected - covered)
            if missing:
                raise StateError(
                    "review did not cover changed files: " + ", ".join(missing)
                )
        findings = render_findings(payload.get("findings", []))
        tests = review_tests(payload.get("tests", []))
        risk = str(payload.get("residual_risk", "")).strip() or None
    else:
        verdict = args.verdict
        if verdict not in VERDICTS:
            raise StateError("--verdict is required")
        findings = args.findings
        if args.findings_file is not None:
            findings = args.findings_file.read_text(encoding="utf-8").strip()
        if verdict != "pass" and not findings:
            raise StateError("review findings cannot be empty")
        tests = list(args.test)
    reviewer = args.reviewer.strip()
    if reviewer != "codex" and not reviewer.startswith("codex/"):
        raise StateError("the reviewer must be Codex (codex/<model>)")
    previous = entry.get("review") or {}
    rounds = int(previous.get("rounds", 0)) + 1
    if verdict == "fix" and rounds > 2:
        raise StateError("after two fix rounds, record revisit instead")
    entry["review"] = {
        "verdict": verdict,
        "reviewer": reviewer,
        "rounds": rounds,
        "findings": findings,
        "reviewed_at_utc": now_utc(),
    }
    if summary:
        entry["review"]["summary"] = summary
    if reviewed_files:
        entry["review"]["reviewed_files"] = reviewed_files
    if skipped_files:
        entry["review"]["skipped_files"] = skipped_files
    if tests:
        entry["tests"] = list(dict.fromkeys(tests))
    if risk is not None:
        entry["residual_risk"] = risk
    entry["status"] = {
        "pass": "reviewed",
        "fix": "needs_fix",
        "revisit": "revisit",
    }[verdict]
    save_state(args.state, state)
    print_result(
        {"commit": commit, "status": entry["status"], "review": entry["review"]},
        args.json,
    )


def cmd_complete(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    commit = normalize_sha(args.commit)
    entry = state["commits"].get(commit)
    if entry is None:
        raise StateError(f"{commit} has not been started")
    review = entry.get("review")
    if review is None:
        raise StateError(f"{commit} has no independent review")
    integration = [normalize_sha(value) for value in args.integration_commit]
    if args.disposition == "revisit":
        if review["verdict"] != "revisit":
            raise StateError("a revisit decision needs a revisit review verdict")
        if integration:
            raise StateError("a revisit decision cannot name integration commits")
        entry["status"] = "revisit"
    else:
        if review["verdict"] != "pass":
            raise StateError("completion requires a passing review")
        if args.disposition in {"cherry-pick", "adapt", "replay"} and not integration:
            raise StateError(
                f"{args.disposition} requires at least one integration commit"
            )
        if args.disposition == "skip" and integration:
            raise StateError("a skip decision cannot name integration commits")
        entry["status"] = "complete"
    entry["disposition"] = args.disposition
    entry["integration_commits"] = integration
    if args.test:
        entry["tests"] = list(dict.fromkeys(args.test))
    if args.risk is not None:
        entry["residual_risk"] = args.risk.strip()
    entry["completed_at_utc"] = now_utc()
    save_state(args.state, state)
    print_result(
        {
            "commit": commit,
            "status": entry["status"],
            "disposition": entry["disposition"],
        },
        args.json,
    )


def cmd_show(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        return
    counts = Counter(entry["status"] for entry in state["commits"].values())
    print(f"state: {args.state}")
    print(f"interval: {state['marker']}..{state['head']}")
    print(
        "commits: "
        + ", ".join(f"{name}={counts.get(name, 0)}" for name in sorted(STATUSES))
    )
    for commit, entry in state["commits"].items():
        review = entry.get("review") or {}
        print(
            f"{entry['status']:12} {commit[:12]} "
            f"{entry.get('disposition') or '-':12} "
            f"{review.get('verdict') or '-'}"
        )


def table_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def cmd_report(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    ledger: dict[str, dict[str, Any]] = {}
    if args.ledger.exists():
        ledger = {
            commit: record
            for commit, record in latest_by_commit(load_events(args.ledger)).items()
            if record is not None
        }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for commit, subject in git_commits(
        args.repo.resolve(), state["marker"], state["head"]
    ):
        seen.add(commit)
        entry = state["commits"].get(commit, {})
        record = ledger.get(commit, {})
        review = entry.get("review") or {}
        if entry:
            status = entry.get("status", "pending")
        elif record:
            status = "revisit" if record.get("disposition") == "revisit" else "complete"
        else:
            status = "pending"
        rows.append(
            {
                "commit": commit,
                "subject": entry.get("summary") or record.get("summary") or subject,
                "status": status,
                "disposition": entry.get("disposition")
                or record.get("disposition", ""),
                "integration": entry.get("integration_commits")
                or record.get("integration_commits", []),
                "tests": entry.get("tests") or record.get("tests", []),
                "reviewer": review.get("reviewer") or record.get("reviewer", ""),
                "verdict": review.get("verdict") or record.get("review_verdict", ""),
                "rounds": review.get("rounds") or record.get("review_rounds", ""),
                "findings": review.get("findings") or record.get("review_notes", ""),
                "summary": review.get("summary", ""),
                "reviewed_files": review.get("reviewed_files", []),
                "skipped_files": review.get("skipped_files", []),
                "risk": entry.get("residual_risk", ""),
            }
        )
    for commit, entry in state["commits"].items():
        if commit in seen:
            continue
        record = ledger.get(commit, {})
        review = entry.get("review") or {}
        rows.append(
            {
                "commit": commit,
                "subject": record.get("summary") or "(not in interval)",
                "status": entry.get("status", "pending"),
                "disposition": entry.get("disposition")
                or record.get("disposition", ""),
                "integration": entry.get("integration_commits")
                or record.get("integration_commits", []),
                "tests": entry.get("tests") or record.get("tests", []),
                "reviewer": review.get("reviewer") or record.get("reviewer", ""),
                "verdict": review.get("verdict") or record.get("review_verdict", ""),
                "rounds": review.get("rounds") or record.get("review_rounds", ""),
                "findings": review.get("findings") or record.get("review_notes", ""),
                "summary": review.get("summary", ""),
                "reviewed_files": review.get("reviewed_files", []),
                "skipped_files": review.get("skipped_files", []),
                "risk": entry.get("residual_risk", ""),
            }
        )
    lines = [
        f"# Upstream sync {state['marker'][:12]}..{state['head'][:12]}",
        "",
        f"- Marker: `{state['marker']}`",
        f"- Head: `{state['head']}`",
        f"- Generated: {now_utc()}",
        f"- Commits: {len(rows)}",
        "",
        "| Upstream | Subject | Disposition | Status | Review | Integration | Tests |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        review = ""
        if row["verdict"]:
            review = f"{row['verdict']} by {row['reviewer']}"
            if row["rounds"]:
                review += f" (round {row['rounds']})"
        lines.append(
            "| "
            + " | ".join(
                table_cell(value)
                for value in (
                    row["commit"][:12],
                    row["subject"],
                    row["disposition"],
                    row["status"],
                    review,
                    ", ".join(x[:12] for x in row["integration"]),
                    ", ".join(row["tests"]),
                )
            )
            + " |"
        )
    lines.extend(["", "## Details", ""])
    for row in rows:
        lines.extend(
            [
                f"### `{row['commit'][:12]}` {row['subject']}",
                "",
                f"- Status: {row['status']}",
                f"- Disposition: {row['disposition'] or '-'}",
                f"- Integration: {', '.join(row['integration']) or '-'}",
                f"- Review: {row['verdict'] or '-'}"
                f"{f' by {row["reviewer"]}' if row['reviewer'] else ''}"
                f"{f' (round {row["rounds"]})' if row['rounds'] else ''}",
                f"- Summary: {row['summary'] or '-'}",
                f"- Reviewed files: {', '.join(row['reviewed_files']) or '-'}",
                "- Skipped files: "
                + (
                    ", ".join(
                        f"{item['path']} ({item['reason'] or 'no reason'})"
                        for item in row["skipped_files"]
                    )
                    or "-"
                ),
                f"- Findings: {row['findings'] or '-'}",
                f"- Tests: {', '.join(row['tests']) or '-'}",
                f"- Residual risk: {row['risk'] or '-'}",
                "",
            ]
        )
    report = "\n".join(lines).rstrip() + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(args.output)
    else:
        print(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create an interval checkpoint")
    init.add_argument("--repo", type=Path, default=Path("."))
    init.add_argument("--sync-file", type=Path, default=Path("upstream-sync.yaml"))
    init.add_argument("--marker")
    init.add_argument("--head", default="upstream/master")
    add_state_argument(init, required=False)
    init.add_argument("--force", action="store_true")
    init.add_argument("--json", action="store_true")
    init.set_defaults(handler=cmd_init)

    start = subparsers.add_parser("start", help="mark a commit as in progress")
    add_state_argument(start)
    start.add_argument("--commit", required=True)
    start.add_argument("--json", action="store_true")
    start.set_defaults(handler=cmd_start)

    review = subparsers.add_parser("review", help="record an independent review")
    add_state_argument(review)
    review.add_argument("--commit", required=True)
    findings = review.add_mutually_exclusive_group(required=True)
    findings.add_argument("--findings")
    findings.add_argument("--findings-file", type=Path)
    findings.add_argument("--review-json", type=Path)
    review.add_argument("--verdict", choices=sorted(VERDICTS))
    review.add_argument("--reviewer", default="codex")
    review.add_argument("--repo", type=Path, default=Path("."))
    review.add_argument(
        "--changed-files-from",
        help="check reviewed_files and skipped_files cover this commit's changed files",
    )
    review.add_argument("--test", action="append", default=[])
    review.add_argument("--json", action="store_true")
    review.set_defaults(handler=cmd_review)

    complete = subparsers.add_parser("complete", help="record the final decision")
    add_state_argument(complete)
    complete.add_argument("--commit", required=True)
    complete.add_argument("--disposition", choices=sorted(DISPOSITIONS), required=True)
    complete.add_argument("--integration-commit", action="append", default=[])
    complete.add_argument("--test", action="append", default=[])
    complete.add_argument("--risk")
    complete.add_argument("--json", action="store_true")
    complete.set_defaults(handler=cmd_complete)

    show = subparsers.add_parser("show", help="show checkpoint status")
    add_state_argument(show)
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=cmd_show)

    report = subparsers.add_parser("report", help="render the interval report")
    add_state_argument(report)
    report.add_argument("--repo", type=Path, default=Path("."))
    report.add_argument("--ledger", type=Path, default=Path("upstream-decisions.jsonl"))
    report.add_argument("--output", type=Path)
    report.set_defaults(handler=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except (StateError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
