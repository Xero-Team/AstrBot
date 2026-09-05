---
name: plan-issue
description: >
  Turn a GitHub Issue or a pasted change request into a code-backed
  implementation plan for this Xero-Team/AstrBot checkout. Use when the
  user asks to plan, shape, triage, spec, or turn an issue into tasks —
  even if they say 方案, 规划, or 可落地. Do not use for plugin scaffolding,
  upstream cherry-pick, product audits, or starting implementation.
license: AGPL-3.0-or-later
compatibility: >
  Requires this Xero-Team/AstrBot checkout, Python 3.14+, git, and gh
  when fetching a GitHub Issue. Working state lives under .tmp/issue-plan/.
metadata:
  author: Xero-Team
  checkout: Xero-Team/AstrBot
---

# Plan an Issue against this checkout

Convert an Issue or pasted request into a plan an executor can follow
without the planning chat. Ground every claim in this worktree. Stop at
the written plan unless the user approved implementation in this
conversation.

Cite `AGENTS.md`, `GOVERNANCE.md`, `AI_POLICY.md`, this folder's
`REFERENCE.md`, and `references/sources.md`. Do not paste those files.
Do not vendor third-party planning skill trees into `.agents/skills/`.

## Locked

- Plans and working state live under `.tmp/issue-plan/<run-id>/`
  (gitignored). Do not write them into `docs/`, `tasks/`, `dev/plans/`,
  or `docs/superpowers/`.
- Python 3.14+, source-build `compose.yml` / `astrbot:local`, in-app docs
  at `/help/`. Do not restore legacy shims or treat upstream PyPI,
  `soulter/astrbot`, or `docs.astrbot.app` as fork artifacts.
- Open Issues and PRs against `Xero-Team/AstrBot` with
  `--repo Xero-Team/AstrBot`. Do not open them on `AstrBotDevs/AstrBot`
  unless the user explicitly confirms that upstream target.
- Security reports follow `SECURITY.md`. Do not plan a public Issue or
  public PR for a vulnerability.
- Agents may commit this skill when asked. They must not merge, push
  `master`, tag, or publish. See
  `.agents/shared/ai-contribution/REFERENCE.md`.
- Do not implement, scaffold, or edit production code during planning.

## Open

Which Issue or pasted request to plan, spike vs bounded vs feature
depth, whether to fetch with `gh`, and whether the user **explicitly**
skipped probe. Ask only when those choices change the artifact. Default
depth is **feature** when the user asked for a written plan. Default
probe is **required**.

## Do not

- Jump to implementation because the change "looks small".
- Invent file paths, line numbers, APIs, or tests that were not read.
- Restore `platform_settings.group_wake_policy`,
  `disable_builtin_commands`, handler-name `alter_cmd` lookup, or other
  removed surfaces listed in `AGENTS.md`.
- Install GitHub Spec Kit, create `.specify/`, or copy Superpowers /
  mattpocock / addyosmani skill trees into this checkout.
- Auto-comment on GitHub during planning unless the user asked.
- Split work by layer (all models, then all routes, then all UI) when a
  vertical slice can ship one observable behavior.
- Dump full implementations into every task. Name paths, symbols, and
  contracts; add a code sketch only when a new signature is easy to get
  wrong.
- Claim a command was verified unless this session ran it.
- Skip brief, quiz, reflect, or grill unless the user explicitly waived
  probe in this conversation. Filing an Issue, "this is small", or "I
  know the tree" is not a waiver.
- Ask the user a fact this tree already answers.
- Treat an empty grep as proof the behavior is absent.
- Create `CONTEXT.md`, `docs/adr/`, `.specify/`, or an HTML architecture
  report in this checkout. Cite `AGENTS.md` instead.
- Propose a new seam or interface before the user picks a path.
- Mix a behavior-preserving refactor with a feature change in one task.

## Handoff

Load only the file the current step needs:

- Checkout overlay and `gh` commands: `REFERENCE.md`
- Research protocol: `references/research.md`
- Brief, quiz, reflect: `references/probe.md`
- Plan shape: `references/plan-template.md`
- Plan checker: `references/verification.md`
- Provenance (cite, do not paste): `references/sources.md`
- Plugin packages: `.agents/skills/create-astrbot-plugin/SKILL.md`
- Upstream absorb: `.agents/skills/sync-upstream/SKILL.md`
- Product audit: `.agents/skills/audit-product/SKILL.md`
- Diagrams, if the plan needs one: `.agents/skills/archify/SKILL.md`
- Commit shape: `.agents/shared/conventional-commit/REFERENCE.md` only
  if committing this skill

## Operating modes

- **Research mode:** read the Issue, search the tree, write a detailed
  Chinese `RESEARCH.md`. No plan yet if a stop condition fires.
- **Probe mode:** brief the problem, quiz the user, reflect on a better
  whole-tree path. Required after research unless the user explicitly
  skipped it. See `references/probe.md`.
- **Clarify mode:** grill only after probe. Record answers in
  `QUESTIONS.md`. Completeness check, not a new spec file. Skipped with
  probe.
- **Plan mode (default end state):** write `PLAN.md`, then validate.
- **Check mode:** re-validate an existing workspace.
- **Implement mode:** enter only after the user explicitly approved the
  plan in this conversation. That is a different task; keep the plan
  stable and follow it.

After research, classify **depth** (`small` / `medium` / `large` /
`complex`) in `RESEARCH.md`. Probe still runs unless waived. Small
skips approach variants. Large or complex work that still has fog
writes a capability map before one giant plan. See `references/probe.md`.

Treat these phrases as an explicit skip, and only these (or a clear
synonym that names skipping the Q&A): `skip probe`, `skip quiz`,
`skip the questions`, `just write the plan`, `跳过问答`, `跳过提问`,
`直接出方案`. Record `probe: skipped` in the workspace:

```bash
python .agents/skills/plan-issue/scripts/issue_plan.py skip-probe
```

Pass `--skip-probe` on `init` only when that waiver already happened.
Do not infer a skip.

## Preflight

1. Read `REFERENCE.md` and `references/research.md`. Cite `AGENTS.md`;
   do not paste it.
2. Inspect `git status --short --branch` and `git rev-parse HEAD`. Do
   not stash, reset, or discard unrelated work.
3. Create or resume the workspace:

   ```bash
   python .agents/skills/plan-issue/scripts/issue_plan.py init --issue 123
   python .agents/skills/plan-issue/scripts/issue_plan.py fetch --issue 123
   python .agents/skills/plan-issue/scripts/issue_plan.py status
   ```

   For a pasted request with no Issue number, pass `--slug <short-name>`
   instead of `--issue`. New user-facing features still need a
   development Issue before the follow-up PR (`GOVERNANCE.md`); note
   that in the plan rather than blocking research.

4. Route away when the request is owned by another skill: plugin package
   → `create-astrbot-plugin`; upstream absorb → `sync-upstream`; product
   audit → `audit-product`.

## Workflow

### 1. Research

Follow `references/research.md`. Write `RESEARCH.md` in Simplified
Chinese (English H2 headings, verbatim paths/symbols/commands). Present
it in Chinese in chat. Done when `RESEARCH.md` records:

- `Kind` plus `Depth`, and a coverage ledger of 2–7 current-state
  questions, each answered or explicitly open, with a paragraph per row
- a search log of queries, synonyms or a second surface, and hits
- current behavior as trigger → path → result, with `path:line` evidence
- redundancy result (already implemented or not, and where searched)
- prior-rejection result for all four sources (`AGENTS.md`, changelog
  fork deviations, closed wontfix / duplicate Issues,
  `upstream-decisions.jsonl` when applicable)
- owners, tests, matching `docs/zh/` + `docs/en/` pages, and a named
  impact surface
- hypotheses labeled `CONFIRMED` / `REJECTED` / `UNRESOLVED` with
  confidence
- stop, spike, or continue

Stop and report, do not write a build plan, when the change is already
implemented, previously rejected, a security vulnerability, or owned by
another skill.

For a `bug`, name one **red-capable** command that would catch the
reporter's symptom before hypothesising a mechanism. If this session
ran it, paste redacted output. If not, say so.

### 2–4. Brief, quiz, reflect

Follow `references/probe.md` in order unless probe is skipped. Do not
skip to grilling on the agent's own judgment.

If probe is **skipped**, do not wait and do not quiz. Write `BRIEF.md`
and `REFLECT.md` from research (default path `surgical` unless the
request already picked one), write `QUIZ.md` with `**Verdict:** skipped`,
write `QUESTIONS.md` with the skip record, then go to the plan. Remaining
unknowns become plan Open questions, not a stall.

Otherwise:

1. **Brief** the problem in this checkout. Wait for the user to accept
   or correct the framing (`BRIEF.md`).
2. **Quiz** with five issue-specific multiple-choice questions, one at
   a time. Do not ask who owns the code or any fact a grep can answer.
   Score 0–2 each (expected total **7/10**). Use answers, including
   distractors, to infer real intent. Write `QUIZ.md`. A `fail` does
   not abort the run; it means the Issue text is not yet the spec.
3. **Reflect** on the inferred **job** (JTBD: verb + object + context,
   no proposed patch). Run a Five Whys chain on the request until the
   root is an executable change. Compare a surgical current-path
   change with a better whole-tree design, including refactors.
   Recommend one. Wait for the user to pick (`REFLECT.md`).

If they waive probe after it started, keep answers already recorded,
run `skip-probe`, mark the rest skipped, and continue.

### 5. Grill

Skip this step when probe is skipped. Otherwise ask one question at a
time, and only when the answer changes scope, architecture, or
acceptance. Scan remaining unknowns Clear / Partial / Missing; ask at
most five, highest Impact × Uncertainty first. Prefer a short
multiple-choice with a **recommended** answer. First open choice, if
any: surgical vs better vs stop. Record each Q/A in `QUESTIONS.md`.

List remaining non-blocking assumptions in the plan instead of stalling.
If the request bundles several independently testable capabilities, or
the way to the destination is still fog, stop and propose a capability
map (vertical slices + blocking edges) before writing one giant plan.
Close grilling with a coverage summary: Resolved / Deferred / Clear /
Outstanding.

### 6. Choose an approach

Work inside the path the user picked after reflection (`surgical` or
`better`). If probe was skipped, use the `REFLECT.md` recommendation
(default `surgical`) and record rejected alternatives in the plan; do
not wait for another pick. Present remaining candidates as Files /
Problem / Solution / Benefits. Apply the deletion test and the
one-adapter rule (`references/probe.md`). Prefer existing seams; fewer
seams is better. Do not propose a new interface until they pick. For
`medium`/`large`/`complex` work with probe required, present 2–3
variants of that path with trade-offs and one recommendation. Small
work, and skipped probe, may skip variants. Do not silently fall back
to a local patch if they chose the better-path refactor.

### 7. Write the plan

Use `references/plan-template.md`. Each task is a vertical slice with
exact paths, symbols, acceptance, and a real verify command from this
checkout. No `TBD`, no "add tests", no "similar to Task N".

Then validate:

```bash
python .agents/skills/plan-issue/scripts/issue_plan.py validate
```

### 8. Hard gate

Show the plan path. Ask the user to approve it. Do not start
implementation in the same turn that first presents the plan.

## Verify

```bash
python .agents/skills/plan-issue/scripts/issue_plan.py validate
python .agents/skills/plan-issue/scripts/issue_plan.py status
```

A finished planning run has `RESEARCH.md` (with depth), `BRIEF.md`,
`QUIZ.md` (`pass` / `fail` / `override`, or `skipped` after an explicit
waiver), `REFLECT.md`, `QUESTIONS.md` coverage or skip record,
`PLAN.md`, a passing validator with empty BLOCKING, and either an Issue
URL under `github.com/Xero-Team/AstrBot` or an explicit local-slug note
that a development Issue is still required before a feature PR.

## Anti-rationalization

| Excuse                                    | Rebuttal                                                                     |
| ----------------------------------------- | ---------------------------------------------------------------------------- |
| "It is obvious, I will just code it"      | This skill's output is the plan. Implementation is a later, gated task.      |
| "I know this kind of bot, so I can skip"  | Bounded means this repo already has the flow. Read it.                       |
| "File paths will go stale, so omit them"  | The executor starts now, on this SHA. Record paths plus durable symbols.     |
| "I will add verification later"           | A task without a command is incomplete. Fix it before handoff.               |
| "Spec Kit / Superpowers is more complete" | Cite those URLs. Do not vendor their trees or their default directories.     |
| "The Issue is on upstream, close enough"  | Plan against `Xero-Team/AstrBot` unless the user confirmed upstream.         |
| "I will restore the old flag for compat"  | Compatibility shims are out of scope. Design on the current path.            |
| "They filed the Issue, skip the quiz"     | A ticket is not a waiver. Probe unless they explicitly skipped it.           |
| "Low quiz score, abort"                   | Reflect and grill until the inferred goal is explicit. Then plan.            |
| "Reflection is gold-plating"              | It is a recommendation. The user picks. The plan records that choice.        |
| "One grep found nothing, so it is new"    | Empty lane is not absence. Report queries, a synonym, and a second surface.  |
| "Ask the user how the code works"         | Facts are yours. Decisions are theirs.                                       |
| "The ticket is the job"                   | State the JTBD without the proposed patch. Then plan for that job.           |
| "Better means rewrite the tree"           | Deletion test + YAGNI hot spots. Cold code stays.                            |
| "Add a seam so tests can mock it"         | One adapter is hypothetical; two adapters make a real seam.                  |
| "I can see the bug in the stack trace"    | Name a red-capable command first. Then hypothesise.                          |
| "Small change, skip probe"                | Small only skips approach variants. Probe still runs unless waived.          |
| "User said they know this tree"           | Knowledge is not a skip phrase. Wait for `skip probe` / `跳过问答`.          |
| "User explicitly skipped probe"           | Skip interactive Q&A. Still research, still write BRIEF/REFLECT, still gate. |
