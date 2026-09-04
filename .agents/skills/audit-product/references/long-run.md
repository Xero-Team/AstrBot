# Long-run protocol

A full-product audit does not fit one context window. The ledger is the
memory. Finished chapters stay on disk.

## Run identity

```text
<UTC YYYYMMDDThhmmssZ>-<shortsha>
```

Example: `20260904T120000Z-a1b2c3d`. `init` creates this. One worktree, one
active run, unless the user asks to fork a scope.

## Resume

At session start:

```bash
python .agents/skills/audit-product/scripts/audit_ledger.py status
python .agents/skills/audit-product/scripts/audit_ledger.py next
```

Then:

1. Read `manifest.json` (SHA, scope). If `HEAD` differs, start a new run.
2. Do **not** read `REPORT.md` or finished `CHAPTER.md` unless synthesizing
   or the user named that module.
3. Read only `modules/<current>/CHAPTER.md` if status is `in_progress`.
4. Continue from the first `pending` or `in_progress` module.
5. If `CURRENT.md` exists, treat it as a hint only; prefer `status` /
   `next` when they disagree.

Query instead of loading:

```bash
python .agents/skills/audit-product/scripts/audit_ledger.py list-findings --module authz
python .agents/skills/audit-product/scripts/audit_ledger.py list-findings --severity high
python .agents/skills/audit-product/scripts/audit_ledger.py scores --module authz
```

## Context budget

Per module, keep in the model:

- This skill's `SKILL.md` headings + the one module row from `REFERENCE.md`
- The dimension list (already loaded)
- Code and tests for **this** module
- At most a short finding index from the ledger

Do not paste ISO/ASVS catalogs, AGENTS.md, `references/standards.md` in
full, or other modules' chapters. Load only the standard **row** for this
module, then fetch that URL if needed.

If a module is too large (`platform`, `dashboard-ui`, `agent`):

1. Split internally into documented slices (e.g. adapter families).
2. Still one `module_id` and one chapter.
3. Record skipped slices as `未评估` with names, not silent omissions.

## Checkpoint

After each module:

1. `add-finding` / `diagram` events flushed
2. Independent disprove for `security`/`defect` at `confirmed`/`likely`
   (`references/verification.md`)
3. Variant sweep after the first confirmed security/defect, or an explicit skip
4. `score` events flushed
5. `CHAPTER.md` written with Spec vs Standards, pre-conclusion list
6. `module_status complete` or `blocked`
7. `validate` passes for that module
8. User-visible progress: module id, overall rating, open high+, next module

Stop the session cleanly at a checkpoint. Do not leave `in_progress` with
unwritten findings. Do not `score` before the disprove step.

Rewrite `.tmp/product-audit/<run-id>/CURRENT.md` (10–20 lines): SHA, next
`module_id`, open high+, last command actually run, whether the lab at
`http://127.0.0.1:6185` was up. Do **not** paste the lab password,
standards catalogs, design systems, or finished chapters into it. The
ledger `next` / `status` queries remain the source of truth; `CURRENT.md`
is only a cheap resume hint.

## Parallelism

Default is **sequential** in the catalog order.

Read-only explore subagents are allowed for inventory (file maps). They must
not write the ledger. The parent verifies every finding location before
`add-finding`. Never create findings from a subagent summary alone.
Disprove agents in `references/verification.md` are a second, **fresh**
read-only pass after the finding exists; they still do not write the ledger.

Do not run two writers against the same `audit.jsonl`. Do not launch a
fleet of hunters that append findings in parallel.

## Blocked vs skipped

- `blocked`: cannot finish without user input or a failing tool. Say what.
- `skipped`: user or scope excluded it. Reason required.
- Do not skip `authz`, `pipeline`, `agent`, `dashboard-api`, or
  `knowledge-base` in a full-product run without an explicit user decision.

## Synthesis gate

`REPORT.md` may be written only when `status` shows zero `pending` /
`in_progress` modules in scope. Pull counts and ratings from the ledger.
Re-read chapters only to quote, not to discover new findings. New issues
found during synthesis go back to the owning module as findings first.

## Failure of gates

If `pytest`, `make check`, or `make quality` cannot run, record a
`ops-supply-chain` or module `test-gap` finding with `confidence=confirmed`
for "gate not executed", and continue static review. Do not pretend the
gate passed.

## User interrupts

If the user changes scope mid-run, record skipped modules rather than
deleting the run. Keep IDs stable.

## Lab

Default origin is `http://127.0.0.1:6185` on this branch. Credentials
are in `REFERENCE.md` (acceptance-test only; never production). Record
in `CURRENT.md` whether the lab was up, without the password.
