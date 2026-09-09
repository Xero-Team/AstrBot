# Plan template

Use the headings below for `issue_plan.py validate`; write prose in the user's
language. Keep evidence and decisions in this document. Add separate notes only
when the investigation needs them.

````markdown
# <Title>

**Issue:** <fork Issue URL or local-slug>
**SHA:** <full checkout SHA>

## Goal

Who needs which observable outcome?

## Architecture

The current owner, proposed change, and a real tradeoff if one exists.

## Constraints

Task-specific constraints; cite AGENTS.md for repository-wide rules.

## Current behavior

Trigger → code path → result, citing inspected `path:line` and symbols.

## Desired behavior

Testable outcomes and relevant failure behavior.

## Out of scope

Only material scope boundaries.

## Tasks

### Task 1: <observable change>

**Blocked by:** none

**Files:**

- Modify: `exact/path.py` (`symbol`)
- Test: `tests/unit/test_area.py`

**Acceptance:**

- [ ] <trigger and expected result>

**Verify:**

```bash
uv run pytest tests/unit/test_area.py
```

## Verification

Focused commands for the whole change, with expected outcomes.

## Docs / OpenAPI

Affected bilingual pages and generated contracts, or why none apply.

## Risks and open questions

Relevant assumptions, remaining decisions, and failure risks.
````

Repeat Task sections only for independently reviewable work. Use `Create:`
for new paths, `Modify:` for existing files, and `Blocked by: Task N` for
dependencies. Include a concrete verification command for every task.
Do not prescribe new tests for a low-impact edit that only needs existing
format or contract checks. Avoid placeholder code and full implementations.
