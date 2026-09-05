# Research protocol

Load this before writing `RESEARCH.md`. Search by domain concept, not
only the Issue's wording. Facts about this tree are the agent's job;
do not ask the user what a grep can answer.

## Read the request

1. Title, body, labels, comments, linked PRs. For a PR treated as a
   request, read the diff too.
2. Parse prior Human note / Agent note so resolved questions are not
   re-asked.
3. Classify: `bug`, `enhancement`, `task`, or mixed. Mixed work that
   bundles independent capabilities needs a capability map first.

## Coverage ledger

Before a deep dive, write 2–7 **current-state** questions. Each row
asks what exists, where it lives, how it behaves, or how it is tested.
Do not encode the requested patch in the question.

Typical dimensions (keep a row only when it is material):

| Angle       | Question to answer                                   |
| ----------- | ---------------------------------------------------- |
| Structure   | Which package or owner owns this surface?            |
| Entrypoints | What starts the flow (adapter, route, CLI, cron)?    |
| Flow        | How state or a message moves through the system?     |
| Contracts   | Types, schemas, config, events, OpenAPI fields?      |
| Validation  | Which tests and fixtures prove the current behavior? |
| History     | Why is it this way (`git log`, changelog, ADRs)?     |

A row is done only when it is `answered` with `path:line` (and a test
path, or an explicit "no test") or `open:` with the missing evidence
and why that gap matters. Empty search is "this lane cannot see it",
not "it is absent". Report the queries and at least one synonym or
second surface before claiming absence.

## Parallel lanes

For a non-trivial request, fan out disjoint lanes rather than one
serial skim. Typical first wave:

1. Target-flow: inbound trigger to effect.
2. Validation and history: tests, docs, recent commits.
3. Cross-check: alternate paths, flags, generated code, fork
   invariants.

Give each lane an exact question, directories to prefer, and a
required return of `claim`, `path:line`, `verdict`, `confidence`.
Do not spawn two agents onto the same vague question.

The parent re-reads every load-bearing `path:line`. Subagent
summaries are leads. Merge by hunting conflict first; do not average
disagreement away.

## Redundancy

Search the tree for an existing implementation of the requested
behavior. Report the queries and the paths inspected.

Typical seams:

- Pipeline stages: `astrbot/core/pipeline/stage_order.py`
- Commands: command database / Orbit handlers, not fossil short names
- Providers: `astrbot/core/provider/provider_modules.py`
- Dashboard HTTP: `openspec/openapi-v1.yaml` then `astrbot/dashboard/`
- Plugin SDK: `astrbot/api/` only for plugin-facing work

If the behavior already exists, stop. Point to it. Do not write a
rebuild plan.

## Prior rejection

Check, in order, and quote the hit or write `nothing found`:

1. `AGENTS.md` do-not-restore and security invariants
2. Latest `changelogs/` _Fork Adaptations_ / _Fork Deviations_
3. Closed Issues/PRs with `wontfix`, duplicate, or "will not restore"
4. `upstream-decisions.jsonl` when the request is an upstream feature
   this fork skipped

Do not create `.out-of-scope/`. A rejected enhancement stays in GitHub
plus changelog notes.

## Trace current behavior

Read the owner, the nearest tests, and the matching `docs/zh/` +
`docs/en/` pages. Cite `path:line`. Docs vs code drift is a finding for
the plan (fix docs with the change), not a license to invent a third
behavior.

For a bug: reproduce from the reporter's steps, or trace the code path
and say the live repro was not run. Distinguish **symptom** (what
fails) from **mechanism** (how the current path produces it).

## Hypotheses

When behavior or "already implemented" is ambiguous, keep 1–3 sharp
hypotheses and spend the cheapest check that **kills** one. Label each
`CONFIRMED`, `REJECTED`, or `UNRESOLVED`. Tie the verdict to files,
tests, config, or history. Leave `UNRESOLVED` rather than padding
certainty. Distinguish direct evidence from inference.

Track `claim → evidence → confidence → next check`. A snippet is a
lead until a second surface (test, caller, config, or git history)
agrees.

## Impact surface

Name the likely callers, configs, generated artifacts, tests, and
bilingual docs a change here would touch. That list becomes plan
tasks or explicit out-of-scope.

## Stop conditions

Write `RESEARCH.md` and halt planning when:

- already implemented
- previously rejected, and the user did not explicitly reopen it
- security vulnerability (direct the user to `SECURITY.md`)
- owned by `create-astrbot-plugin`, `sync-upstream`, or `audit-product`

## RESEARCH.md shape

```markdown
# Research: <title>

**Issue:** <url or local-slug>
**SHA:** <full>
**Verdict:** continue | already-implemented | rejected | route:<skill> | security

## Request

## Coverage ledger

| #   | Question               | Area  | Evidence    | Status   |
| --- | ---------------------- | ----- | ----------- | -------- |
| 1   | How does X work today? | owner | `path:line` | answered |

## Current behavior

## Redundancy

## Prior rejection

## Owners and tests

## Docs

## Impact surface

## Hypotheses

| Claim                    | Verdict  | Evidence                        |
| ------------------------ | -------- | ------------------------------- |
| already implemented as Y | REJECTED | searched A, B; read `path:line` |

## Open questions
```

After a `continue` verdict, load `references/probe.md`. Do not grill or
write `PLAN.md` until brief, quiz, and reflect are done.
