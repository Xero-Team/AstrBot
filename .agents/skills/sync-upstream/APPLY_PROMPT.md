# Apply a reviewed upstream integration plan

Use the sync-upstream skill in apply mode. In Codex CLI, invoke it as
`$sync-upstream`; in OpenCode, load `sync-upstream` with the skill tool.
Execute the reviewed plan supplied in this conversation and carry it through
integration, ledger updates, and verification.

## Inputs and authorization

Find the reviewed commit list, dispositions, interval, and push/PR instructions
in the current conversation or the supplied plan artifact. Reuse decisions and
authorization already given. If the plan is missing, inspect the cursor and
ledger, then ask for the missing plan before applying commits. Do not invent
approved dispositions.

Read these sources as needed; cite them instead of pasting them:

- `AGENTS.md`: fork invariants, toolchain, generated artifacts, and git policy.
- `.agents/skills/sync-upstream/SKILL.md`: apply workflow and provenance.
- `.agents/shared/conventional-commit/REFERENCE.md`: generated commit messages.
- `.agents/shared/ai-contribution/REFERENCE.md` and `AI_POLICY.md`: contribution boundaries.
- `upstream-sync.yaml`: cursor; there is no `pending` field.
- `upstream-decisions.jsonl`: durable decisions and replay authorization.

## Prepare

Inspect `git status --short --branch` and `git remote -v`. Preserve unrelated
work and use a feature branch or isolated worktree. Verify `upstream` points to
`https://github.com/AstrBotDevs/AstrBot.git`; add the remote if absent or correct
its URL if needed. Run:

```bash
git fetch --prune --tags upstream
uv run python .agents/skills/sync-upstream/scripts/inspect_upstream.py
```

Read patches with `git show <sha>`. Keep the fork branch as the integration
base. Check the ledger before repeating any prior integration.

## Apply and verify

Process the reviewed interval oldest-first. Create one implementation commit
per `cherry-pick`, `adapt`, or `replay` item; `skip` and `revisit` create
none. Preserve upstream subjects and authors, with the skill's provenance
trailers for adaptations. Resolve routine conflicts against current fork
behavior. Record unresolved intent as `revisit` instead of guessing.

Run focused tests, then the relevant gates in `AGENTS.md`. Record each
disposition in the ledger. Advance the cursor only after every SHA has a
disposition and the interval is complete, using the metadata-only commit
`chore(sync): record upstream integration`.

Push a feature branch only when already requested. Follow the conversation's
PR instructions and target `Xero-Team/AstrBot` with
`--repo Xero-Team/AstrBot`; verify the returned URL. An upstream PR requires
explicit confirmation of that target. A human maintainer performs merges,
pushes to `master`, tags, and releases under repository policy.

## Deliver

Return the branch, commit/disposition mapping, ledger and cursor status,
checks actually run, remaining risks, and PR URL if one was opened. Preserve
checkpoint state if blocked so the next session can resume without repeating
completed commits.
