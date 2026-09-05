# Issue-plan overlay

This file is the checkout-specific fact sheet for `plan-issue`. Policy
stays in `SKILL.md`. Cite `AGENTS.md`, `GOVERNANCE.md`, and
`references/sources.md`; do not paste them.

## Product identity

| Field               | Value                                                             |
| ------------------- | ----------------------------------------------------------------- |
| Product             | AstrBot (Xero-Team fork)                                          |
| Repository          | `Xero-Team/AstrBot`                                               |
| Upstream provenance | `AstrBotDevs/AstrBot` (sync source only)                          |
| Issue templates     | `.github/ISSUE_TEMPLATE/{bug_report,feature_request,task}.yml`    |
| PR templates        | `.github/PULL_REQUEST_TEMPLATE/{feat,fix,docs,refactor,chore}.md` |
| Published artifacts | none                                                              |
| Docs                | in-app `/help/`                                                   |
| Python floor        | `>=3.14`; pin in `.python-version`                                |

`gh` must pass `--repo Xero-Team/AstrBot`. Confirm created URLs are under
`github.com/Xero-Team/AstrBot`.

## Issue kinds

| Template / label | Plan type                          | Extra research                           |
| ---------------- | ---------------------------------- | ---------------------------------------- |
| `bug`            | Fix plan                           | Reproduce or trace before designing      |
| `enhancement`    | Feature plan                       | Development Issue must exist before PR   |
| `task`           | Maintenance plan                   | Name the files or commands that prove it |
| pasted request   | Same as above after classification | Note that a feature still needs an Issue |

Fill exactly one of Human note or Agent note on any Issue this skill
opens. Agents must not fabricate a Human note.

## Workspace

Created by `scripts/issue_plan.py init` at `.tmp/issue-plan/<run-id>/`:

```text
.tmp/issue-plan/<run-id>/
  manifest.json    # SHA, branch, issue, slug, start time
  ISSUE.md         # fetched or pasted request
  RESEARCH.md      # coverage ledger, depth, current path, hypotheses
  BRIEF.md         # problem framing
  QUIZ.md          # five questions, scores, verdict
  REFLECT.md       # JTBD, why-chain, surgical vs better path
  QUESTIONS.md     # grill log, coverage summary
  PLAN.md          # executor plan
```

`<run-id>` is `issue-<number>` or `local-<slug>`. `.tmp/` is gitignored.
Do not relocate the run into `docs/` or `data/`.

If `status` shows an in-progress run at the same SHA and same issue or
slug, resume it. If the SHA drifted, start a new run and say so. Do not
overwrite a different incomplete plan without `--force`.

## Fetch commands

```bash
gh issue view <n> --repo Xero-Team/AstrBot \
  --json number,title,body,labels,comments,url,state,author,createdAt
gh issue list --repo Xero-Team/AstrBot --state all --search "<query>" --limit 20
gh search issues --repo Xero-Team/AstrBot "<query>"
```

Refuse a URL under `github.com/AstrBotDevs/AstrBot` unless the user
confirmed that upstream target. Do not post triage comments unless asked.

## Verify command map

Prescribe commands that exist in this checkout. Do not invent CI umbrellas.

| Surface                    | Focused command                                                                        |
| -------------------------- | -------------------------------------------------------------------------------------- |
| One Python behavior        | `uv run pytest tests/unit/test_<area>.py::TestClass::test_name`                        |
| Blocking Python            | `make test-blocking`                                                                   |
| Dashboard unit             | `cd dashboard && pnpm test`                                                            |
| Dashboard i18n             | `cd dashboard && pnpm i18n:check`                                                      |
| OpenAPI + generated client | `cd dashboard && pnpm generate:api` then the Prettier / docs JSON steps in `AGENTS.md` |
| Docs pages                 | `cd docs && pnpm run docs:build` and `make check-md`                                   |
| Host format/lint/build     | `make check`                                                                           |
| Plugin package             | `python .agents/skills/create-astrbot-plugin/scripts/check_plugin.py`                  |
| NapCat generated model     | `make napcat-check`                                                                    |

`make check` is not a complete CI-equivalent umbrella. Name the focused
test first; add `make check` only when the slice touches format/lint
surfaces.

## Owner map

Start from the module catalog in
`.agents/skills/audit-product/REFERENCE.md`. Assign the plan to the
runtime owner, not the importer. Sensitive zones (Dashboard auth, MCP
URLs, file tokens, adapter XML, knowledge-base upload, config redaction,
`v-html`) need an explicit failure-path task.

## Routing

| Request                                       | Skill                     |
| --------------------------------------------- | ------------------------- |
| Standalone plugin package                     | `create-astrbot-plugin`   |
| Absorb `upstream/master`                      | `sync-upstream`           |
| Product / security / completeness audit       | `audit-product`           |
| Architecture diagram of current code          | `archify`                 |
| Change this checkout from an Issue or request | `plan-issue` (this skill) |
