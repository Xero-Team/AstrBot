# Plan template

Write `PLAN.md` in English. Keep paths, commands, APIs, and error
strings verbatim. Copy this skeleton; delete unused optional sections.

````markdown
# <Title> Implementation Plan

**Goal:** one sentence
**Issue:** URL under github.com/Xero-Team/AstrBot, or `local-<slug>` plus
"open a development Issue before the PR"
**SHA:** full object name this plan was researched against
**Architecture:** 2–3 sentences
**Recommended approach:** name, why it wins, what was rejected
**Probe:** quiz `pass` / `fail` / `override`; user picked `surgical` or
`better`; job statement from `REFLECT.md`

## Constraints

- Python `>=3.14`; no 3.10–3.13 branches
- No legacy shims; current-path design only
- In-app docs at `/help/`; no `docs.astrbot.app`
- Agents must not merge or push `master`

## Current behavior

Cite `path:line`. Note the impact surface (callers, configs, tests,
docs) a change here would touch.

## Desired behavior

Testable outcomes, including failure paths that matter.

## Out of scope

Bullet list. Include adjacent features that will look related.

## Tasks

### Task 1: <observable slice>

**Files:**

- Modify: `exact/path.py` (`symbol_name`)
- Test: `tests/unit/test_exact.py`

**Acceptance:**

- [ ] specific observable 1
- [ ] specific observable 2

**Verify:**

```bash
uv run pytest tests/unit/test_exact.py::test_name
```

Expected: PASS (or the named failure if this is a red test)

### Task 2: <next slice>

...

## Verification

End-to-end commands for the whole change, focused first, then the
smallest extra gate the slice actually touches.

## Docs / OpenAPI

`none` or the bilingual pages plus `openspec/openapi-v1.yaml` regeneration
commands from `AGENTS.md`.

## Risks

| Risk | Impact       | Mitigation |
| ---- | ------------ | ---------- |
| ...  | high/med/low | ...        |

## Open questions

Non-blocking assumptions only. Blocking questions belong in
`QUESTIONS.md` until answered.
````

## Task rules

- One vertical slice per task: a behavior a reviewer could accept or
  reject on its own.
- Name files and symbols. Add a short code sketch only for a new
  contract (function signature, schema field, event name).
- Every task has **Files**, **Acceptance**, and **Verify** with a real
  command from `REFERENCE.md`.
- Fold scaffolding, config, and docs into the task that needs them.
- If a task would exceed about five files or two independent
  subsystems, split it.
- Conventional Commit type for the follow-up PR goes in the last task
  or a short Handoff line (`feat` / `fix` / `docs` / `chore`, …). Do
  not commit during planning.
