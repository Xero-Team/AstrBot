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
        "source_ref": {
            "sha": "a" * 40,
            "dirty": False,
            "modified_paths": [],
            "modified_paths_omitted": 0,
        },
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


def _attempt(**overrides: object) -> dict:
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
        "agent_id": "hunter-b",
        "reviewed_paths": [PATH],
        "checks": [_check(agent_id="hunter-b")],
        "result_fingerprints": [],
        "unresolved": [],
        "wave": 1,
        "reassignment_reason": "reopened by the coverage critic",
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
        },
        surface="dashboard-ws",
        boundary="guest-to-account",
        subsystem="webchat",
    )
    errors = script.validate_run(_metadata(), [_unit(), second], [])
    assert any("duplicate coverage_id" in error for error in errors)


def test_duplicate_semantic_tuple_rejected():
    script = _load_script()
    second = _unit(coverage_id="web.auth.session-two")
    errors = script.validate_run(_metadata(), [_unit(), second], [])
    assert any("semantic tuple" in error for error in errors)


def test_labels_must_copy_canonical_refs():
    script = _load_script()
    errors = script.validate_run(_metadata(), [_unit(attack_class="xss")], [])
    assert any("must equal canonical_refs.attack_class" in error for error in errors)


def test_canonical_refs_reject_unknown_fields():
    script = _load_script()
    refs = dict(_unit()["canonical_refs"], lifecycle_mode="stale")
    errors = script.validate_run(_metadata(), [_unit(canonical_refs=refs)], [])
    assert any(
        "canonical_refs has unexpected lifecycle_mode" in error for error in errors
    )


def test_lifecycle_must_appear_on_the_unit_and_in_canonical_refs():
    script = _load_script()
    refs = dict(_unit()["canonical_refs"], lifecycle="revoked-token")
    errors = script.validate_run(_metadata(), [_unit(canonical_refs=refs)], [])
    assert any("must appear together" in error for error in errors)

    unit = _unit(canonical_refs=refs, lifecycle="revoked-token")
    assert script.validate_run(_metadata(), [unit], []) == []


def test_covered_unit_requires_owner_and_checks():
    script = _load_script()
    errors = script.validate_run(_metadata(), [_unit(agent_id=None, checks=[])], [])
    assert any("agent_id is required" in error for error in errors)
    assert any("checks must not be empty" in error for error in errors)


def test_in_progress_owner_must_be_a_canonical_agent_id():
    script = _load_script()
    unit = _unit(
        status="in_progress",
        agent_id="BAD",
        reviewed_paths=[],
        checks=[],
        result_fingerprints=[],
        unresolved=[],
    )
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("must be a lowercase canonical agent id" in error for error in errors)


def test_reserved_windows_device_names_are_rejected():
    script = _load_script()
    assert script.check_agent_id("con", "agent_id", []) is False
    errors = script.validate_run(
        _metadata(), [_unit(starting_paths=["con/keys.py"], reviewed_paths=[PATH])], []
    )
    assert any("Windows reserved device name" in error for error in errors)


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


@pytest.mark.parametrize(
    "path",
    [
        "C:foo/bar.py",
        "astrbot/foo:bar.py",
        "astrbot/dashboard/api/aux.py",
        "astrbot/com1/handler.py",
        "astrbot/dashboard/con.txt",
        "astrbot/dashboard/auth.py.",
        " astrbot/dashboard/auth.py",
        "astrbot/dashboard/... ",
        "astrbot\\\\dashboard\\\\auth.py",
    ],
)
def test_windows_and_ambiguous_paths_rejected(path):
    script = _load_script()
    errors: list[str] = []
    assert script.check_rel_path(path, "starting_paths[0]", errors) is False
    assert errors


def test_selected_attack_class_blocks_are_validated():
    script = _load_script()
    unit = _unit(selected_attack_class_blocks=["references/web-and-dashboard.md#csrf"])
    assert script.validate_run(_metadata(), [unit], []) == []

    bad = _unit(selected_attack_class_blocks=["ATTACK-CLASSES"])
    errors = script.validate_run(_metadata(), [bad], [])
    assert any("FILE.md#section" in error for error in errors)

    conflicting = _unit(
        selected_attack_class_blocks=["references/web-and-dashboard.md#csrf"],
        excluded_blocks=[
            {"block": "references/web-and-dashboard.md#csrf", "reason": "no route"}
        ],
    )
    errors = script.validate_run(_metadata(), [conflicting], [])
    assert any("is also excluded" in error for error in errors)


def test_legacy_block_fields_are_rejected():
    script = _load_script()
    unit = _unit(selected_companion_blocks=["WEB.md"])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("selected_attack_class_blocks" in error for error in errors)


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
    attempt = _attempt(wave=2)
    errors = script.validate_run(_metadata(), [_unit(wave=2, attempts=[attempt])], [])
    assert any("must be below the live wave" in error for error in errors)

    attempt = _attempt(wave=1)
    assert (
        script.validate_run(_metadata(), [_unit(wave=2, attempts=[attempt])], []) == []
    )


def test_attempt_waves_must_strictly_increase():
    script = _load_script()
    first = _attempt(wave=1, agent_id="hunter-b", checks=[_check(agent_id="hunter-b")])
    second = _attempt(wave=1, agent_id="hunter-c", checks=[_check(agent_id="hunter-c")])
    unit = _unit(wave=3, attempts=[first, second])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("strictly increasing" in error for error in errors)


def test_attempt_owner_must_be_fresh():
    script = _load_script()
    attempt = _attempt(agent_id="hunter-a", checks=[_check(agent_id="hunter-a")])
    unit = _unit(wave=2, attempts=[attempt])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("must be fresh after a reassignment" in error for error in errors)


def test_attempt_cannot_reuse_an_archived_artifact():
    script = _load_script()
    first = _attempt(
        wave=1,
        status="covered",
        agent_id="hunter-b",
        reviewed_paths=[PATH],
        checks=[
            _check(
                agent_id="hunter-b",
                method="local",
                artifact="agents/hunter-b/artifacts/out.txt",
            )
        ],
    )
    second = _attempt(
        wave=2,
        status="covered",
        agent_id="hunter-c",
        reviewed_paths=[PATH],
        checks=[
            _check(
                agent_id="hunter-c",
                method="local",
                artifact="agents/hunter-b/artifacts/out.txt",
            )
        ],
    )
    unit = _unit(wave=3, attempts=[first, second])
    errors = script.validate_run(_metadata(), [unit], [])
    assert any("reuses an earlier archived artifact" in error for error in errors)


def test_attempt_must_match_the_live_unit_refs_and_paths():
    script = _load_script()
    refs = dict(_attempt()["canonical_refs"], attack_class="ssrf")
    attempt = _attempt(wave=1, canonical_refs=refs, attack_class="ssrf")
    errors = script.validate_run(_metadata(), [_unit(wave=2, attempts=[attempt])], [])
    assert any("canonical_refs must match the live unit" in error for error in errors)

    attempt = _attempt(wave=1, starting_paths=["astrbot/dashboard/server.py"])
    errors = script.validate_run(_metadata(), [_unit(wave=2, attempts=[attempt])], [])
    assert any("starting_paths must match the live unit" in error for error in errors)


def test_bad_metadata_rejected():
    script = _load_script()
    errors = script.validate_run(
        _metadata(profile="exhaustive", execution_policy="any"), [_unit()], []
    )
    assert any("profile must be one of" in error for error in errors)
    assert any("execution_policy must be" in error for error in errors)


def test_dirty_source_ref_must_record_sorted_safe_paths():
    script = _load_script()
    ref = {
        "sha": "a" * 40,
        "dirty": True,
        "modified_paths": [],
        "modified_paths_omitted": 0,
    }
    errors = script.validate_run(_metadata(source_ref=ref), [_unit()], [])
    assert any("must record its modified paths" in error for error in errors)

    ref["modified_paths"] = ["astrbot/b.py", "astrbot/a.py"]
    errors = script.validate_run(_metadata(source_ref=ref), [_unit()], [])
    assert any("must be sorted" in error for error in errors)

    ref["modified_paths"] = ["astrbot/a.py", "C:/windows/system32/x.dll"]
    errors = script.validate_run(_metadata(source_ref=ref), [_unit()], [])
    assert any("must be repository-relative" in error for error in errors)

    ref["modified_paths"] = ["astrbot/a.py"]
    assert script.validate_run(_metadata(source_ref=ref), [_unit()], []) == []


def test_clean_source_ref_cannot_record_modified_paths():
    script = _load_script()
    ref = {
        "sha": "a" * 40,
        "dirty": False,
        "modified_paths": ["astrbot/a.py"],
        "modified_paths_omitted": 0,
    }
    errors = script.validate_run(_metadata(source_ref=ref), [_unit()], [])
    assert any("clean source_ref" in error for error in errors)


def test_check_paths_flag_rejects_missing_files(tmp_path):
    script = _load_script()
    unit = _unit(starting_paths=["astrbot/does-not-exist.py"])
    errors = script.validate_ledger([unit], root=tmp_path, check_paths_exist=True)
    assert any("does not exist" in error for error in errors)


def test_check_paths_flag_rejects_missing_artifacts(tmp_path):
    script = _load_script()
    unit = _unit(
        checks=[
            _check(
                method="local",
                artifact="agents/hunter-a/artifacts/out.txt",
            )
        ]
    )
    errors = script.validate_ledger([unit], run_dir=tmp_path, check_paths_exist=True)
    assert any("artifact does not exist" in error for error in errors)

    artifact = tmp_path / "agents" / "hunter-a" / "artifacts" / "out.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("evidence", encoding="utf-8")
    assert (
        script.validate_ledger([unit], run_dir=tmp_path, check_paths_exist=True) == []
    )


def test_deep_json_is_rejected_without_recursing():
    script = _load_script()
    deep: list = []
    node = deep
    for _ in range(500):
        child: list = []
        node.append(child)
        node = child
    assert script.json_depth(deep) > script.MAX_DEPTH
    unit = _unit()
    unit["notes_of_extra_depth"] = deep
    errors = script.validate_ledger([unit])
    assert any("nesting levels" in error for error in errors)


def test_load_json_rejects_missing_and_invalid_files(tmp_path):
    script = _load_script()
    with pytest.raises(script.SecurityAuditError, match="missing"):
        script.load_json(tmp_path / "absent.json")

    path = tmp_path / "coverage-ledger.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(script.SecurityAuditError, match="invalid JSON"):
        script.load_json(path)

    path.write_text("[" * 5000 + "]" * 5000, encoding="utf-8")
    with pytest.raises(script.SecurityAuditError, match="nesting levels"):
        script.load_json(path)


def test_cli_init_status_validate(tmp_path, monkeypatch, capsys):
    script = _load_script()
    monkeypatch.setattr(script, "repo_root", lambda: tmp_path)

    status = (
        " M astrbot/dashboard/api/auth.py\x00"
        "R  astrbot/new_name.py\x00astrbot/old_name.py\x00"
        "?? con\x00"
    )

    def fake_git(root, *arguments, strip=True):
        if arguments and arguments[0] == "rev-parse":
            return "a" * 40
        if arguments and arguments[0] == "status":
            return status
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
    assert metadata["source_ref"]["dirty"] is True
    assert metadata["source_ref"]["modified_paths"] == [
        "astrbot/dashboard/api/auth.py",
        "astrbot/new_name.py",
    ]
    assert metadata["source_ref"]["modified_paths_omitted"] == 1

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
    monkeypatch.setattr(script, "run_git", lambda root, *arguments, **kwargs: "a" * 40)
    outside = tmp_path.parent / "outside-scope"
    outside.mkdir(exist_ok=True)
    assert script.main(["init", "--scope", str(outside)]) == 2
    assert not (tmp_path / ".tmp" / "security-audit" / "run-1").exists()


def test_cli_rejects_non_positive_budget(tmp_path, monkeypatch):
    script = _load_script()
    monkeypatch.setattr(script, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(script, "run_git", lambda root, *arguments, **kwargs: "a" * 40)
    assert script.main(["init", "--budget", "0"]) == 2
    assert script.main(["init", "--budget", "-5"]) == 2
    assert not (tmp_path / ".tmp" / "security-audit" / "run-1").exists()
    assert script.main(["init", "--budget", "4"]) == 0


def test_run_dir_must_stay_inside_the_runs_root(tmp_path, monkeypatch):
    script = _load_script()
    monkeypatch.setattr(script, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(script, "run_git", lambda root, *arguments, **kwargs: "a" * 40)
    outside = tmp_path.parent / "outside-run"
    (outside / "run-metadata.json").parent.mkdir(parents=True, exist_ok=True)
    assert script.main(["--run-dir", str(outside), "status"]) == 2

    run_dir = tmp_path / ".tmp" / "security-audit" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run-metadata.json").write_text('{"run_id": "run-1"}', encoding="utf-8")
    (run_dir / "coverage-ledger.json").write_text("[]", encoding="utf-8")
    (run_dir / "findings.json").write_text("[]", encoding="utf-8")
    assert script.main(["--run-dir", "run-1", "status"]) == 0


def test_latest_pointer_must_name_a_safe_run(tmp_path, monkeypatch):
    script = _load_script()
    base = tmp_path / ".tmp" / "security-audit"
    (base / "run-1").mkdir(parents=True)
    (base / "LATEST").write_text("../escape\n", encoding="utf-8")
    assert script.resolve_run_dir(tmp_path, None) == (base / "run-1").resolve()
