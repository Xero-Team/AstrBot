# Integration mechanics

Read this in apply mode. Use the relevant checks and release metadata rules
linked from `AGENTS.md`.

## Commit provenance

One absorbed upstream commit maps to at most one implementation commit,
oldest-first. Skip/revisit produces none; an already-equivalent patch needs
a ledger decision rather than a duplicate commit.

- Cherry-pick with `git cherry-pick -x <full-sha>`. Preserve its upstream author
  and message; an unchanged message does not receive AI footers.
- Adapt manually against current fork owners, committing with
  `git commit --author="<upstream author>"`.
- Replay only when a historical ledger record authorizes it. Follow adaptation
  provenance and cite that record.

Preserve the upstream subject, including an existing PR suffix. Do not invent
a suffix. Change the subject only when the fork's user-visible semantics
materially differ, with an explanation in the body.

Adapted, replayed, and conflict-rewritten messages use this shape:

```text
<upstream subject>

<fork-specific explanation if needed>

Upstream-Commit: <full upstream SHA>
Upstream-Author: <name> <email>
Upstream-PR: AstrBotDevs#<number>
Sync-Disposition: adapt
Fork-Adaptation: <fork-specific change>
Tested: <command actually run>
AI-Generated: true
Generated-At: <current UTC timestamp>
```

Use the actual disposition and omit unavailable values. Obtain the timestamp
as specified in the shared commit reference. Git's retained `-x` line already
provides commit provenance; do not duplicate it with an Upstream-Commit trailer.
Do not add Signed-off-by without a repository/user DCO requirement.

Verify each author and one-to-one SHA mapping before continuing:

```bash
git show -s --format='%H%n%an <%ae>%n%cn <%ce>%n%s%n%B' HEAD
git show --stat --oneline HEAD
```

The fork maintainer is normally the committer, not the replacement author.

## Conflicts and existing integrations

Inspect conflicts and prerequisites instead of selecting ours/theirs blindly:

```bash
git log HEAD..<upstream_sha>^ -- <conflicted-path>
git log -G'<symbol>' HEAD..<upstream_sha>^ -- <conflicted-path>
git log --all --grep='Upstream-Commit: <full-upstream-sha>' --format='%H %s'
git cherry upstream/master
```

Mechanical context changes can remain cherry-picks. Behavior changes needed
for fork architecture are adaptations; preserve the author and record why.
If `-x` provenance was lost during resolution, add Upstream-Commit.
If intent or prerequisites cannot be established, abort only the cherry-pick
started by this workflow, record `revisit`, and explain the unresolved state.

## Ledger and cursor

The append-only ledger CLI supports `init`, `add`, `update`, `get`,
`list`, `validate`, `delete`, and `import-git`. Use `--help` for arguments.
Example:

```bash
uv run python .agents/skills/sync-upstream/scripts/upstream_decisions.py add \
  --commit <full-sha> --disposition adapt --summary "<reason>" \
  --source-pr 123 --reason-code fork-architecture --path astrbot/core/... \
  --fork-adaptation "<change>" --integration-commit <full-fork-sha>
uv run python .agents/skills/sync-upstream/scripts/upstream_decisions.py get --commit <sha> --history
uv run python .agents/skills/sync-upstream/scripts/upstream_decisions.py validate
```

`delete --reason` appends a tombstone; never remove historical JSONL lines.
`import-git --range <old>..<new>` produces inferred records that need review.
Reassess prior decisions when architecture, security, contracts, or toolchain
assumptions change.

After every commit in the interval has a completed disposition, finalize the
absorbed version/changelog and update `upstream-sync.yaml` with the full
fetched SHA, UTC timestamp, source PRs, and honest outcomes. If anything remains
unresolved, leave the cursor unchanged. Use a separate metadata-only commit,
`chore(sync): record upstream integration`, with AI footers.
