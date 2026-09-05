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
**Depth:** `small` / `medium` / `large` / `complex`
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

Testable outcomes, including failure paths that matter. Prefer
WHEN/THEN (or WHILE/IF) so each line has one interpretation.

## Out of scope

Bullet list. Include adjacent features that will look related.

## Tasks

### Task 1: <observable slice>

**Blocked by:** none (or Task N)

**Files:**

- Modify: `exact/path.py` (`symbol_name`)
- Test: `tests/unit/test_exact.py`

**Acceptance:**

- [ ] WHEN <trigger> THEN <observable>
- [ ] IF <failure> THEN <observable>

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
  contract (function signature, schema field, event name). Prefer
  existing seams; do not invent a new one unless the user picked
  `better` and two real adapters already exist.
- Every task has **Files**, **Acceptance**, and **Verify** with a real
  command from `REFERENCE.md`. **Blocked by** is required when tasks
  are not a linear chain.
- Fold scaffolding, config, and docs into the task that needs them.
- If a task would exceed about five files or two independent
  subsystems, split it.
- A behavior-preserving prefactor and the feature change are separate
  tasks. Do not mix them.
- A wide mechanical rename whose blast radius cannot stay green as a
  vertical slice uses expand → migrate batches → contract, not one
  tracer bullet.
- Conventional Commit type for the follow-up PR goes in the last task
  or a short Handoff line (`feat` / `fix` / `docs` / `chore`, …). Do
  not commit during planning.
