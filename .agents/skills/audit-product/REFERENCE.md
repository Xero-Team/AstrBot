# Product audit overlay

This file is the checkout-specific fact sheet for `audit-product`. Policy
stays in `SKILL.md`. Cite `AGENTS.md`, `docs/zh/dev/architecture.md`, and
`references/standards.md`; do not paste them.

## Product identity

| Field               | Value                                                     |
| ------------------- | --------------------------------------------------------- |
| Product             | AstrBot (Xero-Team fork)                                  |
| Repository          | `Xero-Team/AstrBot`                                       |
| Upstream provenance | `AstrBotDevs/AstrBot` (sync source only)                  |
| Support surface     | current `master` only; see `SECURITY.md`                  |
| Published artifacts | none (no fork PyPI, GitHub Release, or container publish) |
| Runtime image tag   | source-build `astrbot:local` via `compose.yml`            |
| Docs                | in-app `/help/` from the Dashboard                        |
| Python floor        | `>=3.14`; pin in `.python-version`                        |
| Dashboard stack     | Vue + Vuetify + Vite; FastAPI `/api/v1`                   |

Do not describe this fork as the PyPI package `astrbot` or the image
`soulter/astrbot`.

## Acceptance-test lab

Default live target when the user does not override host, origin, or
account. **Acceptance-test only. Never production.**

| Field    | Value                                                                         |
| -------- | ----------------------------------------------------------------------------- |
| Target   | Current-branch process in this worktree, not `soulter/astrbot` or another SHA |
| Origin   | `http://127.0.0.1:6185`                                                       |
| Username | `astrbot`                                                                     |
| Password | `Astrbot123`                                                                  |
| Use      | Live Dashboard login, operator-path evidence, optional CWV/axe                |

If `127.0.0.1:6185` is already bound, confirm it is this worktree
(`make status`, startup log, or process cwd) before logging in. If it
is down, start this checkout (`make dev` unless the user asked for
`make run`) and record the command plus HEAD SHA in `manifest.json`.
A SHA/bind mismatch is an inventory assumption, not a silent login.

Do not write the lab password into `REPORT.md`, `CHAPTER.md`, Issues, or
changelogs. Cite "acceptance-test lab in `REFERENCE.md`". Do not copy
this password into product `default.py`, docs, Compose, or images.
Shipped first-start remains: username `astrbot`, random password in the
startup log (`AGENTS.md`). Finding `Astrbot123` hardcoded as a product
default is a separate insecure-default finding, not this lab convention.

## Comparison sources

When judging completeness or correctness, read these in order. Code wins if
docs are stale; that drift is still a finding.

1. Runtime code under `astrbot/`, `dashboard/src/`, `main.py`, `runtime_bootstrap.py`.
2. Contract: `openspec/openapi-v1.yaml`, `astrbot/core/config/default.py`.
3. Official standard for that surface: matching row in `references/standards.md`
   (fetch the URL; do not paste the spec).
4. User/operator docs: `docs/zh/` and `docs/en/` (must stay structurally aligned).
5. Tests: `tests/`, `dashboard/tests/`.
6. Gates: `Makefile` targets `check`, `test-blocking`, `quality` — not a
   substitute for review.
7. Policy: `AGENTS.md` security invariants, `SECURITY.md`, `AI_POLICY.md`.

## Sensitive zones

Extra scrutiny, even in a "quality" audit. From `AI_POLICY.md` and `AGENTS.md`:

- Dashboard authentication, TOTP/step-up, rate limiting, `trust_proxy_headers`
- Authorization (`astrbot/core/auth/`), API keys, WebChat identity
- Agent sandbox, tool execution, MCP URLs, computer-use
- File token service, data-file manager, backup import
- Adapter parsers (especially XML: `defusedxml`)
- Knowledge-base upload and compensating cleanup
- Config redaction/restoration
- DOMPurify / `v-html`
- TLS verification on download/update clients

## Workspace

Inventory records owners, promises, and assumptions. An assumption the
code relies on with **nothing found** that establishes it is the most
useful hand-off into module mode. Open questions stay open; do not close
them with confidence. Disagreements between records are quoted, not
quietly reconciled.

Created by `scripts/audit_ledger.py init` at
`.tmp/product-audit/<run-id>/`:

```text
.tmp/product-audit/<run-id>/
  manifest.json          # SHA, branch, scope, start time
  audit.jsonl            # append-only ledger
  CURRENT.md             # optional 10–20 line resume hint
  REPORT.md              # written in synthesis mode
  modules/<module_id>/
    CHAPTER.md           # Chinese chapter
    SENSITIVE.md         # optional; non-public repro detail
  diagrams/              # copies or pointers to archify HTML
```

`.tmp/` is gitignored. Do not relocate the run into `docs/` or `data/`.

## Module catalog

Audit units are **product modules**, not every Python package. A module has
one owner path, a user-visible promise, and a default diagram. Inspect the
tree at the frozen SHA; this table is a starting map, not a substitute for
`ls` and imports.

| ID                 | Promise                                            | Primary paths                                                                                      | Default diagram |
| ------------------ | -------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------- |
| `runtime`          | Process starts, owns services, shuts down cleanly  | `main.py`, `runtime_bootstrap.py`, `core_lifecycle.py`, `runtime_services.py`, `initial_loader.py` | architecture    |
| `config`           | Profiles, defaults, atomic async save              | `astrbot/core/config/`, `astrbot_config_mgr.py`, `umop_config_router.py`                           | dataflow        |
| `authz`            | One `authorize()` door, Dashboard auth, API keys   | `astrbot/core/auth/`, `dashboard/api/auth.py`, `authorization.py`                                  | architecture    |
| `db`               | `data_v4.db` schema, domain stores                 | `astrbot/core/db/`                                                                                 | architecture    |
| `pipeline`         | EventBus → ordered stages → respond                | `event_bus.py`, `astrbot/core/pipeline/`                                                           | workflow        |
| `command`          | Orbit parse/bind, command catalog                  | `astrbot/core/command/`, star filters                                                              | sequence        |
| `platform`         | IM adapters normalize to `AstrMessageEvent`        | `astrbot/core/platform/`                                                                           | architecture    |
| `provider`         | Chat/STT/TTS/embed/rerank via lazy modules         | `astrbot/core/provider/`                                                                           | architecture    |
| `agent`            | Tool loop, MCP, runners, sub-agents, `agent_stats` | `astrbot/core/agent/`, `astr_main_agent.py`, `subagent_orchestrator.py`                            | sequence        |
| `star`             | Plugin SDK, load/unload, Dashboard Extension v1    | `astrbot/core/star/`, `astrbot/api/`                                                               | architecture    |
| `builtin-stars`    | Built-in Stars behave as plugins                   | `astrbot/builtin_stars/`                                                                           | workflow        |
| `knowledge-base`   | Upload, chunk, FAISS, compensating cleanup         | `astrbot/core/knowledge_base/`, `db/vec_db/`                                                       | dataflow        |
| `memory`           | Memory writeback/retrieval policy                  | `astrbot/core/memory/`                                                                             | dataflow        |
| `persona`          | Persona runtime and learners                       | `astrbot/core/persona_runtime/`, `persona_mgr.py`                                                  | lifecycle       |
| `conversation`     | Conversations, history, attachments                | `conversation_mgr.py`, message history                                                             | lifecycle       |
| `cron`             | Scheduled jobs                                     | `astrbot/core/cron/`                                                                               | lifecycle       |
| `skills`           | Skill discovery from data/plugins/workspace        | `astrbot/core/skills/`                                                                             | architecture    |
| `computer`         | Computer-use / local tools                         | `astrbot/core/computer/`, `core/tools/`                                                            | sequence        |
| `backup`           | Backup and restore                                 | `astrbot/core/backup/`                                                                             | dataflow        |
| `dashboard-api`    | FastAPI `/api/v1`, services, envelopes             | `astrbot/dashboard/`                                                                               | architecture    |
| `dashboard-ui`     | Operator WebUI                                     | `dashboard/src/`                                                                                   | architecture    |
| `webchat`          | Unified Chat WebSocket, request-scoped runs        | `astrbot/core/webchat/`, dashboard chat APIs                                                       | sequence        |
| `cli`              | `astrbot` console entry                            | `astrbot/cli/`                                                                                     | lifecycle       |
| `sdk-api`          | Public plugin SDK boundary                         | `astrbot/api/`                                                                                     | architecture    |
| `ops-supply-chain` | Compose, Docker, CI, locks, docs build, updates    | `compose.yml`, `Dockerfile`, `.github/`, `docs/`, lockfiles                                        | architecture    |

`product-overview` is not in this table. It is synthesized last from ledger
scores and must not be "audited" as if it were a code owner.

When a path is shared, assign findings to the **runtime owner**, not the
importer. Example: a Dashboard route that only forwards to `AuthorizationService`
is an `authz` finding if the bug is the decision; `dashboard-api` if the
envelope, authn, or OpenAPI is wrong.

## Suggested audit order

Respect dependencies so later chapters can cite earlier trust boundaries:

1. `runtime`, `config`, `db`
2. `authz`, `sdk-api`, `star`
3. `pipeline`, `command`, `platform`
4. `provider`, `agent`, `computer`, `skills`
5. `conversation`, `memory`, `persona`, `knowledge-base`
6. `cron`, `backup`, `webchat`
7. `dashboard-api`, `dashboard-ui`, `cli`, `builtin-stars`
8. `ops-supply-chain`
9. Cross-cut + synthesis

## Built-in gates (signals, not the audit)

Use these as evidence. A green gate does not close a dimension.

```bash
uv run pytest --test-profile blocking
make test-blocking
make check
make quality
cd dashboard && pnpm test
```

Python function coverage for `astrbot` is gated at 99% via
`scripts/check_function_coverage.py`. Dashboard Vitest gates are in
`dashboard/vitest.config.ts`. Coverage is necessary and not sufficient.

## Fork policies that affect ratings

Violations are findings, not style nits:

- No legacy shims; no Python 3.10–3.13 branches
- Import boundaries in `tests/unit/test_import_boundaries.py`
- Group wake is explicit (`llm_access.group`, `llm_access.reply_to_bot`)
- Command identity is `command_id`; no fossil short-name lookup
- Dashboard bind defaults to `127.0.0.1`; MCP private-network default deny
- User-facing agent failures stay generic; redact secrets
- Bilingual docs for user-visible behavior
