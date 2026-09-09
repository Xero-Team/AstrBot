# Continue an upstream integration

Use $sync-upstream to execute the integration scope below on a feature branch.
Resume from the decision ledger and current Git state; query specific SHAs
instead of loading the whole ledger. Preserve one upstream commit per
implementation commit, its author, subject, and provenance.

Resolve routine conflicts, run the relevant checks, and update the cursor only
when the interval is complete. Follow AGENTS.md for contribution boundaries.
Report the resulting commits, skipped/deferred work, checks, and residual risk.

Integration scope: <reviewed plan or upstream interval>
