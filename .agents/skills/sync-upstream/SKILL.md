---
name: sync-upstream
description: Review or integrate upstream AstrBot commits with a searchable decision ledger, per-commit provenance, and the fork's current architecture.
---

# Sync AstrBot upstream

Use the user's requested mode: review means inspect and propose; integrate or
apply authorizes implementation. Continue an already authorized sync without
another approval gate. Follow the upstream rules in `AGENTS.md`.

Inspect the worktree, remotes, and `upstream-sync.yaml`. Verify `upstream`
points to `https://github.com/AstrBotDevs/AstrBot.git`, then fetch and inspect:

```bash
git fetch --prune --tags upstream
uv run python .agents/skills/sync-upstream/scripts/inspect_upstream.py
uv run python .agents/skills/sync-upstream/scripts/upstream_decisions.py list --query "<feature>"
```

The inspector checks marker ancestry. A history mismatch needs resolution
before selecting an interval. Query prior decisions by SHA, PR, path, or feature
instead of loading `upstream-decisions.jsonl`.

For each pending commit, oldest-first, read its patch, source PR, and current
fork owner. Choose `cherry-pick`, `adapt`, `skip`, `replay`, or `revisit`
with a concrete reason. Reuse decisions only while their assumptions hold.
Replay requires an authorizing historical record.

In apply mode, work on a feature branch and read
[REFERENCE.md](REFERENCE.md) for commit provenance, conflict handling, and
ledger commands. Each absorbed upstream commit gets at most one implementation
commit; skip/revisit gets none. Preserve upstream authors and subjects.
Resolve routine conflicts against current fork contracts; use `revisit`
when prerequisites or intended behavior cannot be established.

Finish relevant dependency, OpenAPI, generated-model, bilingual-doc, and
release-metadata changes with the checks specified in `AGENTS.md`.
Advance the cursor only after the entire interval has explicit, completed
decisions. Put the cursor update in a separate metadata-only commit,
`chore(sync): record upstream integration`.

Return commit/disposition mappings, checks, and unresolved items.
[APPLY_PROMPT.md](APPLY_PROMPT.md) is a short continuation prompt.
