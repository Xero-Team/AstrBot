# Review a plan

Run `scripts/issue_plan.py validate` after `PLAN.md` exists. It checks the
document structure, a source citation in Current behavior, task dependencies,
existing Modify paths, placeholders, and the manifest SHA. It requires no quiz
or research sidecars. Citation accuracy still needs the agent's review.

Review what the script cannot establish:

- Every requested outcome maps to a task or an explicit scope decision.
- Current behavior cites inspected code; hypotheses and assumptions are labeled.
- Files and symbols exist, and tasks use current owners without restoring
  removed contracts or weakening repository invariants.
- Each task has observable acceptance and a command that exercises the
  affected behavior. For bugs, it catches the reported symptom.
- Relevant call sites, tests, bilingual docs, and OpenAPI generation are included.
- Alternatives and added dependencies have a concrete reason; unrelated
  restructuring does not enter the task.
- Material unresolved choices are visible rather than silently assumed.

Report blockers that would prevent execution separately from optional
improvements. Fix the plan's omissions before handing it off. Return its path;
continue implementation if already authorized, otherwise finish the planning
request without adding a mandatory approval ceremony.
