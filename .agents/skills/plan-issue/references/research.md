# Research a change

Read the request and prior decisions, then trace the relevant runtime owner,
callers, tests, configuration, and docs. Search by domain terms and symbols,
not only the ticket's wording. An empty search is not proof of absence;
check an alternate term or surface before concluding behavior is missing.

Research should establish:

- Current behavior: trigger, code path, and observable result, with actual
  `path:line` evidence.
- Requested behavior and the smallest current design that can provide it.
- Existing implementation or prior rejection, where relevant. Check repository
  invariants, nearby Git history/changelog, and related Issues; query the
  upstream ledger only for upstream-derived work.
- Affected callers, contracts, tests, generated artifacts, and bilingual docs.
- Unresolved facts or choices that change the approach.

For a bug, identify a command or existing test that can reproduce the reported
symptom before settling on a cause. Distinguish a traced explanation from a
hypothesis, and report whether the check actually ran.

If the behavior already exists, explain where and assess the remaining gap.
If a prior decision conflicts with the request, explain the conflict and
continue whatever remains in scope. Keep vulnerability details private per
`SECURITY.md`; a private remediation plan remains possible when requested.

Put concise research in the plan's Current behavior section. Use
`RESEARCH.md` only when substantial evidence is useful for resuming or
reviewing the work. Match the user's language; preserve paths and symbols.
Do not manufacture reports, hypothesis counts, or extra research lanes for a
bounded change.

For material uncertainty, see [probe.md](probe.md); otherwise write the plan.
