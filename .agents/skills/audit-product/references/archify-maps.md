# Archify maps for a product audit

Load `.agents/skills/archify/SKILL.md` before authoring. Facts come from
current code at the frozen SHA. Use `schema_version: 2`. Author
`meta.locale: "zh-CN"` and Simplified Chinese copy. Keep code identifiers
verbatim.

Write IR under `.tmp/product-audit/<run-id>/diagrams/<name>.json`, deliver
HTML beside it, and also keep the archify working copies under
`.tmp/archify/` if the renderer expects that tree.

```bash
node .agents/skills/archify/bin/archify.mjs doctor
node .agents/skills/archify/bin/archify.mjs validate <type> <ir.json> --quality showcase --json
node .agents/skills/archify/bin/archify.mjs deliver <type> <ir.json> <out.html> --quality showcase --json
```

Record each success with `audit_ledger.py diagram`. Skip `visual-check` when
Playwright cannot run; say so in the appendix.

## Required for a full-product run

| File stem           | Type           | Shows                                                             |
| ------------------- | -------------- | ----------------------------------------------------------------- |
| `product-overview`  | `architecture` | Adapters, EventBus, pipeline, agent/stars, Dashboard, data stores |
| `runtime-ownership` | `architecture` | `RuntimeServices` vs `AstrBotCoreLifecycle` vs Dashboard process  |
| `pipeline-stages`   | `workflow`     | `stage_order.py` exact sequence                                   |
| `inbound-sequence`  | `sequence`     | Adapter → EventBus → scheduler → Process → Respond                |
| `authz-decision`    | `sequence`     | subject → `authorize()` → audit / step-up                         |
| `kb-upload`         | `dataflow`     | media, metadata, chunks, FAISS, compensating cleanup              |
| `agent-run`         | `lifecycle`    | request-scoped run, tools, `agent_stats`, interrupt               |

## Per-module default

See `REFERENCE.md` "Default diagram". If the module is tiny and the
overview already contains it, reuse that figure and record
`diagram reused:<stem>` rather than inventing a second topology.

Additional maps when the module owns the behavior:

| Module             | Extra map                                                     |
| ------------------ | ------------------------------------------------------------- |
| `platform`         | architecture of discovery + one representative adapter family |
| `webchat`          | sequence with `message_id` multiplexing                       |
| `star`             | architecture of load path + Extension Protocol v1 sandbox     |
| `dashboard-api`    | architecture of `/api/v1` assembly (router → service → store) |
| `config`           | dataflow of `save_config_async` revisions                     |
| `computer`         | sequence of tool permission ∩ step-up                         |
| `backup`           | dataflow of backup/restore                                    |
| `ops-supply-chain` | architecture of source-build compose + in-app `/help/`        |

## Forbidden drawings

- `platform_settings.group_wake_policy`
- `disable_builtin_commands` as a pipeline switch
- session-wide WebChat busy flag
- `docs.astrbot.app`, `soulter/astrbot`, PyPI `astrbot` as fork artifacts
- Legacy plugin `register` / `event.bot` APIs
- Alembic/sqlc (this fork has none)

## Quality bar

Showcase: all artifact checks, 0 composition errors or warnings. Node labels
must name real types/modules. Do not use example JSON facts from
`archify/examples/`.
