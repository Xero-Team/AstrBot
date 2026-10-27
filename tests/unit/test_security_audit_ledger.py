import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / "security-audit"
    / "scripts"
    / "security_audit.py"
)

PATH = "astrbot/dashboard/api/auth.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("security_audit", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Failed to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metadata(**overrides: object) -> dict:
    payload: dict = {
        "schema_version": 1,
        "run_id": "run-1",
        "repo": "Xero-Team/AstrBot",
        "target": ".",
        "source_ref": {"sha": "a" * 40, "dirty": False},
        "profile": "standard",
        "scope_paths": [],
        "budget": None,
        "execution_policy": "sandboxed-source-and-local-only",
        "prior_runs": [],
        "run_status": "in_progress",
        "created_at_utc": "2026-10-27T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _check(**overrides: object) -> dict:
    payload: dict = {
        "agent_id": "hunter-a",
        "reviewed_paths": [PATH],
        "invariant": "the route requires a verified session",
        "method": "source",
        "result": "anonymous requests are rejected before dispatch",
        "artifact": None,
    }
    payload.update(overrides)
    return payload


def _unit(**overrides: object) -> dict:
    payload: dict = {
        "coverage_id": "web.auth.session",
        "canonical_refs": {
            "surface": "dashboard-http",
            "boundary": "anonymous-to-account",
            "subsystem": "auth",
            "attack_class": "session-forgery",
        },
        "surface": "dashboard-http",
        "boundary": "anonymous-to-account",
        "subsystem": "auth",
        "attack_class": "session-forgery",
        "starting_paths": [PATH],
        "status": "covered",
        "agent_id": "hunter-a",
        "reviewed_paths": [PATH],
        "checks": [_check()],
        "result_fingerprints": [],
        "unresolved": [],
    }
    payload.update(overrides)
    return payload


def _trace() -> list[dict]:
    return [
        {
            "kind": "entrypoint",
            "file": PATH,
            "line": 10,
            "scope": "http-request",
            "description": "route accepts an anonymous request",
        },
        {
            "kind": "sink",
            "file": PATH,
            "line": 20,
            "scope": "account",
            "description": "handler acts on the account",
        },
    ]


def _evidence() -> list[dict]:
    return [{"file": PATH, "line": 10, "description": "the dependency is optional"}]


def _confirmed(fingerprint: str = "AUD-1", **overrides: object) -> dict:
    payload: dict = {
        "verdict": "confirmed",
        "fingerprint": fingerprint,
        "title": "anonymous handler reaches an account action",
        "description": "the route skips its session dependency",
        "root_cause": "the handler takes an optional principal",
        "intended_behavior": "every account action requires a session",
        "trace": _trace(),
        "evidence": _evidence(),
        "conditions": [
            {"kind": "authentication_level", "description": "unauthenticated caller"}
        ],
        "execution": {
            "attacker_perspective": "anonymous network caller",
            "payloads": ["GET /api/v1/account"],
            "instructions": ["send an unauthenticated request"],
            "observed_result": "the handler returns account state",
        },
        "remediation": {
            "strategy": "require the session dependency",
            "code_changes": [],
        },
        "severity": {
            "likelihood": {"score": "high", "reason": "no precondition"},
            "impact": {"score": "high", "reason": "account state readable"},
            "overall_severity": "high",
        },
        "confidence": {"score": "high", "reason": "local request observed"},
    }
    payload.update(overrides)
    return payload


def _needs_validation(fingerprint: str = "AUD-2", **overrides: object) -> dict:
    payload: dict = {
        "verdict": "needs_validation",
        "fingerprint": fingerprint,
        "title": "proxy trust may widen the rate-limit key",
        "description": "the flag is deployment-owned",
        "claimed_root_cause": "client IP is derived from a forwarded header",
        "trace": _trace(),
        "evidence": _evidence(),
        "blockers": ["the deployed proxy configuration is not in the repository"],
        "validation_plan": {
            "local": "send two spoofed X-Forwarded-For values to the limiter",
            "deployment": None,
        },
    }
    payload.update(overrides)
    return payload


def _rejected(fingerprint: str = "AUD-3", **overrides: object) -> dict:
    payload: dict = {
        "verdict": "rejected",
        "fingerprint": fingerprint,
        "title": "template escaping is not a sink",
        "description": "the value never reaches v-html",
        "claimed_root_cause": "user text is rendered",
        "trace": _trace(),
        "evidence": _evidence(),
        "reason": "the renderer escapes the value",
    }
    payload.update(overrides)
    return payload


def _candidate_unit(fingerprint: str, **overrides: object) -> dict:
    payload = _unit(
        status="candidate",
        result_fingerprints=[fingerprint],
        unresolved=[f"{fingerprint} awaits independent validation"],
        **overrides,
    )
    payload.update(overrides)
    return payload


def test_valid_run_has_no_errors():
    script = _load_script()
    assert script.validate_run(_metadata(), [_unit()], []) == []


def test_planned_unit_is_unowned_and_empty():
    script = _load_script()
    unit = _unit(
        status="planned",
        agent_id=None,
        reviewed_paths=[],
        checks=[],
        result_fingerprints=[],
        unresolved=[],
    )
    assert script.validate_run(_metadata(), [unit], []) == []


def test_duplicate_coverage_ids_rejected():
    script = _load_script()
    second = _unit(
        canonical_refs={
            "surface": "dashboard-ws",
            "boundary": "guest-to-account",
            "subsystem": "webchat",
            "attack_class": "session-forgery",
        }
    )
    errors = script.validate_run(_metadata(), [_unit(), second], [])
    assert any("duplicate coverage_id" in error for error in errors)


def test_duplicate_semantic_tuple_rejected():
    script = _load_script()
    second = _unit(coverage_id="web.auth.session-two")
    errors = script.validate_run(_metadata(), [_unit(), second], [])
    assert any("semantic tuple" in error for error in errors)


def test_covered_unit_requires_owner_and_checks():
    script = _load_script()
    errors = script.validate_run(_metadata(), [_unit(agent_id=None, checks=[])], [])
    assert any("agent_id is required" in error for error in errors)
    assert any("checks must not be empty" in error for error in errors)


def test_reviewed_paths_must_equal_check_union():
    script = _load_script()
    unit = _unit(reviewed_paths=["astrbot/dashboard/server.py"])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("union of check paths" in error for error in errors)


def test_local_check_artifact_is_confined_to_owner():
    script = _load_script()
    unit = _unit(
        checks=[
            _check(
                method="local",
                artifact="agents/other-hunter/artifacts/output.txt",
            )
        ]
    )
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("must be under agents/hunter-a/artifacts/" in error for error in errors)


def test_source_check_rejects_artifact():
    script = _load_script()
    unit = _unit(checks=[_check(artifact="agents/hunter-a/artifacts/output.txt")])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("must be null for source checks" in error for error in errors)


def test_in_progress_unit_must_be_empty():
    script = _load_script()
    unit = _unit(status="in_progress")
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("must be empty while in_progress" in error for error in errors)


def test_terminal_statuses_need_a_reason():
    script = _load_script()
    unit = _unit(
        status="deferred",
        agent_id=None,
        reviewed_paths=[],
        checks=[],
        result_fingerprints=[],
        unresolved=[],
    )
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("needs a reason" in error for error in errors)


def test_absolute_and_parent_paths_rejected():
    script = _load_script()
    errors = script.validate_run(
        _metadata(),
        [_unit(starting_paths=["/etc/passwd"], reviewed_paths=[PATH])],
        [],
    )
    assert any("repository-relative" in error for error in errors)

    script = _load_script()
    errors = script.validate_run(
        _metadata(),
        [_unit(starting_paths=[f"astrbot/../{PATH}"], reviewed_paths=[PATH])],
        [],
    )
    assert any("unsafe path segment" in error for error in errors)


def test_needs_validation_carries_no_severity():
    script = _load_script()
    record = _needs_validation()
    assert script.validate_findings([record]) == []

    record["severity"] = _confirmed()["severity"]
    errors = script.validate_findings([record])
    assert any("unexpected severity" in error for error in errors)


def test_confirmed_requires_execution_and_remediation():
    script = _load_script()
    record = _confirmed()
    del record["execution"]
    del record["remediation"]
    errors = script.validate_findings([record])
    assert any("missing execution, remediation" in error for error in errors)


def test_overall_severity_cannot_exceed_impact():
    script = _load_script()
    record = _confirmed()
    record["severity"]["impact"] = {"score": "low", "reason": "narrow read"}
    errors = script.validate_findings([record])
    assert any("overall exceeds demonstrated impact" in error for error in errors)


def test_rejected_has_no_blockers_or_severity():
    script = _load_script()
    assert script.validate_findings([_rejected()]) == []

    record = _rejected()
    record["blockers"] = ["unknown"]
    errors = script.validate_findings([record])
    assert any("unexpected blockers" in error for error in errors)


def test_trace_must_start_at_entrypoint_and_end_at_sink():
    script = _load_script()
    record = _confirmed()
    record["trace"] = [
        {
            "kind": "propagation",
            "file": PATH,
            "line": 10,
            "scope": "http-request",
            "description": "route",
        },
        {
            "kind": "sink",
            "file": PATH,
            "line": 20,
            "scope": "account",
            "description": "handler",
        },
    ]
    errors = script.validate_findings([record])
    assert any("must start at entrypoint" in error for error in errors)


def test_single_step_trace_must_be_entrypoint_or_sink():
    script = _load_script()
    record = _confirmed()
    record["trace"] = [
        {
            "kind": "propagation",
            "file": PATH,
            "line": 10,
            "scope": "http-request",
            "description": "route",
        }
    ]
    errors = script.validate_findings([record])
    assert any("one step that is not entrypoint or sink" in error for error in errors)


def test_findings_must_be_sorted_by_fingerprint():
    script = _load_script()
    errors = script.validate_findings([_confirmed("B-2"), _confirmed("A-1")])
    assert any("sorted by fingerprint" in error for error in errors)


def test_duplicate_fingerprints_rejected():
    script = _load_script()
    errors = script.validate_findings([_confirmed("A-1"), _confirmed("A-1")])
    assert any("duplicate fingerprints" in error for error in errors)


def test_confirmed_record_must_be_linked_from_a_unit():
    script = _load_script()
    errors = script.validate_run(_metadata(), [_unit()], [_confirmed()])
    assert any("is not linked from a ledger unit" in error for error in errors)


def test_complete_run_cannot_leave_planned_units():
    script = _load_script()
    unit = _unit(
        status="planned",
        agent_id=None,
        reviewed_paths=[],
        checks=[],
        result_fingerprints=[],
        unresolved=[],
    )
    errors = script.validate_run(_metadata(run_status="complete"), [unit], [])
    assert any("complete run has a planned unit" in error for error in errors)


def test_complete_run_requires_coverage_units():
    script = _load_script()
    errors = script.validate_run(_metadata(run_status="complete"), [], [])
    assert any("no coverage units" in error for error in errors)


def test_complete_run_candidate_needs_a_record():
    script = _load_script()
    errors = script.validate_run(
        _metadata(run_status="complete"), [_candidate_unit("AUD-9")], []
    )
    assert any("unvalidated candidate" in error for error in errors)


def test_complete_run_with_validated_candidate_is_clean():
    script = _load_script()
    unit = _candidate_unit("AUD-1")
    errors = script.validate_run(
        _metadata(run_status="complete"), [unit], [_confirmed("AUD-1")]
    )
    assert errors == []


def test_incomplete_run_requires_a_reason():
    script = _load_script()
    errors = script.validate_run(_metadata(run_status="incomplete"), [_unit()], [])
    assert any("incomplete_reason" in error for error in errors)


def test_candidate_may_omit_reason_but_blocked_may_not():
    script = _load_script()
    unit = _unit(status="candidate", result_fingerprints=["AUD-1"], unresolved=[])
    assert script.validate_run(_metadata(), [unit], [_confirmed("AUD-1")]) == []

    blocked = _unit(status="blocked", result_fingerprints=[], unresolved=[])
    errors = script.validate_run(_metadata(), [blocked], [])
    assert any("must not be empty for blocked" in error for error in errors)


def test_attempt_wave_must_trail_the_live_wave():
    script = _load_script()
    attempt = _unit(
        status="covered",
        wave=2,
        reassignment_reason="reopened by the coverage critic",
    )
    unit = _unit(wave=2, attempts=[attempt])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("must be below the live wave" in error for error in errors)

    attempt["wave"] = 1
    script = _load_script()
    assert (
        script.validate_run(_metadata(), [_unit(wave=2, attempts=[attempt])], []) == []
    )


def test_bad_metadata_rejected():
    script = _load_script()
    errors = script.validate_run(
        _metadata(profile="exhaustive", execution_policy="any"), [_unit()], []
    )
    assert any("profile must be one of" in error for error in errors)
    assert any("execution_policy must be" in error for error in errors)


def test_check_paths_flag_rejects_missing_files(tmp_path):
    script = _load_script()
    unit = _unit(starting_paths=["astrbot/does-not-exist.py"])
    errors = script.validate_ledger([unit], root=tmp_path, check_paths_exist=True)
    assert any("does not exist" in error for error in errors)


def test_load_json_rejects_missing_and_invalid_files(tmp_path):
    script = _load_script()
    with pytest.raises(script.SecurityAuditError, match="missing"):
        script.load_json(tmp_path / "absent.json")

    path = tmp_path / "coverage-ledger.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(script.SecurityAuditError, match="invalid JSON"):
        script.load_json(path)


def test_cli_init_status_validate(tmp_path, monkeypatch, capsys):
    script = _load_script()
    monkeypatch.setattr(script, "repo_root", lambda: tmp_path)

    def fake_git(root, *arguments):
        if arguments and arguments[0] == "rev-parse":
            return "a" * 40
        return ""

    monkeypatch.setattr(script, "run_git", fake_git)
    scope = tmp_path / "astrbot" / "dashboard" / "api"
    scope.mkdir(parents=True)

    assert script.main(["init", "--profile", "quick", "--scope", str(scope)]) == 0
    run_dir = tmp_path / ".tmp" / "security-audit" / "run-1"
    assert run_dir.is_dir()
    assert (run_dir / "coverage-ledger.json").read_text().strip() == "[]"
    assert (run_dir / "findings.json").read_text().strip() == "[]"
    assert (run_dir / "agents").is_dir()
    metadata = script.load_json(run_dir / "run-metadata.json")
    assert metadata["profile"] == "quick"
    assert metadata["scope_paths"] == ["astrbot/dashboard/api"]
    assert metadata["source_ref"]["sha"] == "a" * 40

    capsys.readouterr()
    assert script.main(["status"]) == 0
    assert "run-1" in capsys.readouterr().out

    assert script.main(["validate"]) == 0
    assert script.main(["validate", "--strict"]) == 2

    assert script.main(["init", "--run-id", "run-1"]) == 2
    assert script.main(["init"]) == 0
    assert (tmp_path / ".tmp" / "security-audit" / "run-2").is_dir()
    pointer = tmp_path / ".tmp" / "security-audit" / "LATEST"
    assert pointer.read_text().strip() == "run-2"


def test_cli_rejects_scope_outside_checkout(tmp_path, monkeypatch):
    script = _load_script()
    monkeypatch.setattr(script, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(script, "run_git", lambda root, *arguments: "a" * 40)
    outside = tmp_path.parent / "outside-scope"
    outside.mkdir(exist_ok=True)
    assert script.main(["init", "--scope", str(outside)]) == 2
    assert not (tmp_path / ".tmp" / "security-audit" / "run-1").exists()
