# Security audit reference

Run contract, provenance, and the facts that the workflow assumes. Cite this
file; do not restate it in reports.

## Provenance and adaptation

This skill is an AstrBot overlay of
[cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill)
(MIT, Copyright 2025-2026 Cloudflare, Inc.), consumed through the
`Xero-Team/security-audit-skill` fork at commit
`c1c8a8c1471069fb0e188eeaff69b8e8db6564a8`.

This directory is an AGPL-3.0-or-later overlay of those MIT-derived portions.
The full upstream MIT permission notice is reproduced in
`THIRD_PARTY_NOTICES.md`, and `VENDOR.json` records the source repository, path,
commit, license, purpose, and every local patch. Keep both files when you change
the overlay.

Absorbed: source-first boundary/result gate; universal execution safety (every
local check runs in an OS sandbox with an empty allowlisted environment);
`confirmed` / `needs_validation` / `rejected` verdicts; adversarial independence
(a validator that did not hunt the candidate, and a fresh owner plus fresh
evidence for each re-attempt); coverage ledger as the coverage claim; prior-run
additivity; target-neutral reporting; severity from impact; "defense-in-depth
gaps are not vulnerabilities".

Cut or replaced: the ten domain companions (five AstrBot-oriented files
remain); the 1,600-line Node schema/ledger validators (one Python script with
unit tests); the descriptor-level artifact-promotion choreography (a bounded
parent-side copy rule remains); percent-encoded coverage IDs; fixed six-phase
names.

Do not vendor the upstream tree into `.agents/skills/`.

## Principals and assets

- **Dashboard account** (`root` / `operator` / `member`) — API scopes, step-up
  actions, config, plugins, backups; see `astrbot/core/auth/service.py` and
  `astrbot/dashboard/api/auth.py`.
- **WebChat user / guest** — chat runs over one socket; an unverified sender
  becomes `Subject.guest` (`astrbot/core/pipeline/waking_check/stage.py`).
- **IM sender** — platform-authenticated sender inside one config instance and
  UMO.
- **Plugin author** — in-process Python with full host authority once installed.
- **Dashboard Extension page** — sandboxed iframe with declared Actions only.
- **MCP peer / remote server** — untrusted tool results, resources, and
  metadata.
- **Model output** — untrusted input to handlers, tools, memory, and rendering.
- **OS user / process** — local sandbox peer, file owner, local-IPC caller.

Assets worth naming in a candidate: provider API keys and base URLs, Dashboard
JWT/TOTP/step-up state, chat history and conversation shares, knowledge-base
documents and vectors, plugin config and secrets, the agent process/host,
release and update authority, and operator-owned spend.

## Scope boundaries

`SECURITY.md` defines in-scope code and exclusions. Out of scope for findings:
upstream-only issues, third-party plugin defects unless the platform sandbox or
authorization boundary fails, self-inflicted exposure, dependency CVEs, and DoS
of a self-hosted instance. Record those as out-of-scope or hardening notes.

## Run layout and write isolation

```text
.tmp/security-audit/
  LATEST                      # newest run directory name
  run-<N>/
    run-metadata.json
    architecture.md
    coverage-ledger.json
    findings.json
    REPORT.md
    FINDINGS-DETAIL.md
    NEEDS-VALIDATION.md
    SENSITIVE.md              # only when critical/high needs detail out of REPORT
    agents/<id>/scratch/      # the only agent-writable area
    agents/<id>/artifacts/    # parent-promoted, regular, bounded files only
```

`run-metadata.json` records `run_id`, `repo`, `target`, `source_ref`, `profile`,
`scope_paths`, `budget`, `execution_policy`, `prior_runs`, `run_status`, and
`created_at_utc`. `source_ref` is
`{sha, dirty, modified_paths, modified_paths_omitted}`: `modified_paths` is
sorted, bounded, and contains only safe repository-relative names, and
`modified_paths_omitted` counts the rest. A dirty worktree must record at least
one modified path; a clean one must record none.

`--run-dir` and the `LATEST` pointer must resolve inside `.tmp/security-audit/`.

The parent is the only writer of shared files. Agents may write only their own
`scratch/`. After the agent process exits, the parent may copy a predeclared
regular file into that agent's `artifacts/`, with a per-file and total size cap;
reject absolute paths, `..`, symlinks, special files, and anything that changed
during the copy. Never glob a scratch tree or extract an archive into artifacts.

## Execution boundary

Every local check — first-party or plugin — runs target-controlled code only
inside `bwrap` (Linux) or `sandbox-exec` (macOS) with an empty allowlisted
environment (scratch-local `HOME`, `XDG_*`, `UV_*`, caches, `TMPDIR`/`TMP`/
`TEMP`), a read-only target and toolchain, scratch-only writes, no external
network, an ephemeral loopback port instead of `6185`, and explicit CPU,
memory, process, file-size, and wall-clock limits. `SKILL.md` owns the wording;
this file records that the requirement is universal, not plugin-only. A missing
sandbox or control is a `needs_validation` blocker, never a reason to run
unsandboxed.

## Profiles

| Profile    | Ledger granularity                            | Waves and critics                                                         | Verification                                                                       |
| ---------- | --------------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `quick`    | coarse: one all-in-scope subsystem dimension  | exactly one hunter wave and one final critic pass                         | one fresh verifier per candidate; it also signs the final record                   |
| `standard` | surface × boundary × subsystem × class        | waves until both the post-wave and the distinct final-clean critic accept | Phase 3 verifier and final record verifier are separate agents                     |
| `deep`     | adds lifecycle modes and per-subsystem splits | as `standard`, to a clean pass                                            | as `standard`, plus an independent second pass for prior same-source covered units |

A **scoped** run (named paths, one subsystem, or a diff) seeds units only for
in-scope surfaces and records everything else as `out_of_scope`. A scoped or
`quick` run is partial coverage and must say so.

Budget is a maximum number of delegated agent invocations, recorded as
`budget` (or `null`). Reserve the mandatory critics and a validation reserve
before assigning hunters. If the minimum cannot be funded, launch no agent,
set `run_status: "incomplete"` with `incomplete_reason:
"budget_cannot_fund_reconnaissance_and_reserves"`, and say no pass ran. If
candidates exceed the validation reserve, stop hunting, validate in fingerprint
order while the budget permits, keep the rest as unresolved ledger candidates,
and set `incomplete_reason: "validation_budget_exhausted"`. Never exceed a
user-set budget silently.

## Coverage ledger contract

File: `coverage-ledger.json`, a JSON array of units. Semantic fields:

| Field                                                 | Meaning                                                                            |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `coverage_id`                                         | stable ID, `^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$`; no wave, verdict, severity, or line |
| `canonical_refs`                                      | `surface`, `boundary`, `subsystem`, `attack_class`, optional `lifecycle`           |
| `surface` / `boundary` / `subsystem` / `attack_class` | must copy the matching `canonical_refs` value                                      |
| `starting_paths`                                      | repository-relative paths, nonempty                                                |
| `status`                                              | one of the states below                                                            |
| `agent_id`                                            | canonical owner, lowercase, safe directory name                                    |
| `reviewed_paths`                                      | exactly the union of the unit's check paths                                        |
| `checks`                                              | owned evidence entries                                                             |
| `result_fingerprints`                                 | candidate fingerprints linked to this unit                                         |
| `unresolved`                                          | blockers or deferral reasons                                                       |

`canonical_refs` is the single source of truth and the dedup key. It accepts no
fields beyond the five above, every top-level label must equal it field by
field, and `lifecycle` must appear on both or on neither. Two units that differ
only in their copied labels are rejected instead of counted as separate
coverage.

Optional bookkeeping: `wave`, `attempts`, `prior_status`,
`selected_attack_class_blocks`, `excluded_blocks`. Blocks are `FILE.md#section`
tokens; `excluded_blocks` entries are `{block, reason}`; a block may not be both
selected and excluded. The pre-rename `selected_companion_blocks` and
`ordinary_attack_class_block` fields are rejected.

A check is `{agent_id, reviewed_paths, invariant, method, result, artifact}`.
`method` is `source` (artifact `null`) or `local` (artifact under exactly
`agents/<check.agent_id>/artifacts/`). Keep `coverage_id` stable across runs for
the same source object; fail on duplicates and on two IDs for the same semantic
tuple.

State table (the validator enforces it):

| Status                                       | Owner    | Paths and checks | Fingerprints | Unresolved      |
| -------------------------------------------- | -------- | ---------------- | ------------ | --------------- |
| `planned`                                    | null     | empty            | empty        | empty           |
| `in_progress`                                | required | empty            | empty        | empty           |
| `blocked`                                    | required | nonempty         | empty        | nonempty        |
| `covered`                                    | required | nonempty         | empty        | empty           |
| `candidate`                                  | required | nonempty         | nonempty     | optional        |
| `deferred`, `not_applicable`, `out_of_scope` | null     | empty            | empty        | nonempty reason |

`attempts` archives a reopened terminal unit: the same unit fields with
`canonical_refs`, top-level labels, and `starting_paths` copied from the live
unit, plus `wave`, `status` (`blocked`/`covered`/`candidate`), and a nonempty
`reassignment_reason`. Attempt waves are strictly increasing and stay below the
live wave. Each attempt needs a fresh `agent_id` — never the live owner or an
earlier attempt's owner — and live evidence never copies from an archived
attempt: a check's owner may not be a prior owner and a `local` artifact may not
repeat an archived or live artifact. Re-hunting the same question with the same
agent is not a re-attempt.

Repository-relative paths reject a leading `/` or `~`, any `:` or `\`, `.`/`..`
and empty segments, trailing dots or spaces, control characters, and Windows
reserved device names (`con`, `prn`, `aux`, `nul`, `com1`-`com9`,
`lpt1`-`lpt9`). Agent and run IDs reject the same device names and a trailing
dot or space.

## Findings contract

File: `findings.json`, a JSON array sorted by fingerprint. The script
(`scripts/security_audit.py validate`) is the contract owner and enforces:

- `confirmed`: `root_cause`, `intended_behavior`, `trace`, `evidence`,
  `conditions`, `execution`, `remediation`, `severity`, `confidence`.
  `execution` has `attacker_perspective`, nonempty `payloads`, `instructions`,
  and `observed_result`. `severity` has likelihood, impact, and
  `overall_severity`, where overall rank cannot exceed impact rank.
- `needs_validation`: `claimed_root_cause`, `trace`, `evidence`, nonempty
  `blockers`, and a `validation_plan` with at least one nonempty `local` or
  `deployment` field. No severity, execution, remediation, reason, or confirmed
  root cause.
- `rejected`: `claimed_root_cause`, `trace`, `evidence`, `reason`. No severity,
  execution, remediation, blockers, or validation plan.

A multi-step trace starts at `entrypoint`, ends at `sink`, and labels the middle
`propagation`; a one-entry trace is `entrypoint` or `sink`. All paths are
repository-relative with no absolute prefix, `..`, or backslash. Every
fingerprint in a record must be linked from a ledger unit, and a complete run
cannot leave a `candidate` fingerprint without a record.

## Severity anchors

- **critical** — unauthenticated code execution in the backend host, full
  database or provider-key access, or takeover of arbitrary Dashboard accounts.
- **high** — Dashboard/step-up auth bypass, cross-user or cross-tenant read or
  write, stored Dashboard script execution, plugin code crossing into host
  authority, or unauthenticated remote stop of a shared bot.
- **medium** — real boundary violation with limited blast radius, uncommon
  preconditions, or a narrow resource set.
- **low** — non-secret internals; sustained effort for minimal gain.
- **informational** — confirmed minimal impact, useful as a prerequisite.

The high/medium discriminator: does the demonstrated result fully defeat an
explicit control for an action with real consequences, or only weaken it?

## Prior runs

Multiple runs are additive; one run does not exhaust the target. Compare current
source, not just a prior SHA. Carry a prior `confirmed` record only when its
relevant source and conditions are unchanged and its evidence still meets this
contract: same fingerprint, linked to a current `planned` unit, excluded from
hunting by fingerprint only, then re-verified. Changed source becomes current
revalidation work. Prior `needs_validation`, `deferred`, `blocked`,
`out_of_scope`, and rejected claims never suppress a current unit.

## Report shape

`REPORT.md`: run profile, scope, budget spent versus planned, source ref,
execution boundary statement, prior-run use, deferred/out-of-scope coverage;
one posture summary; a confirmed table; per-finding source, principal,
target-native bounded reproduction, conditions, result, impact, priority
rationale, and smallest fix; a separate `NEEDS VALIDATION` table without
severity; hardening notes; coverage counts and the critic result.

`FINDINGS-DETAIL.md`: for each confirmed medium/high/critical record, the
complete trace, dummy principal/resource, native input or fixture, bounded
instructions, observed output, invariant, conditions, remediation, and
regression case.

`NEEDS-VALIDATION.md`: source trace, evidence, exact blocker, affected
boundary, and each applicable local or owner-observed plan. No severity, no
live-probe instructions.

Keep critical/high reproduction detail in `SENSITIVE.md` and a short
non-exploitable summary in `REPORT.md`. Report language follows the request;
paths, identifiers, and commands stay verbatim.
