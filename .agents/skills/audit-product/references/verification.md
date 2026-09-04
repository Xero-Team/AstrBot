# Independent verification, variants, and checkpoints

Load this file before scoring a module. It is process, not a second quality
model. Subagents stay **read-only** toward `audit.jsonl`; only the parent
writes findings.

Do not construct exploit payloads, working PoCs, or attack scripts. A
concrete attack scenario is: who, which code path, what is gained. Put any
reproduction detail in `SENSITIVE.md`.

## Independent disprove

After `add-finding` for `kind` in `{security, defect}` and `confidence` in
`{confirmed, likely}`, and **before** `score`:

1. Spawn one research agent **that did not write the finding**. One finding
   per agent. Parallelize independent findings.
2. Give it only: `finding_id`, title, `location`, claimed data flow / sink,
   and the frozen SHA. Do not paste the chapter.
3. Its job is to **disprove** the finding. It must read every cited
   `path:line`.
4. It returns exactly one of:
   - `CONFIRMED` — the cited code does what the finding claims
   - `CORRECTED` — field + old value + new value (wrong line, overstated
     impact, missed mitigation)
   - `REJECTED` — the data flow or impact is false, with code evidence
5. The parent applies `CORRECTED` / `REJECTED` to the ledger (`add-finding`
   replacement or `delete` + new id; never rewrite history in-place) before
   scoring. Downgrade `confirmed` if the verifier could not finish the
   trace.

Same-session parent reread is not a substitute. Inventory explore agents
still must not create findings from summaries alone (`long-run.md`).

Do **not** launch a Cloudflare-style fleet of 8–12 hunters that write the
ledger. Hunt parallelism is read-only mapping only.

## Variant sweep

After the first `confirmed` `security` or `defect` in a module:

1. Name the **root cause** (why it is wrong), not the local identifier.
2. Search other owners of the same pattern family: adapter parsers, provider
   HTTP clients, tool handlers, Dashboard `v-html` sinks, workflow `run:`
   blocks.
3. Confirm or rule out each candidate against the same bar as the original.
   A look-alike with a working control is not a finding.
4. Assign variants to the **runtime owner** module (`REFERENCE.md`). Mention
   the seed finding in `related_modules` / `supersedes` as appropriate.

Skip the sweep when the finding is unique to one generated file or a
single config key, and say so in the chapter. Do not search only the
module where the seed appeared.

External methodology (cite, do not vendor): Trail of Bits variant-analysis
<https://github.com/trailofbits/skills/tree/main/plugins/variant-analysis>.

## Pre-conclusion checklist

Before `module_status complete` / `blocked`:

- Files actually read (paths, not glob counts)
- Each core dimension: rated or `未评估` with reason
- Module-checklist bullets: clean / dirty / skipped
- Independent disprove: done / not applicable (no security|defect at
  `confirmed`/`likely`)
- Variant sweep: done / not applicable / deferred with names
- Spec vs Standards blocks present in `CHAPTER.md`
- `validate` passes for this module's events

Record the list in `modules/<id>/CHAPTER.md` (测试/门禁 + 未评估). A
checkpoint without it is incomplete.

## Hardening vs finding

If layer A already prevents the attack, missing layer B is a hardening
note (`kind=positive` or `severity=info`), not a `security` finding.
Fork invariants in `AGENTS.md` (bind address, TLS verify, MCP
private-network deny, `authorize()` fail-closed, DOMPurify, defusedxml)
stay **findings** when broken: they are product claims, not optional
depth.

OWASP Top 10 / LLM Top 10 / Agentic Top 10 are **overlays**, not bug
lists. A missing header that another layer covers is not `high`.

## GitHub Actions (when `ops-supply-chain` is in scope)

Threat model: an **external** actor without write access (fork PR, issue,
comment). Do not flag `workflow_dispatch` / protected-branch `push` as
exploitable by that actor.

For each workflow finding record, in non-exploitable form:

- `entry_point` — event
- `mechanism` — expression-in-`run:`, fork checkout, config poisoning,
  agent env-var intermediary
- `impact` — token, write, secrets, agent with elevated tools
- `conditions` — permissions, sandbox, allowlist

Local checklist (load the matching `standards.md` rows if citing):

1. `pull_request_target` plus checkout of fork code
2. `${{ github.event.* }}` inside `run:` (not `if:` / `with:`)
3. `issue_comment` commands without `author_association`
4. Unpinned **third-party** actions on jobs that hold secrets or write
   tokens (do not flag first-party `actions/*` version tags)
5. Workflow loads `AGENTS.md` / `Makefile` / hooks from PR content
6. Agentic CI actions: attacker data in `env:` that the prompt reads,
   even when the prompt itself has no `${{ }}`

Cite, do not vendor:

- <https://github.com/getsentry/skills/tree/main/skills/gha-security-review>
- <https://github.com/trailofbits/skills/tree/main/plugins/agentic-actions-auditor>

## Skill and plugin instruction security

When the module is `skills` or `star`, treat `SKILL.md` / Dashboard
Extension assets as untrusted **to the operator who installs them**.
Documented attack patterns in a security skill are not injection.
Misaligned description vs instructions, undeclared network exfil in
bundled scripts, and config-poisoning (`~/.agents/`, hooks) are.

Cite, do not vendor:
<https://github.com/getsentry/skills/tree/main/skills/skill-scanner>

## Live Dashboard lab

Default audit logs into the current-branch lab in `REFERENCE.md`
(`http://127.0.0.1:6185`, username `astrbot`, acceptance-test password).
That password is lab-only: never production, never a shipped product
default, never pasted into `REPORT.md`. If the origin is down, start
this worktree and record the command; if it is a different SHA, say so.

## Optional live Dashboard / interface passes

Do not vendor these trees. Login to the lab is default. CWV / axe-core /
agent-usability run only when the user asked or a scan is already
running; otherwise `未评估`.

| Pass                         | Catalog ids           | Cite                                                                                |
| ---------------------------- | --------------------- | ----------------------------------------------------------------------------------- |
| Desktop lab CWV              | `cwv`                 | <https://web.dev/articles/vitals>                                                   |
| Sampled axe-core WCAG        | `wcag-22`, `axe-core` | <https://www.w3.org/TR/WCAG22/> ; <https://github.com/snapsynapse/skill-a11y-audit> |
| Agent-facing SDK/MCP/Actions | `agent-usability`     | <https://github.com/serpapi/skills/tree/main/skills/agent-usability-test>           |

Do not load SEO suites, uxuiprinciples APIs, TestMu SmartUI, or
alirezarezvani regex a11y `--fix`. Chrome DevTools MCP missing is
`未评估`, not a hard stop.
