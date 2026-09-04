#!/usr/bin/env python3
"""Append-only ledger for a product-audit run."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FINDING_RE = re.compile(
    r"^AUD-\d{8}-[a-z0-9-]+-\d{3}$",
)
SHORTSHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
STANDARD_URL_RE = re.compile(r"^https://[^\s]+$")

MODULE_IDS = (
    "runtime",
    "config",
    "authz",
    "db",
    "pipeline",
    "command",
    "platform",
    "provider",
    "agent",
    "star",
    "builtin-stars",
    "knowledge-base",
    "memory",
    "persona",
    "conversation",
    "cron",
    "skills",
    "computer",
    "backup",
    "dashboard-api",
    "dashboard-ui",
    "webchat",
    "cli",
    "sdk-api",
    "ops-supply-chain",
)

EVENT_TYPES = {
    "run_init",
    "module_status",
    "finding",
    "score",
    "diagram",
    "note",
    "delete",
}
MODULE_STATUSES = {
    "pending",
    "in_progress",
    "complete",
    "blocked",
    "skipped",
}
SEVERITIES = {"critical", "high", "medium", "low", "info"}
KINDS = {
    "defect",
    "security",
    "completeness",
    "architecture",
    "reliability",
    "performance",
    "operability",
    "docs",
    "test-gap",
    "supply-chain",
    "positive",
}
CONFIDENCES = {"confirmed", "likely", "suspected", "not_assessed"}
FINDING_STATUSES = {
    "open",
    "accepted",
    "fixed",
    "false_positive",
    "duplicate",
    "out_of_scope",
}
RATINGS = {"excellent", "good", "acceptable", "weak", "gap", "unrated"}
CORE_DIMENSIONS = (
    "functional_suitability",
    "code_correctness",
    "completeness",
    "security",
    "reliability",
    "performance_efficiency",
    "interaction_capability",
    "maintainability",
    "flexibility",
    "compatibility",
    "safety",
)
EXTRA_DIMENSIONS = (
    "observability",
    "operability",
    "documentation_fitness",
    "test_sufficiency",
    "supply_chain",
    "overall",
)
DIMENSIONS = CORE_DIMENSIONS + EXTRA_DIMENSIONS
DIAGRAM_TYPES = {
    "architecture",
    "workflow",
    "sequence",
    "dataflow",
    "lifecycle",
}
CONTRACT_VERDICTS = {
    "implemented",
    "partial",
    "contradicted",
    "stronger-than-spec",
    "absent",
    "undecidable",
}
UX_SMELLS = {
    "overloaded-screen",
    "click-cemetery",
    "form-graveyard",
    "silent-errors",
    "dead-end-states",
    "mystery-navigation",
    "contrast-blindness",
    "inconsistent-actions",
}
AI_UX_SLUGS = {
    "ai-transparency",
    "ai-capability-disclosure",
    "ai-user-control",
    "efficient-ai-correction",
    "ai-action-consequences",
    "agent-task-handoff",
    "ai-audit-trails",
    "automation-bias-prevention",
    "ai-accuracy-communication",
}
LOCATION_RE = re.compile(r"\S+:\S+")


class LedgerError(ValueError):
    """Raised for invalid ledger input or state."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file():
            return parent
    raise LedgerError("could not locate the AstrBot checkout root")


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
        raise LedgerError(detail) from exc


def default_runs_root(root: Path) -> Path:
    return root / ".tmp" / "product-audit"


def latest_pointer(runs_root: Path) -> Path:
    return runs_root / "LATEST"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{number}: invalid JSON") from exc
        events.append(payload)
    return events


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        )


def next_revision(events: list[dict[str, Any]]) -> int:
    revisions = [
        int(event["revision"])
        for event in events
        if isinstance(event.get("revision"), int)
    ]
    return max(revisions, default=0) + 1


def validate_event(event: Any, *, line_number: int | None = None) -> None:
    where = f" on line {line_number}" if line_number else ""
    if not isinstance(event, dict):
        raise LedgerError(f"ledger event{where} must be a JSON object")
    if event.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError(f"unsupported schema_version{where}")
    if event.get("event_type") not in EVENT_TYPES:
        raise LedgerError(f"invalid event_type{where}")
    recorded = event.get("recorded_at_utc")
    if not isinstance(recorded, str) or not ISO_RE.fullmatch(recorded):
        raise LedgerError(f"recorded_at_utc must be UTC ISO format{where}")
    if not isinstance(event.get("revision"), int) or event["revision"] < 1:
        raise LedgerError(f"revision must be a positive integer{where}")
    event_type = event["event_type"]
    if event_type == "delete":
        if not str(event.get("reason", "")).strip():
            raise LedgerError(f"delete events require reason{where}")
        return
    if event_type == "run_init":
        if not str(event.get("run_id", "")).strip():
            raise LedgerError(f"run_init requires run_id{where}")
        if not SHORTSHA_RE.fullmatch(str(event.get("git_sha", ""))):
            raise LedgerError(f"run_init requires git_sha{where}")
        modules = event.get("modules")
        if not isinstance(modules, list) or not modules:
            raise LedgerError(f"run_init requires modules{where}")
        unknown = [item for item in modules if item not in MODULE_IDS]
        if unknown:
            raise LedgerError(f"unknown module_id{where}: {unknown[0]}")
        return
    if event_type == "module_status":
        if event.get("module_id") not in MODULE_IDS:
            raise LedgerError(f"invalid module_id{where}")
        if event.get("status") not in MODULE_STATUSES:
            raise LedgerError(f"invalid module status{where}")
        if not str(event.get("summary", "")).strip():
            raise LedgerError(f"module_status requires summary{where}")
        return
    if event_type == "finding":
        if not isinstance(event.get("finding_id"), str) or not FINDING_RE.fullmatch(
            event["finding_id"]
        ):
            raise LedgerError(f"invalid finding_id{where}")
        if event.get("module_id") not in MODULE_IDS:
            raise LedgerError(f"invalid module_id{where}")
        if event.get("severity") not in SEVERITIES:
            raise LedgerError(f"invalid severity{where}")
        if event.get("kind") not in KINDS:
            raise LedgerError(f"invalid kind{where}")
        if event.get("confidence") not in CONFIDENCES:
            raise LedgerError(f"invalid confidence{where}")
        if event.get("status", "open") not in FINDING_STATUSES:
            raise LedgerError(f"invalid finding status{where}")
        for key in ("title", "location", "summary"):
            if not str(event.get(key, "")).strip():
                raise LedgerError(f"finding requires {key}{where}")
        standard = event.get("standard")
        clause = event.get("standard_clause")
        if standard:
            if not isinstance(standard, str) or not STANDARD_URL_RE.fullmatch(standard):
                raise LedgerError(f"standard must be an https URL{where}")
        if clause and not standard:
            raise LedgerError(f"standard_clause requires standard{where}")
        verdict = event.get("contract_verdict")
        if verdict is not None and verdict not in CONTRACT_VERDICTS:
            raise LedgerError(f"invalid contract_verdict{where}")
        if event.get("kind") == "completeness" and not verdict:
            raise LedgerError(f"completeness findings require contract_verdict{where}")
        if event.get("kind") == "security" and event.get("confidence") == "confirmed":
            if not str(event.get("boundary", "")).strip():
                raise LedgerError(
                    f"confirmed security findings require boundary{where}"
                )
        ux_smell = event.get("ux_smell")
        if ux_smell is not None and ux_smell not in UX_SMELLS:
            raise LedgerError(f"invalid ux_smell{where}")
        ai_ux = event.get("ai_ux")
        if ai_ux is not None and ai_ux not in AI_UX_SLUGS:
            raise LedgerError(f"invalid ai_ux{where}")
        trace = event.get("trace")
        if trace is not None:
            if not isinstance(trace, list) or not trace:
                raise LedgerError(f"trace must be a non-empty list{where}")
            for step in trace:
                if not isinstance(step, str) or not LOCATION_RE.search(step):
                    raise LedgerError(f"trace entries must be path:line{where}")
        return
    if event_type == "score":
        target = str(event.get("target", ""))
        if target != "product" and not target.startswith("module:"):
            raise LedgerError(f"score target must be product or module:<id>{where}")
        if target.startswith("module:"):
            module_id = target.split(":", 1)[1]
            if module_id not in MODULE_IDS:
                raise LedgerError(f"invalid score module{where}")
        if event.get("dimension") not in DIMENSIONS:
            raise LedgerError(f"invalid dimension{where}")
        if event.get("rating") not in RATINGS:
            raise LedgerError(f"invalid rating{where}")
        if not str(event.get("rationale", "")).strip():
            raise LedgerError(f"score requires rationale{where}")
        return
    if event_type == "diagram":
        if event.get("diagram_type") not in DIAGRAM_TYPES:
            raise LedgerError(f"invalid diagram_type{where}")
        if not str(event.get("name", "")).strip():
            raise LedgerError(f"diagram requires name{where}")
        if not str(event.get("path", "")).strip():
            raise LedgerError(f"diagram requires path{where}")
        return
    if event_type == "note" and not str(event.get("summary", "")).strip():
        raise LedgerError(f"note requires summary{where}")


def resolve_run_dir(root: Path, explicit: str | None) -> Path:
    runs_root = default_runs_root(root)
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = root / path
        if not (path / "audit.jsonl").is_file():
            raise LedgerError(f"no audit.jsonl under {path}")
        return path
    pointer = latest_pointer(runs_root)
    if pointer.is_file():
        target = Path(pointer.read_text(encoding="utf-8").strip())
        if not target.is_absolute():
            target = root / target
        if (target / "audit.jsonl").is_file():
            return target
    if not runs_root.is_dir():
        raise LedgerError("no product-audit run exists; run init first")
    candidates = sorted(
        (path for path in runs_root.iterdir() if (path / "audit.jsonl").is_file()),
        key=lambda path: path.name,
    )
    if not candidates:
        raise LedgerError("no product-audit run exists; run init first")
    return candidates[-1]


def load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise LedgerError(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def scoped_modules(events: list[dict[str, Any]]) -> list[str]:
    for event in events:
        if event.get("event_type") == "run_init":
            return list(event["modules"])
    raise LedgerError("ledger is missing run_init")


def latest_by_key(
    events: list[dict[str, Any]], event_type: str, key: str
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    deleted: set[str] = set()
    for event in events:
        if (
            event.get("event_type") == "delete"
            and event.get("deleted_type") == event_type
        ):
            deleted.add(str(event.get("deleted_key", "")))
            latest.pop(str(event.get("deleted_key", "")), None)
            continue
        if event.get("event_type") != event_type:
            continue
        ident = str(event.get(key, ""))
        if ident in deleted:
            continue
        latest[ident] = event
    return latest


def finding_counts(findings: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = dict.fromkeys(SEVERITIES, 0)
    counts["total_open"] = 0
    for finding in findings:
        if finding.get("status", "open") != "open":
            continue
        if finding.get("kind") == "positive":
            continue
        counts["total_open"] += 1
        counts[str(finding["severity"])] += 1
    return counts


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root()
    sha = run_git(root, "rev-parse", "HEAD")
    branch = run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if args.modules:
        modules = []
        for item in args.modules:
            for module_id in item.split(","):
                module_id = module_id.strip()
                if not module_id:
                    continue
                if module_id not in MODULE_IDS:
                    raise LedgerError(f"unknown module_id: {module_id}")
                if module_id not in modules:
                    modules.append(module_id)
    else:
        modules = list(MODULE_IDS)
    timestamp = now_utc()
    run_id = f"{timestamp.replace('-', '').replace(':', '')}-{sha[:7]}"
    run_dir = default_runs_root(root) / run_id
    if run_dir.exists():
        raise LedgerError(f"run directory already exists: {run_dir}")
    (run_dir / "modules").mkdir(parents=True)
    (run_dir / "diagrams").mkdir()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "git_sha": sha,
        "git_branch": branch,
        "started_at_utc": timestamp,
        "modules": modules,
        "auditor": args.auditor,
        "scope": "full" if modules == list(MODULE_IDS) else "modules",
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ledger = run_dir / "audit.jsonl"
    events: list[dict[str, Any]] = []
    init_event = {
        "schema_version": SCHEMA_VERSION,
        "event_type": "run_init",
        "recorded_at_utc": timestamp,
        "revision": 1,
        **manifest,
    }
    validate_event(init_event)
    append_event(ledger, init_event)
    events.append(init_event)
    for module_id in modules:
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_type": "module_status",
            "recorded_at_utc": now_utc(),
            "revision": next_revision(events),
            "module_id": module_id,
            "status": "pending",
            "summary": "queued",
        }
        validate_event(event)
        append_event(ledger, event)
        events.append(event)
        chapter_dir = run_dir / "modules" / module_id
        chapter_dir.mkdir()
        (chapter_dir / "CHAPTER.md").write_text(
            f"# {module_id}\n\n状态：pending\n",
            encoding="utf-8",
        )
    latest_pointer(default_runs_root(root)).write_text(
        str(run_dir.relative_to(root)) + "\n", encoding="utf-8"
    )
    print(run_dir)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    events = load_jsonl(run_dir / "audit.jsonl")
    for number, event in enumerate(events, 1):
        validate_event(event, line_number=number)
    manifest = load_manifest(run_dir)
    modules = scoped_modules(events)
    statuses = latest_by_key(events, "module_status", "module_id")
    findings = latest_by_key(events, "finding", "finding_id")
    print(f"run_dir\t{run_dir}")
    print(f"run_id\t{manifest['run_id']}")
    print(f"git_sha\t{manifest['git_sha']}")
    print(f"branch\t{manifest['git_branch']}")
    print(f"scope\t{manifest['scope']}")
    for module_id in modules:
        status = statuses.get(module_id, {})
        module_findings = [
            item for item in findings.values() if item.get("module_id") == module_id
        ]
        counts = finding_counts(module_findings)
        print(
            f"module\t{module_id}\t{status.get('status', 'missing')}\t"
            f"open={counts['total_open']}\tcrit={counts['critical']}\t"
            f"high={counts['high']}\t{status.get('summary', '')}"
        )
    counts = finding_counts(findings.values())
    print(
        f"findings\topen={counts['total_open']}\tcritical={counts['critical']}\t"
        f"high={counts['high']}\tmedium={counts['medium']}\tlow={counts['low']}"
    )
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    events = load_jsonl(run_dir / "audit.jsonl")
    modules = scoped_modules(events)
    statuses = latest_by_key(events, "module_status", "module_id")
    for module_id in modules:
        status = statuses.get(module_id, {}).get("status")
        if status == "in_progress":
            print(module_id)
            return 0
    for module_id in modules:
        status = statuses.get(module_id, {}).get("status")
        if status == "pending":
            print(module_id)
            return 0
    return 0


def write_event(run_dir: Path, event: dict[str, Any]) -> None:
    ledger = run_dir / "audit.jsonl"
    events = load_jsonl(ledger)
    event.setdefault("schema_version", SCHEMA_VERSION)
    event.setdefault("recorded_at_utc", now_utc())
    event["revision"] = next_revision(events)
    validate_event(event)
    append_event(ledger, event)


def cmd_module_status(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    write_event(
        run_dir,
        {
            "event_type": "module_status",
            "module_id": args.module,
            "status": args.status,
            "summary": args.summary,
        },
    )
    return 0


def cmd_add_finding(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    related = [item for item in (args.related_modules or []) if item]
    for module_id in related:
        if module_id not in MODULE_IDS:
            raise LedgerError(f"unknown related module: {module_id}")
    event: dict[str, Any] = {
        "event_type": "finding",
        "finding_id": args.finding_id,
        "module_id": args.module,
        "title": args.title,
        "severity": args.severity,
        "kind": args.kind,
        "confidence": args.confidence,
        "location": args.location,
        "summary": args.summary,
        "status": args.status,
        "sensitive": bool(args.sensitive),
    }
    for key, value in (
        ("cwe", args.cwe),
        ("asvs", args.asvs),
        ("iso25010", args.iso25010),
        ("standard", args.standard),
        ("standard_clause", args.standard_clause),
        ("impact", args.impact),
        ("recommendation", args.recommendation),
        ("supersedes", args.supersedes),
        ("contract_verdict", args.contract_verdict),
        ("boundary", args.boundary),
        ("ux_smell", args.ux_smell),
        ("ai_ux", args.ai_ux),
    ):
        if value:
            event[key] = value
    if args.stride:
        event["stride"] = args.stride
    if related:
        event["related_modules"] = related
    if args.trace:
        event["trace"] = args.trace
    write_event(run_dir, event)
    print(args.finding_id)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    target = args.target
    if args.module:
        target = f"module:{args.module}"
    write_event(
        run_dir,
        {
            "event_type": "score",
            "target": target,
            "dimension": args.dimension,
            "rating": args.rating,
            "rationale": args.rationale,
        },
    )
    return 0


def cmd_diagram(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    write_event(
        run_dir,
        {
            "event_type": "diagram",
            "name": args.name,
            "diagram_type": args.type,
            "path": args.path,
            "module_id": args.module or "",
            "summary": args.summary or args.name,
        },
    )
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    write_event(
        run_dir,
        {
            "event_type": "note",
            "module_id": args.module or "",
            "summary": args.summary,
        },
    )
    return 0


def cmd_list_findings(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    events = load_jsonl(run_dir / "audit.jsonl")
    findings = latest_by_key(events, "finding", "finding_id")
    rows = list(findings.values())
    if args.module:
        rows = [item for item in rows if item.get("module_id") == args.module]
    if args.severity:
        rows = [item for item in rows if item.get("severity") == args.severity]
    if args.kind:
        rows = [item for item in rows if item.get("kind") == args.kind]
    if not args.all_status:
        rows = [item for item in rows if item.get("status", "open") == "open"]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for item in rows:
        print(
            f"{item['finding_id']}\t{item['module_id']}\t{item['severity']}\t"
            f"{item['kind']}\t{item['confidence']}\t{item.get('status', 'open')}\t"
            f"{item['title']}"
        )
    return 0


def cmd_scores(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    events = load_jsonl(run_dir / "audit.jsonl")
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") != "score":
            continue
        latest[(str(event["target"]), str(event["dimension"]))] = event
    rows = list(latest.values())
    if args.module:
        rows = [item for item in rows if item.get("target") == f"module:{args.module}"]
    if args.target:
        rows = [item for item in rows if item.get("target") == args.target]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for item in rows:
        print(
            f"{item['target']}\t{item['dimension']}\t{item['rating']}\t"
            f"{item['rationale']}"
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    events = load_jsonl(run_dir / "audit.jsonl")
    if not events:
        raise LedgerError("empty ledger")
    for number, event in enumerate(events, 1):
        validate_event(event, line_number=number)
    modules = scoped_modules(events)
    statuses = latest_by_key(events, "module_status", "module_id")
    findings = latest_by_key(events, "finding", "finding_id")
    errors: list[str] = []
    for module_id in modules:
        if module_id not in statuses:
            errors.append(f"missing module_status for {module_id}")
    seen_ids: set[str] = set()
    for finding in findings.values():
        finding_id = finding["finding_id"]
        if finding_id in seen_ids:
            errors.append(f"duplicate finding_id {finding_id}")
        seen_ids.add(finding_id)
        module_token = finding_id[13:].rsplit("-", 1)[0]
        if module_token != finding["module_id"]:
            errors.append(f"{finding_id} module mismatch ({finding['module_id']})")
        if finding["kind"] == "positive" and finding.get("severity") != "info":
            errors.append(f"{finding_id} positive findings must be info")
    if args.strict:
        incomplete = [
            module_id
            for module_id in modules
            if statuses.get(module_id, {}).get("status") in {"pending", "in_progress"}
        ]
        if incomplete:
            errors.append("incomplete modules: " + ",".join(incomplete))
        scores = {
            (event["target"], event["dimension"]): event
            for event in events
            if event.get("event_type") == "score"
        }
        for module_id in modules:
            if statuses.get(module_id, {}).get("status") != "complete":
                continue
            for dimension in (
                "overall",
                "functional_suitability",
                "code_correctness",
                "completeness",
                "security",
            ):
                if ("module:" + module_id, dimension) not in scores:
                    errors.append(f"missing {dimension} score for {module_id}")
    if errors:
        raise LedgerError("\n".join(errors))
    print(f"ok\tevents={len(events)}\tmodules={len(modules)}\tfindings={len(findings)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="explicit run directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a new audit run")
    init.add_argument("--modules", nargs="*", help="subset of module ids")
    init.add_argument("--auditor", default="agent")
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="print run and module status")
    status.set_defaults(func=cmd_status)

    nxt = sub.add_parser("next", help="print the next pending module id")
    nxt.set_defaults(func=cmd_next)

    module_status = sub.add_parser("module-status", help="update one module")
    module_status.add_argument("--module", required=True, choices=MODULE_IDS)
    module_status.add_argument(
        "--status", required=True, choices=sorted(MODULE_STATUSES)
    )
    module_status.add_argument("--summary", required=True)
    module_status.set_defaults(func=cmd_module_status)

    finding = sub.add_parser("add-finding", help="append a finding")
    finding.add_argument("--finding-id", required=True)
    finding.add_argument("--module", required=True, choices=MODULE_IDS)
    finding.add_argument("--title", required=True)
    finding.add_argument("--severity", required=True, choices=sorted(SEVERITIES))
    finding.add_argument("--kind", required=True, choices=sorted(KINDS))
    finding.add_argument("--confidence", required=True, choices=sorted(CONFIDENCES))
    finding.add_argument("--location", required=True)
    finding.add_argument("--summary", required=True)
    finding.add_argument("--status", default="open", choices=sorted(FINDING_STATUSES))
    finding.add_argument("--cwe")
    finding.add_argument("--asvs")
    finding.add_argument("--iso25010")
    finding.add_argument(
        "--standard",
        help="HTTPS URL of the official spec page from references/standards.md",
    )
    finding.add_argument(
        "--standard-clause",
        help="short locator on that page, e.g. v5.0.0-8.2.1",
    )
    finding.add_argument("--stride", nargs="*")
    finding.add_argument("--related-modules", nargs="*")
    finding.add_argument("--impact")
    finding.add_argument("--recommendation")
    finding.add_argument("--supersedes")
    finding.add_argument(
        "--contract-verdict",
        choices=sorted(CONTRACT_VERDICTS),
        help="docs/OpenAPI/UI vs runtime verdict",
    )
    finding.add_argument(
        "--boundary",
        help="trust boundary crossed; required for confirmed security",
    )
    finding.add_argument(
        "--trace",
        nargs="*",
        help="entrypoint-to-sink path:line steps",
    )
    finding.add_argument(
        "--ux-smell",
        choices=sorted(UX_SMELLS),
        help="optional named UX antipattern tag",
    )
    finding.add_argument(
        "--ai-ux",
        choices=sorted(AI_UX_SLUGS),
        help="optional AI-interface principle slug",
    )
    finding.add_argument("--sensitive", action="store_true")
    finding.set_defaults(func=cmd_add_finding)

    score = sub.add_parser("score", help="record a dimension rating")
    score.add_argument("--target", default="product")
    score.add_argument("--module", choices=MODULE_IDS)
    score.add_argument("--dimension", required=True, choices=DIMENSIONS)
    score.add_argument("--rating", required=True, choices=sorted(RATINGS))
    score.add_argument("--rationale", required=True)
    score.set_defaults(func=cmd_score)

    diagram = sub.add_parser("diagram", help="record a delivered diagram")
    diagram.add_argument("--name", required=True)
    diagram.add_argument("--type", required=True, choices=sorted(DIAGRAM_TYPES))
    diagram.add_argument("--path", required=True)
    diagram.add_argument("--module", choices=MODULE_IDS)
    diagram.add_argument("--summary")
    diagram.set_defaults(func=cmd_diagram)

    note = sub.add_parser("note", help="append a free-form checkpoint note")
    note.add_argument("--summary", required=True)
    note.add_argument("--module", choices=MODULE_IDS)
    note.set_defaults(func=cmd_note)

    listed = sub.add_parser("list-findings", help="list findings")
    listed.add_argument("--module", choices=MODULE_IDS)
    listed.add_argument("--severity", choices=sorted(SEVERITIES))
    listed.add_argument("--kind", choices=sorted(KINDS))
    listed.add_argument("--all-status", action="store_true")
    listed.add_argument("--json", action="store_true")
    listed.set_defaults(func=cmd_list_findings)

    scores = sub.add_parser("scores", help="list latest scores")
    scores.add_argument("--module", choices=MODULE_IDS)
    scores.add_argument("--target")
    scores.add_argument("--json", action="store_true")
    scores.set_defaults(func=cmd_scores)

    validate = sub.add_parser("validate", help="validate the ledger")
    validate.add_argument(
        "--strict",
        action="store_true",
        help="require complete modules and hard-dimension scores",
    )
    validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
