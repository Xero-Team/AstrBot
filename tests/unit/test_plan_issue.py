import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / "plan-issue"
    / "scripts"
    / "issue_plan.py"
)

VALID_PLAN = """# Wake check Implementation Plan

**Goal:** record selected wake reasons on the event
**Issue:** https://github.com/Xero-Team/AstrBot/issues/1
**SHA:** abcdef0123456789
**Architecture:** Keep WakingCheckStage as the owner.
**Recommended approach:** extend the existing stage

## Goal

Record `wake_reasons` without restoring `group_wake_policy`.

## Architecture

Change only the waking-check stage and its unit tests.

## Constraints

- Python >=3.14
- No legacy shims
- In-app docs at `/help/`

## Current behavior

`WakingCheckStage` in `astrbot/core/pipeline/waking_check/stage.py:1` decides
wake without recording reasons.

## Desired behavior

The event stores the selected reasons. Mention-only group messages stay
asleep unless `llm_access.group` allows them.

## Out of scope

Dashboard copy. Provider changes.

## Tasks

### Task 1: Record wake reasons

**Files:**
- Modify: `astrbot/core/pipeline/waking_check/stage.py` (`WakingCheckStage`)
- Test: `tests/unit/test_waking_check.py`

**Acceptance:**
- [ ] `event.wake_reasons` is set on a woken group mention

**Verify:**

```bash
uv run pytest tests/unit/test_waking_check.py::test_records_reasons
```

Expected: PASS

## Verification

```bash
uv run pytest tests/unit/test_waking_check.py
```
"""


def _load():
    spec = importlib.util.spec_from_file_location("issue_plan", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Failed to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_plan_accepts_complete_document():
    module = _load()
    assert module.validate_plan(VALID_PLAN) == []


def test_validate_plan_requires_task_and_headings():
    module = _load()
    errors = module.validate_plan("# Title\n\n## Goal\n\nhello\n")
    assert "missing heading: Architecture" in errors
    assert "missing ### Task section" in errors


def test_validate_plan_requires_current_behavior_evidence():
    module = _load()
    uncited = VALID_PLAN.replace(
        "astrbot/core/pipeline/waking_check/stage.py:1",
        "astrbot/core/pipeline/waking_check/stage.py",
    )
    # A citation in another section does not support the current behavior claim.
    uncited += "\nUnrelated reference: `AGENTS.md:1`\n"
    assert "Current behavior missing `path:line` evidence" in module.validate_plan(
        uncited
    )


@pytest.mark.parametrize("comment", ["# Verify", "## Run tests", "### Task 9: example"])
def test_validate_plan_preserves_shell_comments_in_commands(comment: str):
    module = _load()
    commented = VALID_PLAN.replace(
        "uv run pytest tests/unit/test_waking_check.py::test_records_reasons",
        f"{comment}\nuv run pytest tests/unit/test_waking_check.py::test_records_reasons",
    )
    assert module.validate_plan(commented) == []
    assert module.validate_task_graph(commented) == []


def test_validate_plan_requires_files_verify_and_command():
    module = _load()
    plan = VALID_PLAN.replace("**Files:**\n", "Notes:\n").replace(
        "**Verify:**\n", "Done:\n"
    )
    errors = module.validate_plan(plan)
    assert any(item.endswith("missing Files") for item in errors)
    assert any(item.endswith("missing Verify") for item in errors)


def test_validate_plan_rejects_placeholder_and_forbidden_artifacts():
    module = _load()
    with_placeholder = VALID_PLAN.replace(
        "Dashboard copy. Provider changes.",
        "TODO add the rest later",
    )
    assert "placeholder text is not allowed" in module.validate_plan(with_placeholder)
    with_docs = VALID_PLAN.replace(
        "In-app docs at `/help/`",
        "See https://docs.astrbot.app/guide",
    )
    assert any(
        item.startswith("forbidden artifact:")
        for item in module.validate_plan(with_docs)
    )
    with_floor = VALID_PLAN.replace("Python >=3.14", "Python >=3.12")
    assert any(
        item.startswith("forbidden artifact:")
        for item in module.validate_plan(with_floor)
    )


def test_run_id_for_issue_or_slug():
    module = _load()
    assert module.run_id_for(issue=12, slug=None) == "issue-12"
    assert module.run_id_for(issue=None, slug="wake-reasons") == "local-wake-reasons"
    with pytest.raises(module.PlanError, match="either"):
        module.run_id_for(issue=1, slug="x")
    with pytest.raises(module.PlanError, match="kebab-case"):
        module.run_id_for(issue=None, slug="Wake_Reasons")


def test_init_writes_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load()
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        module,
        "run_git",
        lambda _root, *arguments: (
            "abc123" if arguments[:2] == ("rev-parse", "HEAD") else "plan-issue"
        ),
    )
    monkeypatch.setattr(module, "now_utc", lambda: "2026-09-05T00:00:00Z")
    args = Namespace(issue=9, slug=None, force=False)
    assert module.cmd_init(args) == 0
    run_dir = tmp_path / ".tmp" / "issue-plan" / "issue-9"
    manifest = (run_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"run_id": "issue-9"' in manifest
    assert '"sha": "abc123"' in manifest
    assert '"status": "planning"' in manifest
    pointer = (tmp_path / ".tmp" / "issue-plan" / "LATEST").read_text(encoding="utf-8")
    assert pointer.strip() == "issue-9"
    with pytest.raises(module.PlanError, match="already exists"):
        module.cmd_init(args)
    args.force = True
    assert module.cmd_init(args) == 0
    manifest = (run_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"probe"' not in manifest


def test_validate_task_graph_detects_cycle_and_unknown():
    module = _load()
    cyclic = VALID_PLAN.replace(
        "### Task 1: Record wake reasons\n",
        "### Task 1: Record wake reasons\n\n**Blocked by:** Task 1\n",
    )
    assert any("itself" in item for item in module.validate_task_graph(cyclic))
    unknown = VALID_PLAN.replace(
        "### Task 1: Record wake reasons\n",
        "### Task 1: Record wake reasons\n\n**Blocked by:** Task 9\n",
    )
    assert any("unknown Task 9" in item for item in module.validate_task_graph(unknown))


def test_validate_modify_paths_and_sha_match(tmp_path: Path):
    module = _load()
    missing = tmp_path / "checkout"
    missing.mkdir()
    errors = module.validate_modify_paths(VALID_PLAN, missing)
    assert any(item.startswith("Modify path missing:") for item in errors)
    present = tmp_path / "real"
    target = present / "astrbot" / "core" / "pipeline" / "waking_check"
    target.mkdir(parents=True)
    (target / "stage.py").write_text("class WakingCheckStage:\n    pass\n")
    assert module.validate_modify_paths(VALID_PLAN, present) == []
    assert module.validate_sha_match(VALID_PLAN, "abcdef0123456789") == []
    assert any(
        "does not match" in item
        for item in module.validate_sha_match(VALID_PLAN, "deadbeef")
    )


def test_fetch_refuses_upstream_url():
    module = _load()
    args = Namespace(
        url="https://github.com/AstrBotDevs/AstrBot/issues/1",
        allow_upstream=False,
        issue=1,
        run_dir=None,
    )
    with pytest.raises(module.PlanError, match="AstrBotDevs"):
        module.cmd_fetch(args)


def test_validate_workspace_needs_only_a_concrete_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(module, "run_git", lambda *_args: "abcdef0123456789")
    assert module.main(["init", "--slug", "bounded-change"]) == 0
    run_dir = tmp_path / ".tmp" / "issue-plan" / "local-bounded-change"
    (run_dir / "PLAN.md").write_text(VALID_PLAN, encoding="utf-8")

    assert module.main(["validate"]) == 0
    assert module.main(["status"]) == 0
    assert {path.name for path in run_dir.iterdir()} == {"manifest.json", "PLAN.md"}
    assert "probe" not in json.loads((run_dir / "manifest.json").read_text())


@pytest.mark.parametrize(
    ("before", "after", "error"),
    [
        ("**Acceptance:**", "Notes:", "missing Acceptance"),
        (
            "- [ ] `event.wake_reasons` is set on a woken group mention",
            "",
            "Acceptance is empty",
        ),
        (
            "uv run pytest tests/unit/test_waking_check.py::test_records_reasons",
            "# choose a command",
            "Verify has no command",
        ),
    ],
)
def test_validate_rejects_tasks_without_observable_verification(
    before: str, after: str, error: str
):
    module = _load()
    errors = module.validate_plan(VALID_PLAN.replace(before, after))
    assert any(error in item for item in errors)


def test_workspace_validation_preserves_path_and_sha_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    module = _load()
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(module, "run_git", lambda *_args: "deadbeef")
    (tmp_path / "AGENTS.md").touch()
    (tmp_path / "pyproject.toml").touch()
    assert module.main(["init", "--slug", "stale-plan"]) == 0
    run_dir = tmp_path / ".tmp" / "issue-plan" / "local-stale-plan"
    (run_dir / "PLAN.md").write_text(VALID_PLAN, encoding="utf-8")

    assert module.main(["validate"]) == 1
    errors = capsys.readouterr().err
    assert "Modify path missing:" in errors
    assert "does not match workspace" in errors
