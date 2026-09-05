# Plan checker

Load this after `PLAN.md` exists. Run the script; then do the judgment
pass the script cannot do.

```bash
python .agents/skills/plan-issue/scripts/issue_plan.py validate
```

## Mechanical bars (script)

The validator fails when `PLAN.md` is missing a required heading, has
no `### Task`, a task lacks Files or Verify, or the text contains a
placeholder / forbidden fork artifact. Full validate also requires
`RESEARCH.md`, `BRIEF.md`, `QUIZ.md`, and `REFLECT.md`. `QUIZ.md` must
have five `### Question` sections, a `**Total:** n/10` line, and a
`**Verdict:**` of `pass`, `fail`, or `override`. `RESEARCH.md` must
include Coverage ledger, Hypotheses, and Impact surface headings.

Required headings: Goal, Architecture, Constraints, Current behavior,
Desired behavior, Out of scope, Tasks, Verification.

## Judgment bars (agent)

For every requirement in the Issue and `RESEARCH.md`:

1. **Coverage:** name the task that implements it, or move it to Out of
   scope with a reason. Every coverage-ledger row is answered or
   explicitly open in the plan's Open questions.
2. **Evidence:** current-behavior claims cite `path:line` that this
   session read. Inference is labeled as inference. Empty search is
   not treated as absence without a second surface.
3. **Redundancy:** the plan does not rebuild an existing path.
4. **Invariants:** no task restores a removed surface or weakens a
   security invariant from `AGENTS.md`.
5. **Verify realism:** each command exists in this checkout and matches
   the files touched. A Dashboard-only slice must not prescribe
   `uv run pytest` as its only proof.
6. **Docs:** user-visible behavior has matching `docs/zh/` and
   `docs/en/` work, or an explicit `none` with reason.
7. **OpenAPI:** route/schema changes list the generate-api and
   `docs/public/openapi.json` steps together.
8. **Scope:** no drive-by refactors unless `REFLECT.md` recommended
   them and the user picked `better`. No new dependencies without a
   stated need, no PyPI / image / `docs.astrbot.app` claims.
9. **Probe:** `BRIEF.md` matches the plan's problem. Quiz verdict
   `fail` without `override` must not treat the Issue body as the spec;
   the plan must follow the inferred **job** the user confirmed. Grill
   questions that were asked include a recommended answer.
10. **Impact:** callers, configs, tests, and bilingual docs from the
    research impact surface are tasks or explicit out-of-scope.

## Fail the plan when

- A task says "add tests" without a test path and command
- A task is "implement the feature"
- Approaches were not compared on feature-depth work
- The Issue is a vulnerability
- The only proof is `make check` on a behavior change
- The plan implements the ticket patch after reflection showed a
  different job and the user picked `better`

## After a pass

Show the workspace path. Ask for approval. Do not implement in the
same turn.
