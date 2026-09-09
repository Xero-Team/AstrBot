# Planning workspace

Use `scripts/issue_plan.py` from the checkout root:

```bash
uv run python .agents/skills/plan-issue/scripts/issue_plan.py init --issue 123
uv run python .agents/skills/plan-issue/scripts/issue_plan.py fetch --issue 123
uv run python .agents/skills/plan-issue/scripts/issue_plan.py status
uv run python .agents/skills/plan-issue/scripts/issue_plan.py validate
```

For a pasted request, use `init --slug <short-name>`. Workspaces live at
`.tmp/issue-plan/issue-<number>/` or `.tmp/issue-plan/local-<slug>/`.
They contain `manifest.json` (SHA, branch, request identity), optional
`ISSUE.md` / `issue.json`, and the required `PLAN.md`.
Research and question notes are optional; the validator does not require
a quiz or intermediate documents.

Use `--run-dir <path>` before the subcommand to select a workspace.
Resume when its request and SHA match. If HEAD changed, check whether the
plan's evidence is still valid before updating it. Do not overwrite an
unrelated plan with `init --force`.

The fetch helper targets `Xero-Team/AstrBot`. For additional issue research:

```bash
gh issue view <n> --repo Xero-Team/AstrBot --json title,body,comments,labels,url
gh issue list --repo Xero-Team/AstrBot --state all --search "<query>" --limit 20
```

Reading upstream provenance does not authorize posting there. Any new
Issue/PR follows `AGENTS.md` and `AI_POLICY.md`; planning does not imply
permission to post comments. A new feature needs a development Issue before
its PR under `GOVERNANCE.md`; a local plan can record that follow-up.

Find runtime owners from the architecture guidance linked by `AGENTS.md`.
Choose verification commands from the checkout's `Makefile` and nearest
tests; `make check` is not a complete CI-equivalent gate.
