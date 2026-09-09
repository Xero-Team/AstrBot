---
name: plan-issue
description: Turn a GitHub Issue or change request into a code-backed implementation plan for this checkout. Use for planning or triage, not an implementation-only request.
license: AGPL-3.0-or-later
metadata:
  author: Xero-Team
  checkout: Xero-Team/AstrBot
---

# Plan an Issue

Produce a plan an executor can use without the planning conversation.
Match the user's scope and language. A planning-only request ends at the
plan; if implementation is already authorized, continue after validating it.

Inspect the request, current owners, callers, tests, and relevant docs.
Check for existing behavior or a prior rejection before proposing work.
For deeper investigation, use [research.md](references/research.md).
Ask only about unresolved choices that materially affect scope, behavior,
or acceptance; record routine assumptions and proceed. There is no required
quiz, framing approval, or second approval for previously authorized work.

Keep the plan under `.tmp/issue-plan/<run-id>/PLAN.md`. The workspace helper
records the checkout SHA and optionally fetches an Issue:

```bash
uv run python .agents/skills/plan-issue/scripts/issue_plan.py init --issue 123
uv run python .agents/skills/plan-issue/scripts/issue_plan.py fetch --issue 123
```

For a pasted request use `init --slug <name>`. Read
[REFERENCE.md](REFERENCE.md) for workspace and GitHub details.

Use [plan-template.md](references/plan-template.md). Name exact files,
symbols, observable acceptance criteria, dependencies, and focused verification
commands. Include relevant bilingual docs and generated contracts.
Compare alternatives only when there is a real tradeoff. Keep optional
research notes in the workspace rather than making extra documents a gate.

Review against [verification.md](references/verification.md), then run:

```bash
uv run python .agents/skills/plan-issue/scripts/issue_plan.py validate
```

Return the plan path, material assumptions, and any actual blocker.
Keep vulnerability details private under `SECURITY.md`.
Methodology provenance is in [sources.md](references/sources.md).
