---
name: security-audit
description: >
  Hunt source-grounded security vulnerabilities in this AstrBot checkout,
  validate them independently, and report confirmed boundary failures with
  exact evidence. Use for a requested security audit, vulnerability research,
  or pen-test of a named surface. Not for product-quality scoring, scanner
  triage, dependency CVE review, or plugin creation.
license: AGPL-3.0-or-later
compatibility: >
  Requires the Xero-Team/AstrBot checkout, Python 3.15+, git, and a client that
  can delegate subagents. Local execution uses only the already-synced
  environment and a temporary ASTRBOT_ROOT under .tmp/.
metadata:
  author: Xero-Team
  checkout: Xero-Team/AstrBot
  based_on: cloudflare/security-audit-skill (MIT), via Xero-Team fork
  upstream_commit: c1c8a8c1471069fb0e188eeaff69b8e8db6564a8
---

# Security audit this AstrBot checkout

Find vulnerabilities that violate a real trust boundary in first-party code,
then give maintainers the source evidence, the minimum safe reproduction, the
priority, and the smallest effective fix. This is a defensive, source-first
workflow: a candidate without a concrete affected principal, resource, or
security outcome is not a confirmed finding.

Read `SECURITY.md` before starting. Vulnerability details stay in the private
channel; this skill never files a public Issue or PR for a finding.

## Operating modes

This skill is guidance by default. Loading it does not authorize a full audit
or file creation.

- **Guidance** — security questions, focused reviews, methodology, triage of an
  existing finding, or one named surface. Use the relevant sections only. Do not
  create a run directory or write audit artifacts unless asked.
- **Full audit** — the user explicitly asks to audit or pen-test this codebase,
  asks for a full/comprehensive/end-to-end security review, or requests report
  artifacts. Run the complete workflow and write the run files.

If the request could mean either, ask one focused question before creating
files. A named module with "review the security of X" is a scoped full audit,
not a product-quality audit.

## Locked

- Findings go through `SECURITY.md`. Do not open a public Issue or public PR for
  a vulnerability, and do not ask an agent to do so.
- Do not write exploit chains, weaponized payloads, persistence, lateral
  movement, or post-exploitation material. Record the minimum input that proves
  the boundary result and stop.
- Do not probe a live deployment, the audit lab, external providers, IM
  platforms, MCP servers, or any shared service. Do not send traffic to
  `127.0.0.1:6185`; that is `audit-product`'s product lab, not an attack target.
- Run target code only under the execution boundary below. If a required
  control is unavailable, keep the candidate as `needs_validation`; do not
  substitute a live check or a harder guess.
- Only the parent writes shared run files. Delegated agents write only under
  their own `agents/<id>/scratch/`. Never let target code write `.tmp/` outside
  its scratch, `data/`, the repository, or another agent's directory.
- Do not edit product source while auditing. This skill reports; a separate
  authorized change implements fixes.
- Do not vendor, copy, or re-host the upstream skill tree. Cite
  `REFERENCE.md` and the pinned upstream commit instead.
- Do not report third-party plugin defects, dependency CVEs, or self-inflicted
  exposure (`0.0.0.0` without protection) as product vulnerabilities; see
  `SECURITY.md` scope and the hardening rule below.

## Open

- Scope: whole checkout, named modules, one subsystem, or a diff between two
  refs. Default to the requested surface, not the whole repository.
- Profile: `quick` / `standard` / `deep` (see `REFERENCE.md`, "Profiles"). The
  default is `standard`.
- Whether a candidate needs a local check at all. Static evidence is the
  default; run only the narrowest check that settles the claim.
- Report language: follow the user's request language (default Simplified
  Chinese for a Chinese request). Keep paths, identifiers, JSON keys, and
  command strings verbatim.

## Setup

Run `uv run python .agents/skills/security-audit/scripts/security_audit.py init`
with the chosen profile and scope. It creates `.tmp/security-audit/run-<N>/`
(gitignored), records the full HEAD SHA and worktree dirtiness, and writes:

```text
run-metadata.json   # run identity, profile, scope, source ref, status
architecture.md     # stub; the parent replaces it with the Phase 1 map
coverage-ledger.json
findings.json
agents/<id>/scratch/   # the only agent-writable area
```

Phase 4 adds `REPORT.md`, `FINDINGS-DETAIL.md`, `NEEDS-VALIDATION.md`, and
`SENSITIVE.md` (only when critical/high detail is kept out of `REPORT.md`).

Use `security_audit.py status` to resume and `validate` after every ledger or
findings change. For a dirty worktree, review the current files but record that
the source ref is dirty and which files were modified; never treat generated or
locally modified code as a clean commit.

## Execution boundary

Source inspection is read-only. A local check is allowed only when all of these
hold:

- it uses the already-synced environment (`uv run --no-sync` or an existing
  virtualenv); no dependency install, sync, fetch, or update;
- it uses a temporary runtime root: `ASTRBOT_ROOT=<scratch>/root` and
  `TMPDIR=<scratch>/tmp`, never the developer's `data/`;
- it has no external network; mock provider, MCP, IM, and webhook calls;
- it is bounded: a single test, a minimal harness, a small fixture, or one
  deterministic race/sequence, with a timeout;
- its writes stay in `<scratch>/`; the parent may copy a predeclared, regular,
  size-bounded scratch file into `agents/<id>/artifacts/` after the process
  exits. Never promote a symlink, directory, FIFO, socket, or executable.

Executing untrusted plugin code needs an OS sandbox. If `bwrap` (Linux) or
`sandbox-exec` (macOS) is unavailable, or the check would escape the boundary,
do not run it: record the exact blocker in `needs_validation`.

## Core principles

### Require a boundary and a result

For every candidate, name the lower-trust principal, the accepted input or
action, the control that should stop it, the crossed boundary, the affected
principal or resource, and the concrete observed or owner-observable result. Do
not elevate a missing best practice, guessed deployment behavior, a generic
crash, a scanner match, or self-impact into a finding.

AstrBot principals are not interchangeable: Dashboard account/root/operator,
WebChat user/guest, IM sender, plugin author, MCP peer, model output, and local
OS user. State which one starts and which one is crossed.

### Respect source visibility

Default bind address, TLS verification, MCP private-network denial, proxy
trust, reverse-proxy behavior, IM platform identity, browser policy, and
deployment topology are real controls. If a required fact is outside the
repository, do not assume its presence or absence. Use `needs_validation` with
the exact missing fact and a safe owner-observed or local plan.

### Separate priority from certainty

Only `confirmed` records receive severity. `needs_validation` is a
source-grounded hypothesis blocked by one exact unresolved fact, not a
low-confidence vulnerability; it has no severity. Calibrate with:

- **critical** — an unauthenticated network actor gains code execution in the
  backend host, full database or provider-key access, or takeover of arbitrary
  Dashboard accounts.
- **high** — a principal fully defeats an explicit control: Dashboard or
  step-up authentication bypass, cross-user/tenant read or write, stored script
  execution affecting other Dashboard users, plugin code crossing into host
  authority, or an unauthenticated remote stop of a shared bot.
- **medium** — a real boundary violation with limited blast radius, uncommon
  preconditions, or a narrow resource set.
- **low** — non-secret internals or an effect requiring sustained effort for
  minimal gain.
- **informational** — a confirmed minimal-impact observation, useful mainly as
  a prerequisite.

Overall severity cannot exceed demonstrated impact. If you cannot state the
concrete damage, the severity is lower than it feels.

### Recommend the smallest effective fix

For each confirmed finding, name the invariant the code must enforce and the
narrowest source change at the last trusted decision point. Prefer
repository-relative changes and a regression test over generic hardening
advice. The audit describes fixes; it does not apply them.

### Hardening is not a finding

If another layer already prevents the attack, the missing layer is a hardening
note, not a vulnerability. Fork invariants in `AGENTS.md` (bind address, TLS
verification, MCP private-network deny, fail-closed `authorize()`, DOMPurify,
`defusedxml`, command identity, config revisions) are different: they are
product claims, so breaking one stays a candidate finding even when another
layer blocks the attack today. Demonstrated impact still decides whether it is
`confirmed` or `needs_validation`.

## Workflow

### Phase 1 — Reconnaissance and coverage

Launch parallel read-only research agents (the `explore` agent in OpenCode, or
an equivalent read-only researcher) for: product and local operation;
principals, authority, and controls; entry surfaces and sinks; and local
execution/deployment visibility. They return facts with repository-relative
paths, not files. Synthesize `architecture.md` with principals, surfaces, trust
boundaries, the strongest source-visible control on each, starting paths, and
prior-run gaps.

Then derive the coverage ledger. One unit is one material combination of
surface, boundary, subsystem, and attack class at the profile's granularity.
Every in-scope surface gets a unit; excluded surfaces become `out_of_scope`
units with a reason, never silent omissions. Use the schema and state table in
`REFERENCE.md`. Run `security_audit.py validate` after seeding.

If prior runs exist, read their ledger and findings. Carry an unchanged
same-source `confirmed` record only with the same fingerprint into a current
`planned` unit and re-verify it. Changed source does not inherit its old
verdict. Prior `needs_validation`, `deferred`, `blocked`, `out_of_scope`, and
rejected claims are priority input, never suppression keys. Never use an old
confirmed finding as an exemplar that anchors the hunt.

### Phase 2 — Hunting waves

Assign `planned` units to fresh general-purpose agents (the `general` agent in
OpenCode). Give each hunter, in this order: role; `architecture.md` verbatim;
assigned units and starting paths; the selected attack-class blocks from the
domain references copied verbatim (not names alone); excluded blocks with
reasons; the hunting method and candidate gate from
`references/hunting-prompt.md`; prior same-source exclusions by fingerprint
only; and the scratch paths plus the structured-result contract.

Hunters read source, may run one bounded local check, and return exactly one
JSON object:

```json
{
  "units": [
    {
      "coverage_id": "assigned id",
      "disposition": "covered|candidate|blocked",
      "reviewed_paths": ["repo/relative/path"],
      "checks": [
        {
          "agent_id": "lowercase-owner",
          "reviewed_paths": ["repo/relative/path"],
          "invariant": "control checked",
          "method": "source|local",
          "result": "what settled it",
          "artifact": "agents/<agent-id>/artifacts/file for local, null for source"
        }
      ],
      "result_fingerprints": [],
      "unresolved": []
    }
  ],
  "candidates": [],
  "hardening": [],
  "uncovered": []
}
```

Consolidate candidates by fingerprint, then by root cause. Immediately after
each wave, spend one fresh read-only coverage critic (`explore` in OpenCode)
that proposes missing units, reopened units, and resolved prior leads; it
proposes coverage, not findings. Accept only in-scope, source-backed units,
deduplicate by `coverage_id`, archive reopened terminal evidence under
`attempts`, and increment the wave. In `standard` and `deep`, another distinct
final-clean critic must also return no accepted work before stopping. A unit the
budget or profile cannot reach is `deferred` with a reason; agent count is not
coverage.

### Phase 3 — Independent validation

Give every unique candidate to a fresh general-purpose verifier that did not
hunt it. The verifier receives only the candidate, its linked ledger checks and
artifact paths, the architecture facts needed to interpret the path, the
relevant domain validation rules, and prior records with the same fingerprint.
It must try to refute the claim: re-read every cited line, reconstruct the
strongest control on the path, and reproduce the minimum local result only if
it can do so safely. It returns `confirmed`, `needs_validation`, or `rejected`
with a schema-shaped record.

A verifier may promote to `confirmed` only after independently establishing the
complete path and a bounded observed result. Demote to `needs_validation` when
one decisive deployment or runtime fact is unknown. `rejected` requires source,
local behavior, or an impossible prerequisite that refutes the claim.
`needs_validation` is never a parking place for a speculative idea.

### Phase 4 — Structured output, final record verification, and report

Write `findings.json` sorted by fingerprint, validate it, then have one fresh
read-only verifier per retained record check the record itself (not the hunter
prose). In a `quick` run the Phase 3 verifier also signs the record; every other
profile keeps the two passes separate. A material replacement — a stronger
verdict, a different root cause, trace, input, result, impact, or severity —
needs another independent verifier that did not hunt, validate, or propose the
replacement. If independence or budget is unavailable, remove the disputed
record, keep the ledger unit as an unresolved candidate, and set the run
`incomplete`.

Derive `REPORT.md`, `FINDINGS-DETAIL.md`, and `NEEDS-VALIDATION.md` from the
verified records and ledger. Never let prose change a verdict, severity,
blocker, or observed result. An incomplete run reports only verified records
and lists every unvalidated fingerprint as a lead, never as a finding.

## Verdicts

| Verdict            | Required                                             | Forbidden                                   |
| ------------------ | ---------------------------------------------------- | ------------------------------------------- |
| `confirmed`        | complete trace, bounded observed result, severity    | blockers, `claimed_root_cause`, plan only   |
| `needs_validation` | exact blocker for one decisive fact, validation plan | severity, execution, remediation, rejection |
| `rejected`         | reason grounded in source or local behavior          | severity, execution, blockers, validation   |

Every record has a stable fingerprint, title, description, and
repository-relative trace/evidence. Only `confirmed` may carry severity.

## Handoff

Load only what the current step needs:

- Run contract, profiles, state table, severity anchors, provenance:
  `REFERENCE.md`
- Hunting prompt, candidate gate, local-check rules: `references/hunting-prompt.md`
- Attack classes and validation rules per domain:
  `references/web-and-dashboard.md`, `references/agent-and-llm.md`,
  `references/client-side.md`, `references/data-and-lifecycle.md`,
  `references/supply-chain.md`
- Scanner leads (optional): `ocr-project-review`, `semgrep-project-review`.
  Their reports are hypotheses, not findings.
- Product-quality scoring and the live lab: `audit-product`. Do not duplicate
  its ISO 25010 report or treat its lab account as a target.
- Disclosure channel: `SECURITY.md`. Repository invariants: `AGENTS.md`.
- Architecture charts, only if requested: `archify`.

## Do not

- Present checklist deviations, defense-in-depth gaps, or scanner matches as
  findings.
- Assign severity to `needs_validation` or let overall severity exceed impact.
- Test a live or shared service, use real credentials or user data, or run
  stress/saturation tests.
- Write an exploit chain, persistence, or post-exploitation material.
- Let a hunter or verifier write shared files, target source, or another
  agent's directory.
- Claim complete coverage from agent count, a clean critic on a partial ledger,
  or a `quick`/scoped run.
- Put an unvalidated candidate into `findings.json` under any verdict.
- File a public Issue or PR, or paste secrets, tokens, session IDs, or PII into
  a report.

## Verify

```bash
uv run python .agents/skills/security-audit/scripts/security_audit.py status
uv run python .agents/skills/security-audit/scripts/security_audit.py validate
uv run pytest tests/unit/test_security_audit_ledger.py
```

A finished `standard` run has every unit in a terminal state, every retained
record past final record verification, `validate` green, and every
deferred/out-of-scope gap disclosed in `REPORT.md`. `validate --strict` fails
unless `run_status` is `complete`.
