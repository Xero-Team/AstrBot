# Repository skills and MCPs

Skills live in `.agents/skills/`. Their short descriptions support discovery;
load a `SKILL.md` only for a matching task, then read supporting references
as needed. Keep shared repository policy in `AGENTS.md`, detailed checkout
facts in `.agents/shared/checkout/REFERENCE.md`, and skill-specific procedures
beside their skill.

| Skill                                                   | Use for                                              |
| ------------------------------------------------------- | ---------------------------------------------------- |
| [sync-upstream](sync-upstream/SKILL.md)                 | Review or integrate upstream commits with provenance |
| [create-astrbot-plugin](create-astrbot-plugin/SKILL.md) | Build or repair a standalone AstrBot plugin          |
| [archify](archify/SKILL.md)                             | Render validated standalone HTML diagrams            |
| [audit-product](audit-product/SKILL.md)                 | Audit product quality, security, or completeness     |
| [plan-issue](plan-issue/SKILL.md)                       | Write a code-backed implementation plan              |

## Writing skills

State the outcome, non-obvious constraints, and useful commands. Avoid repeating
`AGENTS.md`, generic tutorials, mandatory Q&A, or fixed report/check counts
without a correctness reason. Descriptions should distinguish tasks; headings
and extra files are optional. Preserve existing authorization and invocation
policy. Validate only what the change needs.

This design follows the [GPT-6 Astra prompting guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices):
audit conflicting instructions, carry authorized work through, and calibrate
verification. The skills remain usable with other capable models.

## Working artifacts

- Planning: `.tmp/issue-plan/`; only `PLAN.md` is required by its validator.
- Product audits: `.tmp/product-audit/`; query the ledger to resume.
- Diagrams: `.tmp/archify/`; keep the vendored renderer and generated
  artifacts out of product builds. Vendor provenance is in
  [archify/REFERENCE.md](archify/REFERENCE.md); check changes with
  `make check-archify`.
- Plugins: prefer a sibling repository and call this checkout's checker
  rather than copying the skill.

Commit/PR work uses [AI contribution guidance](../shared/ai-contribution/REFERENCE.md)
and the [commit reference](../shared/conventional-commit/REFERENCE.md).
Security findings follow `SECURITY.md`.

## Development MCPs

The tracked defaults in `.codex/config.toml` and `.opencode/opencode.json`
keep optional servers disabled, so ordinary sessions do not load their tool
catalogs. Enable only a server needed by the task with `enabled = true`
(Codex TOML) or `"enabled": true` (OpenCode JSON), and reconnect/restart
the client. Local enablement edits need not be committed.

| Server      | Configured client | Enable for                      |
| ----------- | ----------------- | ------------------------------- |
| vuetify-mcp | Codex, OpenCode   | Vuetify component API questions |
| context7    | OpenCode          | External library documentation  |
| playwright  | OpenCode          | Interactive browser inspection  |

For SQLite inspection, use `sqlite3 -readonly <explicit-database-path>`;
there is no development MCP attached to runtime data. Prefer an isolated
database for experiments. The Playwright server uses `npx` from PATH.

Only these two configuration files are tracked; other local agent metadata
stays ignored. Never commit credentials or machine-specific paths.
These settings configure coding clients; AstrBot's runtime MCP integration
and user-configured runtime Skills are separate product features.
