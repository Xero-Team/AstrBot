import importlib.util
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
    args = Namespace(issue=9, slug=None, force=False, skip_probe=False)
    assert module.cmd_init(args) == 0
    run_dir = tmp_path / ".tmp" / "issue-plan" / "issue-9"
    manifest = (run_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"run_id": "issue-9"' in manifest
    assert '"sha": "abc123"' in manifest
    assert '"probe": "required"' in manifest
    pointer = (tmp_path / ".tmp" / "issue-plan" / "LATEST").read_text(encoding="utf-8")
    assert pointer.strip() == "issue-9"
    with pytest.raises(module.PlanError, match="already exists"):
        module.cmd_init(args)
    args.force = True
    args.skip_probe = True
    assert module.cmd_init(args) == 0
    manifest = (run_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"probe": "skipped"' in manifest


VALID_RESEARCH = """# 研究：记录唤醒原因

**Issue:** https://github.com/Xero-Team/AstrBot/issues/1
**SHA:** abcdef0123456789
**Kind:** enhancement
**Depth:** medium
**Verdict:** continue

## Request

- **原话：** 在事件上记录所选唤醒原因
- **分类：** 标签为 enhancement
- **已关闭问题：** 无
- **不在范围内的相邻请求：** 恢复 `group_wake_policy`

## Coverage ledger

| # | 问题 | 区域 | 检索 | 证据 | 状态 |
| - | ---- | ---- | ---- | ---- | ---- |
| 1 | 今天 waking-check 如何决定唤醒？ | pipeline | `WakingCheckStage` | `astrbot/core/pipeline/waking_check/stage.py:1` | answered |

`WakingCheckStage.process` 根据配置决定是否唤醒，不写入原因。测试见 `tests/unit/test_waking_check.py`。

## Search log

| 查询 | 工具 | 命中 | 结论 |
| ---- | ---- | ---- | ---- |
| `wake_reasons` | Grep | 0 | 本车道看不见 |
| `group_wake_policy` | Grep | `AGENTS.md:1` | 已禁止恢复 |

## Current behavior

**触发：** 群聊提及机器人
**路径：** `astrbot/core/pipeline/waking_check/stage.py:1`（`WakingCheckStage`）
**结果：** 唤醒或不唤醒，事件上无原因字段
**失败路径：** 本请求不涉及
**文档 vs 代码：** 无漂移

## Redundancy

- **查询：** `wake_reasons`、`group_wake_policy`
- **看过的路径：** `astrbot/core/pipeline/waking_check/`
- **结论：** 未实现

## Prior rejection

| 来源 | 结果 |
| ---- | ---- |
| `AGENTS.md` | 禁止恢复 `platform_settings.group_wake_policy` |
| changelog | 未找到 |
| wontfix | 未找到 |
| `upstream-decisions.jsonl` | 不适用 |

## Owners and tests

- **运行时所有者：** pipeline `astrbot/core/pipeline/waking_check/stage.py`（`WakingCheckStage`）
- **测试：** `tests/unit/test_waking_check.py`
- **敏感区：** 无

## Docs

- **中文页：** `docs/zh/use/configuration.md`
- **英文页：** `docs/en/use/configuration.md`
- **OpenAPI：** 无
- **漂移：** 无

## Impact surface

| 类别 | 路径 / 符号 | 计划里如何处理 |
| ---- | ----------- | -------------- |
| 调用方 | `WakingCheckStage` | 任务 |
| 测试 | `tests/unit/test_waking_check.py` | 任务 |
| 双语文档 | pipeline 配置页 | 任务 |

## Hypotheses

| 主张 | 结论 | 证据 | 置信度 | 下一步 |
| ---- | ---- | ---- | ------ | ------ |
| 已实现 | REJECTED | 无 `wake_reasons` 符号 | high | 已做完 |

## Open questions

无
"""


VALID_QUIZ = """# Quiz

**Total:** 8/10
**Verdict:** pass

### Question 1: Current path

**Score:** 2

### Question 2: Current path

**Score:** 2

### Question 3: Invariant

**Score:** 1

### Question 4: Done

**Score:** 2

### Question 5: Wrong fix

**Score:** 1
"""


VALID_SKIPPED_QUIZ = """# Quiz

**Total:** 0/10
**Verdict:** skipped
**Reason:** user explicitly skipped probe
"""


VALID_BRIEF = """# Brief

**Problem:** operators cannot see why a group message woke the bot
**Owner:** pipeline `astrbot/core/pipeline/waking_check/stage.py`
**Not the problem:** restoring `group_wake_policy`
"""

VALID_REFLECT = """# Reflect

## Inferred goal

Record why a group message woke the bot.

## Why-chain

Why 1 operators cannot audit wakeups.

## Surgical path

Extend `WakingCheckStage` and its unit tests.

## Better path

Do not split a second wake owner.

## Recommendation

surgical
"""


def test_validate_research_accepts_complete_document():
    module = _load()
    assert module.validate_research(VALID_RESEARCH) == []


def test_validate_research_requires_headings():
    module = _load()
    errors = module.validate_research("# Research\n\n## Request\n\nhello\n")
    assert "RESEARCH.md missing heading: Coverage ledger" in errors
    assert "RESEARCH.md missing heading: Search log" in errors
    assert "RESEARCH.md missing heading: Hypotheses" in errors
    assert "RESEARCH.md missing heading: Impact surface" in errors
    assert any("Depth" in item for item in errors)
    assert any("Kind" in item for item in errors)
    assert any("Verdict" in item for item in errors)


def test_validate_research_requires_path_cite_unless_routed():
    module = _load()
    missing_cite = VALID_RESEARCH.replace(
        "`astrbot/core/pipeline/waking_check/stage.py:1`",
        "`stage.py`",
    ).replace("`AGENTS.md:1`", "`AGENTS.md`")
    assert any("path:line" in item for item in module.validate_research(missing_cite))
    routed = (
        "# 研究：插件\n\n"
        "**Kind:** task\n"
        "**Depth:** small\n"
        "**Verdict:** route:create-astrbot-plugin\n\n"
        "## Request\n\n插件包\n\n"
        "## Coverage ledger\n\n无\n\n"
        "## Search log\n\n无\n\n"
        "## Current behavior\n\n无\n\n"
        "## Redundancy\n\n无\n\n"
        "## Prior rejection\n\n无\n\n"
        "## Owners and tests\n\n无\n\n"
        "## Docs\n\n无\n\n"
        "## Impact surface\n\n无\n\n"
        "## Hypotheses\n\n无\n\n"
        "## Open questions\n\n无\n"
    )
    assert module.validate_research(routed) == []


def test_validate_brief_requires_problem():
    module = _load()
    assert module.validate_brief(VALID_BRIEF) == []
    assert "BRIEF.md missing **Problem:**" in module.validate_brief("# Brief\n")


def test_validate_reflect_requires_path_headings():
    module = _load()
    assert module.validate_reflect(VALID_REFLECT) == []
    errors = module.validate_reflect("# Reflect\n\n## Inferred goal\n\nhello\n")
    assert "REFLECT.md missing heading: Surgical path" in errors
    assert "REFLECT.md missing heading: Better path" in errors


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


def test_validate_quiz_accepts_complete_document():
    module = _load()
    assert module.validate_quiz(VALID_QUIZ) == []


def test_validate_quiz_requires_five_questions_total_and_verdict():
    module = _load()
    errors = module.validate_quiz("# Quiz\n\n**Total:** 11/10\n")
    assert any("Verdict" in item for item in errors)
    errors = module.validate_quiz("# Quiz\n\n**Total:** 11/10\n**Verdict:** pass\n")
    assert any("five ### Question" in item for item in errors)
    assert "QUIZ.md total exceeds 10" in errors


def test_validate_quiz_accepts_skipped_only_when_probe_skipped():
    module = _load()
    assert module.validate_quiz(VALID_SKIPPED_QUIZ, probe="skipped") == []
    errors = module.validate_quiz(VALID_SKIPPED_QUIZ, probe="required")
    assert any("workspace probe is required" in item for item in errors)


def test_validate_requires_align_files_unless_plan_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    run_dir = tmp_path / ".tmp" / "issue-plan" / "issue-9"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        '{"schema_version": 1, "run_id": "issue-9"}\n',
        encoding="utf-8",
    )
    (run_dir / "PLAN.md").write_text(VALID_PLAN, encoding="utf-8")
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    with pytest.raises(module.PlanError, match="RESEARCH.md"):
        module.cmd_validate(Namespace(run_dir=str(run_dir), plan_only=False))
    assert module.cmd_validate(Namespace(run_dir=str(run_dir), plan_only=True)) == 0
    (run_dir / "RESEARCH.md").write_text(VALID_RESEARCH, encoding="utf-8")
    (run_dir / "BRIEF.md").write_text(VALID_BRIEF, encoding="utf-8")
    (run_dir / "REFLECT.md").write_text(VALID_REFLECT, encoding="utf-8")
    (run_dir / "QUIZ.md").write_text(VALID_QUIZ, encoding="utf-8")
    assert module.cmd_validate(Namespace(run_dir=str(run_dir), plan_only=False)) == 0


def test_skip_probe_allows_skipped_quiz_on_full_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    run_dir = tmp_path / ".tmp" / "issue-plan" / "issue-9"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        '{"schema_version": 1, "run_id": "issue-9", "probe": "skipped"}\n',
        encoding="utf-8",
    )
    (run_dir / "PLAN.md").write_text(VALID_PLAN, encoding="utf-8")
    (run_dir / "RESEARCH.md").write_text(VALID_RESEARCH, encoding="utf-8")
    (run_dir / "BRIEF.md").write_text(VALID_BRIEF, encoding="utf-8")
    (run_dir / "REFLECT.md").write_text(VALID_REFLECT, encoding="utf-8")
    (run_dir / "QUIZ.md").write_text(VALID_SKIPPED_QUIZ, encoding="utf-8")
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    assert module.cmd_validate(Namespace(run_dir=str(run_dir), plan_only=False)) == 0


def test_skip_probe_command_updates_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
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
    assert (
        module.cmd_init(Namespace(issue=9, slug=None, force=False, skip_probe=False))
        == 0
    )
    run_dir = tmp_path / ".tmp" / "issue-plan" / "issue-9"
    assert module.cmd_skip_probe(Namespace(run_dir=str(run_dir))) == 0
    manifest = (run_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"probe": "skipped"' in manifest


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
