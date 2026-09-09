# Resume and checkpoint an audit

The ledger is durable memory. Keep finished chapters on disk until synthesis
or a request concerning that module.

```bash
uv run python .agents/skills/audit-product/scripts/audit_ledger.py status
uv run python .agents/skills/audit-product/scripts/audit_ledger.py next
uv run python .agents/skills/audit-product/scripts/audit_ledger.py list-findings --module authz
uv run python .agents/skills/audit-product/scripts/audit_ledger.py scores --module authz
```

Read the manifest for SHA and scope. Resume a matching run; if HEAD changed,
start a new run and identify the drift. Read only the current module's chapter,
relevant standards, code, tests, and a short finding index.

Finish one module at a time. A large module may have named internal slices;
record which were inspected and which remain unassessed. After each module:

1. Flush findings and diagram records.
2. Verify claims and relevant variants per [verification.md](verification.md).
3. Write scores, chapter conclusions, and module status.
4. Validate the ledger and report material progress.

An optional `CURRENT.md` can hold the SHA, next module, open high-impact
findings, last check, and lab availability. Keep secrets out. The ledger's
`status` / `next` overrides this resume hint.

Only one writer updates `audit.jsonl`. Read-only research/review agents may
return evidence; the parent verifies citations before recording findings.

Use `blocked` for a module that cannot finish and `skipped` for an explicit
scope exclusion, with reasons. Missing tools or unrun gates are verification
limitations; record a product defect only when evidence establishes one.
Continue independent static review.

On a scope change, preserve IDs and history, and record exclusions. Write
`REPORT.md` after no in-scope module remains pending/in-progress; derive
counts and ratings from the ledger. New findings discovered during synthesis
return to their owning module first. Persist checkpoints without treating them
as a reason to end an unfinished authorized audit.
