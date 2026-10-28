# Skills

`.agents/skills/` is the only skill source in this repository. Each skill is a
directory with `SKILL.md` (shared instructions) plus optional `REFERENCE.md`,
`scripts/`, and `agents/openai.yaml` (Codex UI metadata).

## Codex CLI and OpenCode

Both clients discover `.agents/skills/<name>/SKILL.md`. Keep one source tree;
do not copy skills into `.codex/` or `.opencode/`. Repository rules remain in
`AGENTS.md`, which both clients support.

In Codex, invoke a skill with a `$skill-name` mention, for example:

```text
Use $plan-issue to turn issue 123 into a plan with exact files and checks.
```

In OpenCode, ask for the same skill by name; its `skill` tool loads the shared
instructions. For example:

```text
Use the plan-issue skill to turn issue 123 into a plan with exact files and checks.
```

`agents/openai.yaml` supplies short labels and starter prompts for Codex. It
must not contain workflow requirements missing from `SKILL.md`; OpenCode does
not need that metadata to execute the skill. Use the active client's available
shell, question, browser, and delegation tools. If a tool is missing, use an
equivalent capability or report the specific unverified part.

Discovery references: [Codex skills](https://learn.chatgpt.com/docs/build-skills)
and [OpenCode skills](https://opencode.ai/docs/skills/).

Shared locks live under `.agents/shared/`:

| Path                               | Role                                             |
| ---------------------------------- | ------------------------------------------------ |
| `conventional-commit/REFERENCE.md` | Commit message shape                             |
| `ai-contribution/REFERENCE.md`     | What agents may open vs what they must not merge |

## Catalog

| Skill                    | Load when                                                             |
| ------------------------ | --------------------------------------------------------------------- |
| `sync-upstream`          | Absorb or audit `AstrBotDevs/AstrBot` `master`                        |
| `create-astrbot-plugin`  | Create or repair a plugin (Star) package                              |
| `archify`                | Checkout-only diagram renderer; not shipped in sdist, wheel, or image |
| `audit-product`          | Baseline or module product audit; Chinese Markdown report + diagrams  |
| `security-audit`         | Source-grounded vulnerability hunt with independent validation        |
| `plan-issue`             | Issue or pasted request → research, clarify, file-path plan           |
| `simplifier`             | Smallest current change; YAGNI ladder; over-engineering delete-list   |
| `dashboard-ui`           | Build or modify the Dashboard (Vue 3 + Vuetify 4) UI                  |
| `ocr-project-review`     | Whole-repo OCR scan plus mandatory independent finding audit          |
| `semgrep-project-review` | Whole-repo Semgrep audit plus deduped confirmed-defect Issue filing   |

Do not add a skill that only restates `AGENTS.md`. Split a skill when a
second, independently loadable workflow appears.

## `SKILL.md` contract

Frontmatter uses a stable directory-matching `name` and a concise `description`
that leads with the capability and trigger. Add exclusions only to prevent
likely misrouting. Keep workflow detail in the body and load supporting
references when needed. The body may use these headings where helpful:

- **Locked** — toolchain or behavior the agent must not change
- **Open** — product design the agent may decide
- **Do not** — hard stops
- **Handoff** — other skills or files to cite, not paste
- **Verify** — focused commands after the change

Cite `AGENTS.md` and shared references. Do not inline those files.

Plugin sibling repositories should call this checkout's
`create-astrbot-plugin/scripts/check_plugin.py` rather than vendoring a copy of
the skill.

`archify` is a vendored MIT renderer from
[tt-a1i/archify](https://github.com/tt-a1i/archify). It is a checkout-only
maintainer tool: hatch sdist excludes `/.agents`, and `.dockerignore` drops
`.agents/` from the image build context. Keep the overlay in
`archify/REFERENCE.md` and the pin in `archify/VENDOR.json`. Agents load it
from `.agents/skills/archify/SKILL.md`. Verify with `make check-archify`; that
target is not part of `make check`.

`audit-product` writes working state under `.tmp/product-audit/` (gitignored)
and diagrams via `archify`. Reports stay out of `docs/` unless the user
explicitly asks to promote a figure. Security findings follow `SECURITY.md`.
Official-standard URLs live in `audit-product/references/standards.md`; cite
them, do not paste the specs. Independent disprove, variant sweeps, and GHA
bars live in `audit-product/references/verification.md`. Do not vendor
third-party audit skill trees into `.agents/skills/`.

`security-audit` is an AstrBot overlay of the MIT
[cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill)
(consumed through the `Xero-Team/security-audit-skill` fork at the commit pinned
in `security-audit/REFERENCE.md`). It hunts source-grounded trust-boundary
failures, validates every candidate with an agent that did not hunt it, and
writes runs under `.tmp/security-audit/run-<N>/` (gitignored). Coverage comes
from `coverage-ledger.json`, never from agent count. Every local check runs
target-controlled code in an OS sandbox (`bwrap`/`sandbox-exec`) with an empty
allowlisted environment; without one, the candidate stays `needs_validation`.
Findings go through `SECURITY.md`; the skill never files a public Issue or PR
and never writes exploit chains. Mechanical bars live in
`security-audit/scripts/security_audit.py`, tested by
`tests/unit/test_security_audit_ledger.py`; methodology and the AstrBot-specific
false-positive traps live in `security-audit/references/`. The overlay license
note is in `security-audit/SKILL.md`, the MIT notice in
`security-audit/THIRD_PARTY_NOTICES.md`, and the pin in
`security-audit/VENDOR.json`. Do not vendor the upstream tree, and do not merge
this workflow into `audit-product`, whose lab is a product-quality surface
rather than an attack target.

`plan-issue` writes working state under `.tmp/issue-plan/` (gitignored). Direct
planning is the default; use `init --skip-probe` and record the reason without
inventing a user waiver. A guided interview is optional when requested. A
planning-only request ends at validated `PLAN.md`; implementation authorization
already given in the conversation remains valid. Cite
`plan-issue/references/sources.md` for Superpowers, triage,
Spec Kit, grilling, JTBD, and related planning skills; do not vendor
those trees or their default `docs/superpowers/`, `tasks/`, `.specify/`,
or `dev/plans/` directories. The plan checker in
`plan-issue/references/verification.md` is the agent judgment pass;
`scripts/issue_plan.py validate` owns mechanical bars.

`simplifier` is an AstrBot overlay of the
[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) YAGNI
ladder (MIT). Invoke it as `simplifier` (`$simplifier` in Codex). Keep the
overlay in `simplifier/SKILL.md` and the pin in `simplifier/VENDOR.json`. Do
not install the upstream plugin, hooks, intensity levels, or companion
skills, and do not copy this skill into `.opencode/` or `.codex/`.

`dashboard-ui` is an AstrBot-authored overlay that fuses several MIT-licensed
Vue/Vuetify agent skills (`skilld-dev/vue-ecosystem-skills`, `vuejs-ai/skills`,
`agents-inc/skills`, `antfu/skills`) into this repository's Dashboard
conventions. Keep the workflow in `dashboard-ui/SKILL.md`, the library facts
and provenance in `dashboard-ui/REFERENCE.md`, and the Codex metadata in
`dashboard-ui/agents/openai.yaml`. It is not a verbatim vendor, so it has no
`VENDOR.json`; record absorbed sources and reviewed commits in
`REFERENCE.md`. Do not copy it into `.opencode/` or `.codex/`, and do not add
a second Vue/Vuetify skill that restates it. Verify it with
`make check-dashboard-ui` (or `node
.agents/skills/dashboard-ui/scripts/check-skill.mjs`), which checks the
frontmatter, headings, referenced paths, and pinned versions. The official
Vuetify MCP setup for OpenCode and Codex is documented in
`dashboard-ui/REFERENCE.md`; the local OpenCode client config lives in the
gitignored `.opencode/opencode.json`.

`ocr-project-review` wraps the Apache-2.0
[alibaba/open-code-review](https://github.com/alibaba/open-code-review) CLI.
Credentials come from its gitignored `.env` (`OCR_LLM_URL`,
`OCR_LLM_API_KEY`, `OCR_LLM_MODEL`); `scripts/ocr_skill.py install` creates a
dedicated OCR provider whose `api_key_cmd` re-reads that file, so the key is
not copied into `~/.opencodereview/config.json`. `run` executes `ocr scan`
over the whole repository with a generated rule that suppresses
compiler/lint/style findings, then writes normalized findings and a report
under a new `.tmp/ocr-project-review/<timestamp>/` directory. For large
repositories, `run --jobs 8` splits
reviewable files by module into up to eight balanced shards, merges the
results, and keeps a coverage table in the report. OCR findings are hypotheses:
every one must
receive a `confirmed`, `false-positive`, or `uncertain` verdict before
`finalize` writes `report-final.md`. Reporting is the default; the `issues`
command only drafts confirmed findings, and `issues --create` runs after the
user explicitly asks and targets `Xero-Team/AstrBot` with duplicate checks.
Related issues block creation unless reviewed; `--supersede NUMBER:DRAFT`
merges the original report into the new Issue and closes the original with a
link after the replacement exists. Security findings stay out of public Issues.
Do not vendor the upstream skill tree, edit project
`.opencodereview/rule.json`, or commit `.env`.

`semgrep-project-review` wraps the LGPL-2.1
[semgrep/semgrep](https://github.com/semgrep/semgrep) CLI. It runs through
`uvx --from semgrep==1.157.0 semgrep` with metrics off and explicit registry
packs (`p/python`, `p/typescript`, `p/security-audit`) plus
`semgrep-project-review/rules/astrbot.yml`. Newer local Semgrep builds can
crash `semgrep-core`, so `--engine auto` retries with the pinned
`docker.io/semgrep/semgrep:1.182.0` image. Semgrep's parser does
not understand Python 3.15 PEP 758 `except A, B:` clauses, so `run` mirrors the
worktree and rewrites those clauses to `except (A, B):` without changing line
numbers before scanning. Findings are normalized under
`.tmp/semgrep-project-review/<timestamp>/` and every one must receive a
`confirmed`, `false-positive`, or `uncertain` verdict before `finalize` writes
`report-final.md`. After the audit, `issues` searches open and closed Issues and
PRs, skips exact duplicates, and drafts confirmed non-security defects; `issues
--create` files them on `Xero-Team/AstrBot` with the `bug` template. Findings
with a security category, CWE/OWASP tag, or exploitable failure mode stay in
`security-findings.md` and use the private advisory channel. Do not use
`--config auto`, `--autofix`, the Pro engine, or the Secrets product, and do not
commit `.tmp/` output.
