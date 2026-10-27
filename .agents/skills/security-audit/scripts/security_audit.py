#!/usr/bin/env python3
"""Manage and validate a security-audit run under .tmp/security-audit/.

Commands:
    init      create a run directory with metadata, ledger, and findings files
    status    summarize the latest or selected run
    validate  check metadata, coverage-ledger.json, and findings.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXECUTION_POLICY = "sandboxed-source-and-local-only"
PROFILES = ("quick", "standard", "deep")
RUN_STATUSES = ("in_progress", "complete", "incomplete")
UNIT_STATUSES = (
    "planned",
    "in_progress",
    "blocked",
    "covered",
    "candidate",
    "deferred",
    "not_applicable",
    "out_of_scope",
)
UNOWNED_STATUSES = ("planned", "deferred", "not_applicable", "out_of_scope")
PRIOR_STATUSES = (
    "new",
    "none",
    "prior_confirmed_same_source",
    "prior_confirmed_changed_source",
    "prior_needs_validation",
    "prior_deferred",
    "prior_blocked",
    "prior_out_of_scope",
    "prior_covered_same_source",
    "prior_covered_changed_source",
    "prior_rejected_claim_changed",
)
CHECK_METHODS = ("source", "local")
SEVERITIES = ("informational", "low", "medium", "high", "critical")
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}
CONFIDENCES = ("low", "medium", "high")
TRACE_KINDS = ("entrypoint", "propagation", "sink")
CONDITION_KINDS = (
    "authentication_level",
    "authorization_role",
    "user_interaction",
    "system_configuration",
    "network_routing",
    "environmental_dependency",
    "data_state",
    "timing_dependency",
    "third_party_dependency",
)

CONFIRMED_FIELDS = frozenset(
    {
        "verdict",
        "fingerprint",
        "title",
        "description",
        "root_cause",
        "intended_behavior",
        "trace",
        "evidence",
        "conditions",
        "execution",
        "remediation",
        "severity",
        "confidence",
    }
)
NEEDS_FIELDS = frozenset(
    {
        "verdict",
        "fingerprint",
        "title",
        "description",
        "claimed_root_cause",
        "trace",
        "evidence",
        "blockers",
        "validation_plan",
    }
)
REJECTED_FIELDS = frozenset(
    {
        "verdict",
        "fingerprint",
        "title",
        "description",
        "claimed_root_cause",
        "trace",
        "evidence",
        "reason",
    }
)

UNIT_REQUIRED = (
    "coverage_id",
    "canonical_refs",
    "surface",
    "boundary",
    "subsystem",
    "attack_class",
    "starting_paths",
    "status",
    "agent_id",
    "reviewed_paths",
    "checks",
    "result_fingerprints",
    "unresolved",
)
CHECK_FIELDS = frozenset(
    {"agent_id", "reviewed_paths", "invariant", "method", "result", "artifact"}
)
TRACE_FIELDS = frozenset({"kind", "file", "line", "scope", "description"})
EVIDENCE_FIELDS = frozenset({"file", "line", "description"})
CONDITION_FIELDS = frozenset({"kind", "description"})
EXECUTION_FIELDS = frozenset(
    {"attacker_perspective", "payloads", "instructions", "observed_result"}
)
REMEDIATION_FIELDS = frozenset({"strategy", "code_changes"})
CODE_CHANGE_FIELDS = frozenset({"file_name", "fixed_code"})
SEVERITY_FIELDS = frozenset({"likelihood", "impact", "overall_severity"})
SEVERITY_SCORE_FIELDS = frozenset({"score", "reason"})
CONFIDENCE_FIELDS = frozenset({"score", "reason"})
PLAN_FIELDS = frozenset({"local", "deployment"})

FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u2028\u2029]")

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNITS = 10_000
MAX_FINDINGS = 1_000
MAX_DEPTH = 64
MAX_ERRORS = 100


class SecurityAuditError(ValueError):
    """Raised for invalid run state or input."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file():
            return parent
    raise SecurityAuditError("could not locate the AstrBot checkout root")


def run_git(root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or "git command failed"
        raise SecurityAuditError(str(detail).strip()) from exc


def runs_root(root: Path) -> Path:
    return root / ".tmp" / "security-audit"


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise SecurityAuditError(f"missing {path.name}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise SecurityAuditError(f"{path.name} exceeds {MAX_FILE_BYTES} bytes")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecurityAuditError(f"{path.name}: invalid JSON") from exc


def json_depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((json_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((json_depth(item) for item in value), default=0)
    return 0


def resolve_run_dir(root: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_absolute() else root / path
    base = runs_root(root)
    pointer = base / "LATEST"
    if pointer.is_file():
        candidate = base / pointer.read_text(encoding="utf-8").strip()
        if candidate.is_dir():
            return candidate
    candidates = sorted(
        (path for path in base.glob("run-*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SecurityAuditError(
            "no security-audit run found under .tmp/security-audit"
        )
    return candidates[-1]


def next_run_id(base: Path) -> str:
    numbers = []
    for path in base.glob("run-*"):
        suffix = path.name.removeprefix("run-")
        if suffix.isdigit():
            numbers.append(int(suffix))
    return f"run-{max(numbers, default=0) + 1}"


def add_error(errors: list[str], message: str) -> None:
    if len(errors) < MAX_ERRORS:
        errors.append(message)


def is_visible(value: str) -> bool:
    return (
        bool(value.strip()) and CONTROL_RE.search(value) is None and "\x00" not in value
    )


def check_string(
    value: Any,
    where: str,
    errors: list[str],
    *,
    allow_empty: bool = False,
) -> bool:
    if not isinstance(value, str):
        add_error(errors, f"{where} must be a string")
        return False
    if not allow_empty and not is_visible(value):
        add_error(errors, f"{where} must contain visible text")
        return False
    return True


def check_int(value: Any, where: str, errors: list[str], *, minimum: int = 1) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        add_error(errors, f"{where} must be an integer >= {minimum}")
        return False
    return True


def check_rel_path(value: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        add_error(errors, f"{where} must be a nonempty repository-relative path")
        return False
    if value.startswith("/") or DRIVE_RE.match(value) or "\\" in value:
        add_error(errors, f"{where} must be repository-relative: {value!r}")
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        add_error(errors, f"{where} has an unsafe path segment: {value!r}")
        return False
    return True


def check_paths(
    value: Any,
    where: str,
    errors: list[str],
    *,
    nonempty: bool,
) -> list[str] | None:
    if not isinstance(value, list):
        add_error(errors, f"{where} must be a list")
        return None
    if nonempty and not value:
        add_error(errors, f"{where} must not be empty")
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not check_rel_path(item, f"{where}[{index}]", errors):
            continue
        if item in seen:
            add_error(errors, f"{where} contains duplicate {item!r}")
        seen.add(item)
    return value


def check_exact_fields(
    payload: Any,
    expected: frozenset[str],
    where: str,
    errors: list[str],
) -> bool:
    if not isinstance(payload, dict):
        add_error(errors, f"{where} must be an object")
        return False
    missing = sorted(expected - payload.keys())
    extra = sorted(payload.keys() - expected)
    if missing:
        add_error(errors, f"{where} is missing {', '.join(missing)}")
    if extra:
        add_error(errors, f"{where} has unexpected {', '.join(extra)}")
    return not missing and not extra


def check_agent_id(value: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not AGENT_ID_RE.fullmatch(value):
        add_error(errors, f"{where} must be a lowercase canonical agent id")
        return False
    return True


def check_fingerprint(value: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
        add_error(errors, f"{where} must match {FINGERPRINT_RE.pattern}")
        return False
    return True


def validate_metadata(meta: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(meta, dict):
        return ["run-metadata.json must be an object"]
    if meta.get("schema_version") != SCHEMA_VERSION:
        add_error(errors, "run-metadata.json has unsupported schema_version")
    if not isinstance(meta.get("run_id"), str) or not RUN_ID_RE.fullmatch(
        meta["run_id"]
    ):
        add_error(errors, "run_id must match a safe run directory name")
    check_string(meta.get("repo"), "repo", errors)
    check_string(meta.get("target"), "target", errors)
    source_ref = meta.get("source_ref")
    if not isinstance(source_ref, dict):
        add_error(errors, "source_ref must be an object")
    else:
        if not isinstance(source_ref.get("sha"), str) or not SHA_RE.fullmatch(
            source_ref["sha"]
        ):
            add_error(errors, "source_ref.sha must be a git object name")
        if not isinstance(source_ref.get("dirty"), bool):
            add_error(errors, "source_ref.dirty must be a boolean")
    if meta.get("profile") not in PROFILES:
        add_error(errors, f"profile must be one of {', '.join(PROFILES)}")
    check_paths(meta.get("scope_paths"), "scope_paths", errors, nonempty=False)
    budget = meta.get("budget")
    if budget is not None and (
        not isinstance(budget, int) or isinstance(budget, bool) or budget < 1
    ):
        add_error(errors, "budget must be null or a positive integer")
    if meta.get("execution_policy") != EXECUTION_POLICY:
        add_error(errors, f"execution_policy must be {EXECUTION_POLICY!r}")
    prior_runs = meta.get("prior_runs")
    if not isinstance(prior_runs, list):
        add_error(errors, "prior_runs must be a list")
    else:
        for index, item in enumerate(prior_runs):
            check_string(item, f"prior_runs[{index}]", errors)
    status = meta.get("run_status")
    if status not in RUN_STATUSES:
        add_error(errors, f"run_status must be one of {', '.join(RUN_STATUSES)}")
    if status == "incomplete":
        check_string(meta.get("incomplete_reason"), "incomplete_reason", errors)
    created = meta.get("created_at_utc")
    if not isinstance(created, str) or not ISO_RE.fullmatch(created):
        add_error(errors, "created_at_utc must be a UTC ISO timestamp")
    return errors


def validate_check(check: Any, where: str, errors: list[str]) -> None:
    if not check_exact_fields(check, CHECK_FIELDS, where, errors):
        return
    check_agent_id(check["agent_id"], f"{where}.agent_id", errors)
    check_paths(
        check["reviewed_paths"], f"{where}.reviewed_paths", errors, nonempty=True
    )
    check_string(check["invariant"], f"{where}.invariant", errors)
    method = check["method"]
    if method not in CHECK_METHODS:
        add_error(errors, f"{where}.method must be source or local")
    check_string(check["result"], f"{where}.result", errors)
    artifact = check["artifact"]
    if method == "source":
        if artifact is not None:
            add_error(errors, f"{where}.artifact must be null for source checks")
        return
    if method != "local":
        return
    if not check_rel_path(artifact, f"{where}.artifact", errors):
        return
    agent_id = check["agent_id"]
    prefix = f"agents/{agent_id}/artifacts/"
    if not isinstance(agent_id, str) or not artifact.startswith(prefix):
        add_error(errors, f"{where}.artifact must be under {prefix}")
        return
    remainder = artifact[len(prefix) :]
    if not remainder.strip("/"):
        add_error(errors, f"{where}.artifact must name a file")


def validate_attempt(
    attempt: Any, where: str, live_wave: Any, errors: list[str]
) -> None:
    if not isinstance(attempt, dict):
        add_error(errors, f"{where} must be an object")
        return
    for key in UNIT_REQUIRED:
        if key not in attempt:
            add_error(errors, f"{where} is missing {key}")
    status = attempt.get("status")
    if status not in {"blocked", "covered", "candidate"}:
        add_error(errors, f"{where}.status must be blocked, covered, or candidate")
    wave = attempt.get("wave")
    if check_int(wave, f"{where}.wave", errors):
        if isinstance(live_wave, int) and wave >= live_wave:
            add_error(errors, f"{where}.wave must be below the live wave")
    check_string(
        attempt.get("reassignment_reason"), f"{where}.reassignment_reason", errors
    )
    if "attempts" in attempt:
        add_error(errors, f"{where} must not nest attempts")
    validate_evidence_state(attempt, where, errors, require_owner=True)


def validate_evidence_state(
    unit: dict[str, Any],
    where: str,
    errors: list[str],
    *,
    require_owner: bool,
) -> None:
    status = unit.get("status")
    agent_id = unit.get("agent_id")
    reviewed = unit.get("reviewed_paths")
    checks = unit.get("checks")
    fingerprints = unit.get("result_fingerprints")
    unresolved = unit.get("unresolved")
    for key, value in (
        ("reviewed_paths", reviewed),
        ("checks", checks),
        ("result_fingerprints", fingerprints),
        ("unresolved", unresolved),
    ):
        if not isinstance(value, list):
            add_error(errors, f"{where}.{key} must be a list")
            return

    if status in UNOWNED_STATUSES:
        if agent_id is not None:
            add_error(errors, f"{where}.agent_id must be null for {status}")
        for key in ("reviewed_paths", "checks", "result_fingerprints"):
            if unit[key]:
                add_error(errors, f"{where}.{key} must be empty for {status}")
        if status == "planned":
            if unresolved:
                add_error(errors, f"{where}.unresolved must be empty for planned")
        elif not unresolved:
            add_error(errors, f"{where}.unresolved needs a reason for {status}")
        return

    if not require_owner and agent_id is None:
        add_error(errors, f"{where}.agent_id is required for {status}")
    if require_owner or status != "in_progress":
        check_agent_id(agent_id, f"{where}.agent_id", errors)

    if status == "in_progress":
        for key in ("reviewed_paths", "checks", "result_fingerprints", "unresolved"):
            if unit[key]:
                add_error(errors, f"{where}.{key} must be empty while in_progress")
        return

    check_paths(reviewed, f"{where}.reviewed_paths", errors, nonempty=True)
    if not checks:
        add_error(errors, f"{where}.checks must not be empty for {status}")
    union: set[str] = set()
    for index, check in enumerate(checks):
        validate_check(check, f"{where}.checks[{index}]", errors)
        if isinstance(check, dict) and isinstance(check.get("reviewed_paths"), list):
            union.update(
                item for item in check["reviewed_paths"] if isinstance(item, str)
            )
    if isinstance(reviewed, list):
        if set(reviewed) != union:
            add_error(
                errors,
                f"{where}.reviewed_paths must equal the union of check paths",
            )

    seen: set[str] = set()
    for index, fingerprint in enumerate(fingerprints):
        if check_fingerprint(
            fingerprint, f"{where}.result_fingerprints[{index}]", errors
        ):
            if fingerprint in seen:
                add_error(errors, f"{where} has duplicate fingerprint {fingerprint}")
            seen.add(fingerprint)

    if status == "blocked" and not unresolved:
        add_error(errors, f"{where}.unresolved must not be empty for blocked")
    if status == "covered" and unresolved:
        add_error(errors, f"{where}.unresolved must be empty for covered")
    if status in {"blocked", "covered"} and fingerprints:
        add_error(errors, f"{where}.result_fingerprints must be empty for {status}")
    if status == "candidate" and not fingerprints:
        add_error(
            errors, f"{where}.result_fingerprints must not be empty for candidate"
        )


def validate_unit(unit: Any, where: str, errors: list[str]) -> None:
    if not isinstance(unit, dict):
        add_error(errors, f"{where} must be an object")
        return
    for key in UNIT_REQUIRED:
        if key not in unit:
            add_error(errors, f"{where} is missing {key}")
    coverage_id = unit.get("coverage_id")
    if not isinstance(coverage_id, str) or not FINGERPRINT_RE.fullmatch(coverage_id):
        add_error(errors, f"{where}.coverage_id must be a stable identifier")
    refs = unit.get("canonical_refs")
    if not isinstance(refs, dict):
        add_error(errors, f"{where}.canonical_refs must be an object")
    else:
        for key in ("surface", "boundary", "subsystem", "attack_class"):
            check_string(refs.get(key), f"{where}.canonical_refs.{key}", errors)
        if "lifecycle" in refs:
            check_string(refs["lifecycle"], f"{where}.canonical_refs.lifecycle", errors)
    for key in ("surface", "boundary", "subsystem", "attack_class", "lifecycle"):
        if key in unit:
            check_string(unit[key], f"{where}.{key}", errors)
    check_paths(
        unit.get("starting_paths"), f"{where}.starting_paths", errors, nonempty=True
    )
    status = unit.get("status")
    if status not in UNIT_STATUSES:
        add_error(errors, f"{where}.status is invalid: {status!r}")
        return
    if "wave" in unit:
        check_int(unit["wave"], f"{where}.wave", errors)
    if "prior_status" in unit and unit["prior_status"] not in PRIOR_STATUSES:
        add_error(errors, f"{where}.prior_status is invalid")
    blocks = unit.get("excluded_blocks")
    if blocks is not None:
        if not isinstance(blocks, list):
            add_error(errors, f"{where}.excluded_blocks must be a list")
        else:
            for index, block in enumerate(blocks):
                if not check_exact_fields(
                    block,
                    frozenset({"block", "reason"}),
                    f"{where}.excluded_blocks[{index}]",
                    errors,
                ):
                    continue
                check_string(
                    block["block"], f"{where}.excluded_blocks[{index}].block", errors
                )
                check_string(
                    block["reason"], f"{where}.excluded_blocks[{index}].reason", errors
                )
    selected = unit.get("selected_companion_blocks")
    if selected is not None:
        if not isinstance(selected, list):
            add_error(errors, f"{where}.selected_companion_blocks must be a list")
        else:
            for index, block in enumerate(selected):
                check_string(
                    block, f"{where}.selected_companion_blocks[{index}]", errors
                )
    validate_evidence_state(unit, where, errors, require_owner=False)
    attempts = unit.get("attempts")
    if attempts is not None:
        if not isinstance(attempts, list):
            add_error(errors, f"{where}.attempts must be a list")
        else:
            for index, attempt in enumerate(attempts):
                validate_attempt(
                    attempt, f"{where}.attempts[{index}]", unit.get("wave"), errors
                )


def validate_ledger(
    units: Any, *, root: Path | None = None, check_paths_exist: bool = False
) -> list[str]:
    errors: list[str] = []
    if not isinstance(units, list):
        return ["coverage-ledger.json must be a JSON array"]
    if len(units) > MAX_UNITS:
        add_error(errors, f"coverage ledger exceeds {MAX_UNITS} units")
    if json_depth(units) > MAX_DEPTH:
        add_error(errors, f"coverage ledger exceeds {MAX_DEPTH} nesting levels")
    identifiers: set[str] = set()
    tuples: set[tuple[str, ...]] = set()
    for index, unit in enumerate(units):
        where = f"units[{index}]"
        validate_unit(unit, where, errors)
        if not isinstance(unit, dict):
            continue
        coverage_id = unit.get("coverage_id")
        if isinstance(coverage_id, str):
            if coverage_id in identifiers:
                add_error(errors, f"duplicate coverage_id {coverage_id!r}")
            identifiers.add(coverage_id)
        refs = unit.get("canonical_refs")
        if isinstance(refs, dict):
            keys = ("surface", "boundary", "subsystem", "attack_class", "lifecycle")
            values = tuple(str(refs.get(key, "")) for key in keys)
            if all(values[:4]) and values in tuples:
                add_error(
                    errors, f"semantic tuple is represented twice: {coverage_id!r}"
                )
            tuples.add(values)
        if check_paths_exist and root is not None:
            for key in ("starting_paths", "reviewed_paths"):
                values = unit.get(key)
                if not isinstance(values, list):
                    continue
                for path in values:
                    if isinstance(path, str) and check_rel_path(path, where, errors):
                        if not (root / path).exists():
                            add_error(errors, f"{where}.{key} does not exist: {path}")
    return errors


def validate_trace(trace: Any, where: str, errors: list[str]) -> None:
    if not isinstance(trace, list) or not trace:
        add_error(errors, f"{where}.trace must be a nonempty list")
        return
    kinds: list[str] = []
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(trace):
        item_where = f"{where}.trace[{index}]"
        if not check_exact_fields(item, TRACE_FIELDS, item_where, errors):
            continue
        kind = item["kind"]
        if kind not in TRACE_KINDS:
            add_error(errors, f"{item_where}.kind is invalid")
        kinds.append(kind if isinstance(kind, str) else "")
        check_rel_path(item["file"], f"{item_where}.file", errors)
        check_int(item["line"], f"{item_where}.line", errors)
        check_string(item["scope"], f"{item_where}.scope", errors)
        check_string(item["description"], f"{item_where}.description", errors)
        key = (item["kind"], item["file"], item["line"], item["scope"])
        if key in seen:
            add_error(errors, f"{item_where} duplicates an earlier step")
        seen.add(key)
    if len(kinds) == 1:
        if kinds[0] not in {"entrypoint", "sink"}:
            add_error(
                errors, f"{where}.trace has one step that is not entrypoint or sink"
            )
    elif kinds:
        if kinds[0] != "entrypoint":
            add_error(errors, f"{where}.trace must start at entrypoint")
        if kinds[-1] != "sink":
            add_error(errors, f"{where}.trace must end at sink")
        for index, kind in enumerate(kinds[1:-1], 1):
            if kind != "propagation":
                add_error(errors, f"{where}.trace[{index}] must be propagation")


def validate_evidence(evidence: Any, where: str, errors: list[str]) -> None:
    if not isinstance(evidence, list) or not evidence:
        add_error(errors, f"{where}.evidence must be a nonempty list")
        return
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(evidence):
        item_where = f"{where}.evidence[{index}]"
        if not check_exact_fields(item, EVIDENCE_FIELDS, item_where, errors):
            continue
        check_rel_path(item["file"], f"{item_where}.file", errors)
        check_int(item["line"], f"{item_where}.line", errors)
        check_string(item["description"], f"{item_where}.description", errors)
        key = (item["file"], item["line"], item["description"])
        if key in seen:
            add_error(errors, f"{item_where} duplicates an earlier entry")
        seen.add(key)


def validate_conditions(conditions: Any, where: str, errors: list[str]) -> None:
    if not isinstance(conditions, list):
        add_error(errors, f"{where}.conditions must be a list")
        return
    for index, item in enumerate(conditions):
        item_where = f"{where}.conditions[{index}]"
        if not check_exact_fields(item, CONDITION_FIELDS, item_where, errors):
            continue
        if item["kind"] not in CONDITION_KINDS:
            add_error(errors, f"{item_where}.kind is invalid")
        check_string(item["description"], f"{item_where}.description", errors)


def validate_execution(execution: Any, where: str, errors: list[str]) -> None:
    if not check_exact_fields(
        execution, EXECUTION_FIELDS, f"{where}.execution", errors
    ):
        return
    check_string(
        execution["attacker_perspective"],
        f"{where}.execution.attacker_perspective",
        errors,
    )
    payloads = execution["payloads"]
    if not isinstance(payloads, list) or not payloads:
        add_error(errors, f"{where}.execution.payloads must be a nonempty list")
    else:
        for index, item in enumerate(payloads):
            check_string(
                item, f"{where}.execution.payloads[{index}]", errors, allow_empty=True
            )
    instructions = execution["instructions"]
    if not isinstance(instructions, list) or not instructions:
        add_error(errors, f"{where}.execution.instructions must be a nonempty list")
    else:
        for index, item in enumerate(instructions):
            check_string(item, f"{where}.execution.instructions[{index}]", errors)
    check_string(
        execution["observed_result"], f"{where}.execution.observed_result", errors
    )


def validate_remediation(remediation: Any, where: str, errors: list[str]) -> None:
    if not check_exact_fields(
        remediation, REMEDIATION_FIELDS, f"{where}.remediation", errors
    ):
        return
    check_string(remediation["strategy"], f"{where}.remediation.strategy", errors)
    changes = remediation.get("code_changes")
    if changes is None:
        return
    if not isinstance(changes, list):
        add_error(errors, f"{where}.remediation.code_changes must be a list")
        return
    for index, change in enumerate(changes):
        item_where = f"{where}.remediation.code_changes[{index}]"
        if not check_exact_fields(change, CODE_CHANGE_FIELDS, item_where, errors):
            continue
        check_rel_path(change["file_name"], f"{item_where}.file_name", errors)
        check_string(
            change["fixed_code"], f"{item_where}.fixed_code", errors, allow_empty=True
        )


def validate_severity(severity: Any, where: str, errors: list[str]) -> None:
    if not check_exact_fields(severity, SEVERITY_FIELDS, f"{where}.severity", errors):
        return
    scores: dict[str, str] = {}
    for key in ("likelihood", "impact"):
        score_obj = severity.get(key)
        if not check_exact_fields(
            score_obj, SEVERITY_SCORE_FIELDS, f"{where}.severity.{key}", errors
        ):
            continue
        score = score_obj.get("score")
        if score not in SEVERITIES:
            add_error(errors, f"{where}.severity.{key}.score is invalid")
        else:
            scores[key] = score
        check_string(score_obj.get("reason"), f"{where}.severity.{key}.reason", errors)
    overall = severity.get("overall_severity")
    if overall not in SEVERITIES:
        add_error(errors, f"{where}.severity.overall_severity is invalid")
        return
    impact = scores.get("impact")
    if impact and SEVERITY_RANK[overall] > SEVERITY_RANK[impact]:
        add_error(errors, f"{where}.severity overall exceeds demonstrated impact")


def validate_confidence(confidence: Any, where: str, errors: list[str]) -> None:
    if not check_exact_fields(
        confidence, CONFIDENCE_FIELDS, f"{where}.confidence", errors
    ):
        return
    if confidence.get("score") not in CONFIDENCES:
        add_error(errors, f"{where}.confidence.score is invalid")
    check_string(confidence.get("reason"), f"{where}.confidence.reason", errors)


def validate_record(record: Any, where: str, errors: list[str]) -> None:
    if not isinstance(record, dict):
        add_error(errors, f"{where} must be an object")
        return
    verdict = record.get("verdict")
    expected = {
        "confirmed": CONFIRMED_FIELDS,
        "needs_validation": NEEDS_FIELDS,
        "rejected": REJECTED_FIELDS,
    }.get(verdict)
    if expected is None:
        add_error(errors, f"{where}.verdict is invalid")
        return
    if not check_exact_fields(record, expected, where, errors):
        return
    check_fingerprint(record["fingerprint"], f"{where}.fingerprint", errors)
    for key in ("title", "description"):
        check_string(record[key], f"{where}.{key}", errors)
    if "root_cause" in record:
        check_string(record["root_cause"], f"{where}.root_cause", errors)
    if "intended_behavior" in record:
        check_string(record["intended_behavior"], f"{where}.intended_behavior", errors)
    if "claimed_root_cause" in record:
        check_string(
            record["claimed_root_cause"], f"{where}.claimed_root_cause", errors
        )
    validate_trace(record["trace"], where, errors)
    validate_evidence(record["evidence"], where, errors)
    if verdict == "confirmed":
        validate_conditions(record["conditions"], where, errors)
        validate_execution(record["execution"], where, errors)
        validate_remediation(record["remediation"], where, errors)
        validate_severity(record["severity"], where, errors)
        validate_confidence(record["confidence"], where, errors)
    elif verdict == "needs_validation":
        blockers = record["blockers"]
        if not isinstance(blockers, list) or not blockers:
            add_error(errors, f"{where}.blockers must be a nonempty list")
        else:
            for index, blocker in enumerate(blockers):
                check_string(blocker, f"{where}.blockers[{index}]", errors)
        plan = record["validation_plan"]
        if not check_exact_fields(
            plan, PLAN_FIELDS, f"{where}.validation_plan", errors
        ):
            return
        if not any(
            isinstance(plan.get(key), str) and is_visible(plan[key])
            for key in ("local", "deployment")
        ):
            add_error(
                errors, f"{where}.validation_plan needs local or deployment detail"
            )
        for key in ("local", "deployment"):
            if plan.get(key) is None:
                continue
            check_string(plan[key], f"{where}.validation_plan.{key}", errors)
    else:
        check_string(record["reason"], f"{where}.reason", errors)


def validate_findings(
    records: Any, *, root: Path | None = None, check_paths_exist: bool = False
) -> list[str]:
    errors: list[str] = []
    if not isinstance(records, list):
        return ["findings.json must be a JSON array"]
    if len(records) > MAX_FINDINGS:
        add_error(errors, f"findings exceed {MAX_FINDINGS} records")
    if json_depth(records) > MAX_DEPTH:
        add_error(errors, f"findings exceed {MAX_DEPTH} nesting levels")
    fingerprints: list[str] = []
    for index, record in enumerate(records):
        where = f"findings[{index}]"
        validate_record(record, where, errors)
        if isinstance(record, dict) and isinstance(record.get("fingerprint"), str):
            fingerprints.append(record["fingerprint"])
        if check_paths_exist and root is not None and isinstance(record, dict):
            for key in ("trace", "evidence"):
                items = record.get(key)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and isinstance(item.get("file"), str):
                        if not (root / item["file"]).exists():
                            add_error(
                                errors,
                                f"{where}.{key} file does not exist: {item['file']}",
                            )
    if len(fingerprints) != len(set(fingerprints)):
        add_error(errors, "findings contain duplicate fingerprints")
    if fingerprints != sorted(fingerprints):
        add_error(errors, "findings must be sorted by fingerprint")
    return errors


def cross_validate(meta: Any, units: Any, records: Any) -> list[str]:
    errors: list[str] = []
    if (
        not isinstance(meta, dict)
        or not isinstance(units, list)
        or not isinstance(records, list)
    ):
        return errors
    if meta.get("run_status") == "complete" and not units:
        add_error(errors, "complete run has no coverage units")
    record_fingerprints = {
        record.get("fingerprint")
        for record in records
        if isinstance(record, dict) and isinstance(record.get("fingerprint"), str)
    }
    unit_fingerprints: set[str] = set()
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        fingerprints = unit.get("result_fingerprints")
        if isinstance(fingerprints, list):
            unit_fingerprints.update(
                item for item in fingerprints if isinstance(item, str)
            )
        if meta.get("run_status") == "complete":
            if unit.get("status") in {"planned", "in_progress"}:
                add_error(errors, f"complete run has a {unit.get('status')} unit")
            if unit.get("status") == "candidate":
                linked = unit.get("result_fingerprints")
                if not isinstance(linked, list) or not any(
                    item in record_fingerprints for item in linked
                ):
                    add_error(
                        errors,
                        f"complete run leaves unit {unit.get('coverage_id')!r} "
                        "as an unvalidated candidate",
                    )
    for fingerprint in sorted(record_fingerprints):
        if fingerprint not in unit_fingerprints:
            add_error(
                errors, f"finding {fingerprint!r} is not linked from a ledger unit"
            )
    if meta.get("run_status") == "complete":
        for fingerprint in sorted(unit_fingerprints - record_fingerprints):
            add_error(
                errors, f"complete run has no record for fingerprint {fingerprint!r}"
            )
    return errors


def validate_run(
    meta: Any,
    units: Any,
    records: Any,
    *,
    root: Path | None = None,
    check_paths_exist: bool = False,
) -> list[str]:
    errors = []
    errors.extend(validate_metadata(meta))
    errors.extend(
        validate_ledger(units, root=root, check_paths_exist=check_paths_exist)
    )
    errors.extend(
        validate_findings(records, root=root, check_paths_exist=check_paths_exist)
    )
    errors.extend(cross_validate(meta, units, records))
    return errors[:MAX_ERRORS]


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root()
    base = runs_root(root)
    base.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or next_run_id(base)
    if not RUN_ID_RE.fullmatch(run_id):
        raise SecurityAuditError("--run-id must be a safe lowercase directory name")
    run_dir = base / run_id
    if run_dir.exists():
        raise SecurityAuditError(f"run directory already exists: {run_dir}")
    target = Path(args.target).expanduser()
    target = (root / target).resolve() if not target.is_absolute() else target.resolve()
    if not target.is_dir():
        raise SecurityAuditError(f"target is not a directory: {target}")
    if not target.is_relative_to(root):
        raise SecurityAuditError("target must be inside this checkout")
    scopes: list[str] = []
    for scope in args.scope:
        candidate = Path(scope)
        resolved = (
            (root / candidate).resolve() if not candidate.is_absolute() else candidate
        )
        if not resolved.exists():
            raise SecurityAuditError(f"scope path does not exist: {scope}")
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise SecurityAuditError(
                f"scope path is outside the checkout: {scope}"
            ) from exc
        scopes.append(relative.as_posix())
    prior = sorted(
        path.name
        for path in base.glob("run-*")
        if path.is_dir() and path.name != run_id
    )
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "repo": "Xero-Team/AstrBot",
        "target": target.relative_to(root).as_posix() if target != root else ".",
        "source_ref": {
            "sha": run_git(root, "rev-parse", "HEAD"),
            "dirty": bool(run_git(root, "status", "--porcelain")),
        },
        "profile": args.profile,
        "scope_paths": scopes,
        "budget": args.budget,
        "execution_policy": EXECUTION_POLICY,
        "prior_runs": prior,
        "run_status": "in_progress",
        "created_at_utc": now_utc(),
    }
    (run_dir / "agents").mkdir(parents=True)
    (run_dir / "run-metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "coverage-ledger.json").write_text("[]\n", encoding="utf-8")
    (run_dir / "findings.json").write_text("[]\n", encoding="utf-8")
    (run_dir / "architecture.md").write_text(
        "<!-- Parent: replace this with the Phase 1 architecture summary. -->\n",
        encoding="utf-8",
    )
    (base / "LATEST").write_text(run_dir.name + "\n", encoding="utf-8")
    print(run_dir)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    meta = load_json(run_dir / "run-metadata.json")
    units = load_json(run_dir / "coverage-ledger.json")
    records = load_json(run_dir / "findings.json")
    if not isinstance(meta, dict):
        raise SecurityAuditError("run-metadata.json must be an object")
    print(f"run\t{meta.get('run_id')}\t{run_dir}")
    print(f"profile\t{meta.get('profile')}\tstatus={meta.get('run_status')}")
    source = meta.get("source_ref") if isinstance(meta.get("source_ref"), dict) else {}
    print(f"source\t{source.get('sha')}\tdirty={source.get('dirty')}")
    if isinstance(units, list):
        counts: dict[str, int] = {}
        for unit in units:
            if isinstance(unit, dict):
                key = str(unit.get("status"))
                counts[key] = counts.get(key, 0) + 1
        rendered = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
        print(f"units\t{len(units)}\t{rendered}")
    if isinstance(records, list):
        counts = {}
        for record in records:
            if isinstance(record, dict):
                key = str(record.get("verdict"))
                counts[key] = counts.get(key, 0) + 1
        rendered = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
        print(f"findings\t{len(records)}\t{rendered}")
    if meta.get("incomplete_reason"):
        print(f"incomplete_reason\t{meta['incomplete_reason']}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = repo_root()
    run_dir = resolve_run_dir(root, args.run_dir)
    meta = load_json(run_dir / "run-metadata.json")
    units = load_json(run_dir / "coverage-ledger.json")
    records = load_json(run_dir / "findings.json")
    errors = validate_run(
        meta, units, records, root=root, check_paths_exist=args.check_paths
    )
    if args.strict and isinstance(meta, dict) and meta.get("run_status") != "complete":
        errors.append("--strict requires run_status=complete")
    if errors:
        raise SecurityAuditError("\n".join(errors[:MAX_ERRORS]))
    unit_count = len(units) if isinstance(units, list) else 0
    record_count = len(records) if isinstance(records, list) else 0
    print(f"ok\tunits={unit_count}\tfindings={record_count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="explicit run directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a new security-audit run")
    init.add_argument("--profile", choices=PROFILES, default="standard")
    init.add_argument("--scope", nargs="*", default=[], help="in-scope paths")
    init.add_argument("--target", default=".", help="repository or subtree to audit")
    init.add_argument("--run-id")
    init.add_argument("--budget", type=int)
    init.set_defaults(func=cmd_init)

    status = sub.add_parser("status", help="summarize a run")
    status.set_defaults(func=cmd_status)

    validate = sub.add_parser("validate", help="validate a run")
    validate.add_argument(
        "--check-paths", action="store_true", help="require cited paths to exist"
    )
    validate.add_argument(
        "--strict", action="store_true", help="require run_status=complete"
    )
    validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SecurityAuditError as exc:
        print(f"security-audit: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
