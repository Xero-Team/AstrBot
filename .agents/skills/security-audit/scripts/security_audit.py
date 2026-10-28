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
import sys
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
ATTEMPT_STATUSES = ("blocked", "covered", "candidate")
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

REF_FIELDS = ("surface", "boundary", "subsystem", "attack_class")
CANONICAL_REF_FIELDS = frozenset({*REF_FIELDS, "lifecycle"})
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
ATTEMPT_REQUIRED = (*UNIT_REQUIRED, "wave", "reassignment_reason")
LEGACY_UNIT_FIELDS = ("selected_companion_blocks", "ordinary_attack_class_block")
CHECK_FIELDS = frozenset(
    {"agent_id", "reviewed_paths", "invariant", "method", "result", "artifact"}
)
SOURCE_REF_FIELDS = frozenset(
    {"sha", "dirty", "modified_paths", "modified_paths_omitted"}
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
EXCLUDED_BLOCK_FIELDS = frozenset({"block", "reason"})

FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
BLOCK_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+\.md#[A-Za-z0-9._-]+$")
WINDOWS_RESERVED_NAME_RE = re.compile(
    r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$",
    re.IGNORECASE,
)
WINDOWS_RESERVED_COMPONENT_RE = re.compile(
    r"^(?:con|prn|aux|nul|clock\$|conin\$|conout\$|com[1-9\u00b9\u00b2\u00b3]"
    r"|lpt[1-9\u00b9\u00b2\u00b3])(?:\.|$)",
    re.IGNORECASE,
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u2028\u2029]")

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNITS = 10_000
MAX_FINDINGS = 1_000
MAX_LIST_ITEMS = 256
MAX_ATTEMPTS = 64
MAX_MODIFIED_PATHS = 256
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


def run_git(root: Path, *arguments: str, strip: bool = True) -> str:
    try:
        output = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or "git command failed"
        raise SecurityAuditError(str(detail).strip()) from exc
    return output.strip() if strip else output


def runs_root(root: Path) -> Path:
    return root / ".tmp" / "security-audit"


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise SecurityAuditError(f"missing {path.name}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise SecurityAuditError(f"{path.name} exceeds {MAX_FILE_BYTES} bytes")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SecurityAuditError(f"{path.name}: invalid JSON") from exc
    if json_depth(value) > MAX_DEPTH:
        raise SecurityAuditError(f"{path.name} exceeds {MAX_DEPTH} nesting levels")
    return value


def json_depth(value: Any) -> int:
    """Return the nesting depth without recursing, so deep input cannot crash."""
    deepest = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict):
            children: Any = item.values()
        elif isinstance(item, list):
            children = item
        else:
            continue
        if depth > deepest:
            deepest = depth
        if deepest > MAX_DEPTH:
            return deepest
        stack.extend((child, depth + 1) for child in children)
    return deepest


def safe_run_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and RUN_ID_RE.fullmatch(value) is not None
        and WINDOWS_RESERVED_NAME_RE.fullmatch(value) is None
        and value.rstrip(". ") == value
    )


def resolve_run_dir(root: Path, explicit: str | None) -> Path:
    base = runs_root(root).resolve()
    if explicit:
        candidate = Path(explicit).expanduser()
        resolved = (
            candidate if candidate.is_absolute() else base / candidate
        ).resolve()
        if not resolved.is_relative_to(base):
            raise SecurityAuditError(
                "--run-dir must resolve inside .tmp/security-audit"
            )
        if not resolved.is_dir():
            raise SecurityAuditError(f"run directory does not exist: {resolved}")
        return resolved
    pointer = base / "LATEST"
    if pointer.is_file():
        name = pointer.read_text(encoding="utf-8").strip()
        if safe_run_name(name) and (base / name).is_dir():
            return (base / name).resolve()
    candidates = sorted(
        (path for path in base.glob("run-*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SecurityAuditError(
            "no security-audit run found under .tmp/security-audit"
        )
    return candidates[-1].resolve()


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


def path_problem(value: Any) -> str | None:
    """Explain why a value is not a safe repository-relative path, else None."""
    if not isinstance(value, str):
        return "must be a string"
    if not value.strip():
        return "must be a nonempty repository-relative path"
    if value != value.strip():
        return f"must not start or end with whitespace: {value!r}"
    if "\\" in value or ":" in value:
        return f"must be repository-relative, not a Windows path: {value!r}"
    if value.startswith(("/", "~")):
        return f"must be repository-relative: {value!r}"
    if CONTROL_RE.search(value):
        return f"must not contain control characters: {value!r}"
    for segment in value.split("/"):
        if segment in {"", ".", ".."}:
            return f"has an unsafe path segment: {value!r}"
        if segment.rstrip(". ") != segment:
            return f"has a segment with a trailing dot or space: {value!r}"
        if WINDOWS_RESERVED_COMPONENT_RE.match(segment):
            return f"has a Windows reserved device name: {value!r}"
    return None


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


def check_list_bound(value: list[Any], where: str, errors: list[str]) -> None:
    if len(value) > MAX_LIST_ITEMS:
        add_error(errors, f"{where} exceeds {MAX_LIST_ITEMS} entries")


def check_rel_path(value: Any, where: str, errors: list[str]) -> bool:
    problem = path_problem(value)
    if problem is not None:
        add_error(errors, f"{where} {problem}")
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
    check_list_bound(value, where, errors)
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
    if WINDOWS_RESERVED_NAME_RE.fullmatch(value):
        add_error(errors, f"{where} must not be a Windows reserved device name")
        return False
    return True


def check_fingerprint(value: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
        add_error(errors, f"{where} must match {FINGERPRINT_RE.pattern}")
        return False
    return True


def check_block_ref(value: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(value, str) or not BLOCK_REF_RE.fullmatch(value):
        add_error(errors, f"{where} must name a reference block as FILE.md#section")
        return False
    return True


def validate_source_ref(source_ref: Any, errors: list[str]) -> None:
    if not check_exact_fields(source_ref, SOURCE_REF_FIELDS, "source_ref", errors):
        return
    if not isinstance(source_ref["sha"], str) or not SHA_RE.fullmatch(
        source_ref["sha"]
    ):
        add_error(errors, "source_ref.sha must be a git object name")
    dirty = source_ref["dirty"]
    if not isinstance(dirty, bool):
        add_error(errors, "source_ref.dirty must be a boolean")
        dirty = None
    paths = source_ref["modified_paths"]
    recorded: list[str] | None = None
    if not isinstance(paths, list):
        add_error(errors, "source_ref.modified_paths must be a list")
    else:
        recorded = [item for item in paths if isinstance(item, str)]
        if len(paths) > MAX_MODIFIED_PATHS:
            add_error(
                errors, f"source_ref.modified_paths exceeds {MAX_MODIFIED_PATHS} paths"
            )
        for index, item in enumerate(paths):
            check_rel_path(item, f"source_ref.modified_paths[{index}]", errors)
        if recorded != sorted(recorded):
            add_error(errors, "source_ref.modified_paths must be sorted")
        if len(recorded) != len(set(recorded)):
            add_error(errors, "source_ref.modified_paths must not repeat a path")
    omitted = source_ref["modified_paths_omitted"]
    if not check_int(omitted, "source_ref.modified_paths_omitted", errors, minimum=0):
        omitted = None
    if recorded is not None and dirty is True and not recorded and not omitted:
        add_error(errors, "a dirty source_ref must record its modified paths")
    if dirty is False and (recorded or omitted):
        add_error(errors, "a clean source_ref must not record modified paths")


def validate_metadata(meta: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(meta, dict):
        return ["run-metadata.json must be an object"]
    if meta.get("schema_version") != SCHEMA_VERSION:
        add_error(errors, "run-metadata.json has unsupported schema_version")
    run_id = meta.get("run_id")
    if not isinstance(run_id, str) or not safe_run_name(run_id):
        add_error(errors, "run_id must match a safe run directory name")
    check_string(meta.get("repo"), "repo", errors)
    check_string(meta.get("target"), "target", errors)
    validate_source_ref(meta.get("source_ref"), errors)
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


def check_artifact_exists(
    artifacts: list[str], run_dir: Path | None, where: str, errors: list[str]
) -> None:
    if run_dir is None:
        return
    for artifact in artifacts:
        if not (run_dir / artifact).is_file():
            add_error(errors, f"{where} artifact does not exist: {artifact}")


def collect_artifacts(payload: Any) -> list[str]:
    artifacts: list[str] = []
    if not isinstance(payload, dict):
        return artifacts
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return artifacts
    for check in checks:
        if isinstance(check, dict) and isinstance(check.get("artifact"), str):
            artifacts.append(check["artifact"])
    return artifacts


def ref_signature(payload: Any) -> tuple[Any, ...] | None:
    if not isinstance(payload, dict):
        return None
    refs = payload.get("canonical_refs")
    if not isinstance(refs, dict):
        return None
    return tuple(refs.get(key) for key in (*REF_FIELDS, "lifecycle"))


def validate_refs_and_labels(
    payload: dict[str, Any], where: str, errors: list[str]
) -> None:
    """canonical_refs is the single source of truth; labels must copy it."""
    refs = payload.get("canonical_refs")
    if not isinstance(refs, dict):
        add_error(errors, f"{where}.canonical_refs must be an object")
        return
    unexpected = sorted(set(refs) - CANONICAL_REF_FIELDS)
    if unexpected:
        add_error(
            errors, f"{where}.canonical_refs has unexpected {', '.join(unexpected)}"
        )
    for field in REF_FIELDS:
        if field not in refs:
            add_error(errors, f"{where}.canonical_refs is missing {field}")
    for field in ("lifecycle",):
        if (field in refs) != (field in payload):
            add_error(
                errors,
                f"{where}.{field} and canonical_refs.{field} must appear together",
            )
    for field in CANONICAL_REF_FIELDS & set(refs):
        check_string(refs[field], f"{where}.canonical_refs.{field}", errors)
        if field not in payload:
            add_error(errors, f"{where}.{field} must copy canonical_refs.{field}")
        elif payload[field] != refs[field]:
            add_error(errors, f"{where}.{field} must equal canonical_refs.{field}")


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


def validate_evidence_state(
    unit: dict[str, Any], where: str, errors: list[str]
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
        check_list_bound(value, f"{where}.{key}", errors)

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

    if agent_id is None:
        add_error(errors, f"{where}.agent_id is required for {status}")
    else:
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


def validate_attempts(
    attempts: Any, unit: dict[str, Any], where: str, errors: list[str]
) -> None:
    """Archived attempts must be independent re-work, not recycled evidence."""
    if attempts is None:
        return
    if not isinstance(attempts, list):
        add_error(errors, f"{where}.attempts must be a list")
        return
    if len(attempts) > MAX_ATTEMPTS:
        add_error(errors, f"{where}.attempts exceeds {MAX_ATTEMPTS} entries")
    live_wave = unit.get("wave")
    live_owner = unit.get("agent_id")
    live_signature = ref_signature(unit)
    live_paths = unit.get("starting_paths")
    live_artifacts = collect_artifacts(unit)
    prior_owners: set[str] = set()
    prior_artifacts: set[str] = set()
    previous_wave = 0
    for index, attempt in enumerate(attempts):
        attempt_where = f"{where}.attempts[{index}]"
        if not isinstance(attempt, dict):
            add_error(errors, f"{attempt_where} must be an object")
            continue
        for key in ATTEMPT_REQUIRED:
            if key not in attempt:
                add_error(errors, f"{attempt_where} is missing {key}")
        if "attempts" in attempt:
            add_error(errors, f"{attempt_where} must not nest attempts")
        status = attempt.get("status")
        if status not in ATTEMPT_STATUSES:
            add_error(
                errors, f"{attempt_where}.status must be blocked, covered, or candidate"
            )
        wave = attempt.get("wave")
        if check_int(wave, f"{attempt_where}.wave", errors):
            if wave <= previous_wave:
                add_error(
                    errors,
                    f"{attempt_where}.wave must be strictly increasing across attempts",
                )
            if isinstance(live_wave, int) and wave >= live_wave:
                add_error(errors, f"{attempt_where}.wave must be below the live wave")
            previous_wave = max(previous_wave, wave)
        check_string(
            attempt.get("reassignment_reason"),
            f"{attempt_where}.reassignment_reason",
            errors,
        )
        owner = attempt.get("agent_id")
        if check_agent_id(owner, f"{attempt_where}.agent_id", errors):
            if owner in prior_owners:
                add_error(
                    errors, f"{attempt_where}.agent_id must be fresh for each attempt"
                )
        validate_refs_and_labels(attempt, attempt_where, errors)
        if live_signature is not None and ref_signature(attempt) != live_signature:
            add_error(
                errors, f"{attempt_where}.canonical_refs must match the live unit"
            )
        if isinstance(live_paths, list) and attempt.get("starting_paths") != live_paths:
            add_error(
                errors, f"{attempt_where}.starting_paths must match the live unit"
            )
        validate_evidence_state(attempt, attempt_where, errors)
        checks = attempt.get("checks")
        if isinstance(checks, list):
            for check_index, check in enumerate(checks):
                if not isinstance(check, dict):
                    continue
                check_owner = check.get("agent_id")
                if check_owner in prior_owners:
                    add_error(
                        errors,
                        f"{attempt_where}.checks[{check_index}].agent_id must keep "
                        "earlier evidence with its earlier attempt",
                    )
        for artifact in collect_artifacts(attempt):
            if artifact in prior_artifacts:
                add_error(
                    errors,
                    f"{attempt_where} reuses an earlier archived artifact: {artifact}",
                )
            elif artifact in live_artifacts:
                add_error(errors, f"{attempt_where} reuses a live artifact: {artifact}")
            prior_artifacts.add(artifact)
        if isinstance(owner, str):
            prior_owners.add(owner)
    if isinstance(live_owner, str) and live_owner in prior_owners:
        add_error(errors, f"{where}.agent_id must be fresh after a reassignment")
    live_checks = unit.get("checks")
    if isinstance(live_checks, list):
        for check_index, check in enumerate(live_checks):
            if not isinstance(check, dict):
                continue
            if check.get("agent_id") in prior_owners:
                add_error(
                    errors,
                    f"{where}.checks[{check_index}].agent_id must keep earlier "
                    "evidence with its archived attempt",
                )
    for artifact in live_artifacts:
        if artifact in prior_artifacts:
            add_error(errors, f"{where} reuses an archived artifact: {artifact}")


def validate_blocks(unit: dict[str, Any], where: str, errors: list[str]) -> None:
    excluded = unit.get("excluded_blocks")
    excluded_blocks: set[str] = set()
    if excluded is not None:
        if not isinstance(excluded, list):
            add_error(errors, f"{where}.excluded_blocks must be a list")
        else:
            check_list_bound(excluded, f"{where}.excluded_blocks", errors)
            for index, block in enumerate(excluded):
                block_where = f"{where}.excluded_blocks[{index}]"
                if not check_exact_fields(
                    block, EXCLUDED_BLOCK_FIELDS, block_where, errors
                ):
                    continue
                if check_block_ref(block["block"], f"{block_where}.block", errors):
                    if block["block"] in excluded_blocks:
                        add_error(errors, f"{block_where}.block is listed twice")
                    excluded_blocks.add(block["block"])
                check_string(block["reason"], f"{block_where}.reason", errors)
    selected = unit.get("selected_attack_class_blocks")
    if selected is not None:
        if not isinstance(selected, list):
            add_error(errors, f"{where}.selected_attack_class_blocks must be a list")
        else:
            check_list_bound(selected, f"{where}.selected_attack_class_blocks", errors)
            for index, block in enumerate(selected):
                block_where = f"{where}.selected_attack_class_blocks[{index}]"
                if not check_block_ref(block, block_where, errors):
                    continue
                if block in excluded_blocks:
                    add_error(errors, f"{block_where} is also excluded")
            if len(set(selected)) != len(selected):
                add_error(
                    errors, f"{where}.selected_attack_class_blocks repeats a block"
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
    validate_refs_and_labels(unit, where, errors)
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
    for legacy in LEGACY_UNIT_FIELDS:
        if legacy in unit:
            add_error(
                errors,
                f"{where}.{legacy} is not part of the ledger contract; "
                "use selected_attack_class_blocks",
            )
    validate_blocks(unit, where, errors)
    validate_evidence_state(unit, where, errors)
    validate_attempts(unit.get("attempts"), unit, where, errors)


def validate_ledger(
    units: Any,
    *,
    root: Path | None = None,
    run_dir: Path | None = None,
    check_paths_exist: bool = False,
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
        signature = ref_signature(unit)
        if signature is not None and all(
            isinstance(value, str) for value in signature[:4]
        ):
            key = tuple(str(value) for value in signature)
            if key in tuples:
                add_error(
                    errors, f"semantic tuple is represented twice: {coverage_id!r}"
                )
            tuples.add(key)
        if check_paths_exist and root is not None:
            for key in ("starting_paths", "reviewed_paths"):
                values = unit.get(key)
                if not isinstance(values, list):
                    continue
                for path in values:
                    if isinstance(path, str) and check_rel_path(path, where, errors):
                        if not (root / path).exists():
                            add_error(errors, f"{where}.{key} does not exist: {path}")
        if check_paths_exist and run_dir is not None:
            check_artifact_exists(
                collect_artifacts(unit), run_dir, f"{where}.checks", errors
            )
            attempts = unit.get("attempts")
            if isinstance(attempts, list):
                for attempt_index, attempt in enumerate(attempts):
                    check_artifact_exists(
                        collect_artifacts(attempt),
                        run_dir,
                        f"{where}.attempts[{attempt_index}].checks",
                        errors,
                    )
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
    run_dir: Path | None = None,
    check_paths_exist: bool = False,
) -> list[str]:
    errors = []
    errors.extend(validate_metadata(meta))
    errors.extend(
        validate_ledger(
            units,
            root=root,
            run_dir=run_dir,
            check_paths_exist=check_paths_exist,
        )
    )
    errors.extend(
        validate_findings(records, root=root, check_paths_exist=check_paths_exist)
    )
    errors.extend(cross_validate(meta, units, records))
    return errors[:MAX_ERRORS]


def collect_modified_paths(root: Path) -> tuple[list[str], int]:
    """Return sorted, safe worktree paths plus a count of unrecorded ones."""
    raw = run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        strip=False,
    )
    entries: list[str] = []
    tokens = raw.split("\x00")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        code = token[:2]
        if "R" in code or "C" in code:
            index += 1  # the rename or copy source follows and is not a live path
        entry = token[3:] if len(token) > 3 else ""
        if entry:
            entries.append(entry)
    kept: set[str] = set()
    for entry in entries:
        candidate = entry.replace("\\", "/")
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if path_problem(candidate) is None:
            kept.add(candidate)
    recorded = sorted(kept)[:MAX_MODIFIED_PATHS]
    return recorded, len(entries) - len(recorded)


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root()
    base = runs_root(root)
    base.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or next_run_id(base)
    if not safe_run_name(run_id):
        raise SecurityAuditError("--run-id must be a safe lowercase directory name")
    if args.budget is not None and args.budget < 1:
        raise SecurityAuditError("--budget must be a positive integer")
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
        candidate = Path(scope).expanduser()
        resolved = (
            candidate if candidate.is_absolute() else root / candidate
        ).resolve()
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
    modified, omitted = collect_modified_paths(root)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "repo": "Xero-Team/AstrBot",
        "target": target.relative_to(root).as_posix() if target != root else ".",
        "source_ref": {
            "sha": run_git(root, "rev-parse", "HEAD"),
            "dirty": bool(modified or omitted),
            "modified_paths": modified,
            "modified_paths_omitted": omitted,
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
    modified = source.get("modified_paths")
    if source.get("dirty") and isinstance(modified, list):
        print(
            "modified"
            f"\t{len(modified)} recorded"
            f"\tomitted={source.get('modified_paths_omitted')}"
        )
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
        meta,
        units,
        records,
        root=root,
        run_dir=run_dir,
        check_paths_exist=args.check_paths,
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
    parser.add_argument(
        "--run-dir",
        help="explicit run directory, absolute or relative to .tmp/security-audit",
    )
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
        "--check-paths",
        action="store_true",
        help="require cited paths and local artifacts to exist",
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
        print(f"security-audit: {exc}", file=sys.stderr)
        return 2
    except RecursionError:
        print("security-audit: input is nested too deeply", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
