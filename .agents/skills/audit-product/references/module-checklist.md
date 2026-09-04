# Per-module checklist

Use with `dimensions.md`. Every bullet is a question. A silent skip is a
`未评估` row, not a pass. Inspect the frozen SHA; this list can lag the
tree.

Before the bullets, load only the matching rows in `references/standards.md`
(see that file's load map). Fetch the official URL when a clause is in
doubt; cite `--standard` / `--standard-clause` on findings.

| Module             | Standard ids                                                                                                                                       |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `runtime`          | `iso-25010`, `pytest`                                                                                                                              |
| `config`           | `iso-25010`, `asvs-5`                                                                                                                              |
| `authz`            | `asvs-5`, `cwe`, `stride`                                                                                                                          |
| `db`               | `asvs-5`, `iso-25010`                                                                                                                              |
| `pipeline`         | `iso-25010`, `pytest-asyncio`                                                                                                                      |
| `command`          | `iso-25010`                                                                                                                                        |
| `platform`         | `defusedxml`, `asvs-5`                                                                                                                             |
| `provider`         | `asvs-5`                                                                                                                                           |
| `agent`            | `mcp-2026-07-28`, `llm-top-10`, `agentic-top-10`, `asvs-5`, `agent-usability`                                                                      |
| `star`             | `agent-skills`, `asvs-5`, `agent-usability`                                                                                                        |
| `builtin-stars`    | `agent-skills`, `asvs-5`                                                                                                                           |
| `knowledge-base`   | `llm-top-10`, `asvs-5`, `iso-25010`                                                                                                                |
| `memory`           | `asvs-5`                                                                                                                                           |
| `persona`          | `asvs-5`                                                                                                                                           |
| `conversation`     | `asvs-5`                                                                                                                                           |
| `cron`             | `asvs-5`                                                                                                                                           |
| `skills`           | `agent-skills`, `agents-md`, `agent-usability`                                                                                                     |
| `computer`         | `llm-top-10`, `agentic-top-10`, `asvs-5`                                                                                                           |
| `backup`           | `asvs-5`                                                                                                                                           |
| `dashboard-api`    | `openapi-31`, `fastapi`, `hey-api`, `asvs-5`                                                                                                       |
| `dashboard-ui`     | `vue3`, `vite`, `vitest`, `playwright`, `pnpm`, `dompurify`, `asvs-5`, `wcag-22`, `axe-core`, `cwv`, `web-interface-guidelines`                    |
| `webchat`          | `asvs-5`, `openapi-31`, `llm-top-10`                                                                                                               |
| `cli`              | `pytest`, `google-pyguide`                                                                                                                         |
| `sdk-api`          | `google-pyguide`, `asvs-5`, `agent-usability`                                                                                                      |
| `ops-supply-chain` | `uv-lock`, `ruff`, `pyright`, `pnpm`, `ssdf`, `semver`, `conventional-commits`, `shellcheck`, `shfmt`, `hadolint`, `psscriptanalyzer`, `vitepress` |

## `runtime`

- `main.py` vs CLI both call `initialize_runtime_bootstrap()`; differences
  (`.astrbot` marker, `--webui-dir`) are documented and tested.
- Importing `astrbot.core` is inert (`test_core_import_smoke.py`).
- `create_runtime_services()` owns config, DB, prefs, Playwright, file
  tokens, pip installer, demo state.
- `AstrBotCoreLifecycle` init/shutdown order; partial-init cleanup;
  `CancelledError` re-raised.
- Process reboot / lock file / `ASTRBOT_ROOT` vs source tree.
- First-start Dashboard password is random and logged once.

## `config`

- Defaults live in `astrbot/core/config/default.py`; version is derived,
  not hardcoded.
- `save_config_async()` snapshots before leaving the loop; monotonic
  revision; atomic replace + fsync.
- Rejects `admins_id`, `tool_permissions`, `disable_builtin_commands`,
  `group_wake_policy`.
- Secret fields redact on API read and restore on write.
- Profile / UMO routing (`umop_config_router.py`) cannot apply the wrong
  config to an event.
- Probe `0` / `""` / `-1` / missing env: timeouts, retry, bind, TLS verify.
  Fallback secrets (`env.get(K) or 'dev'`), fail-open flags, debug traces in
  API responses. Defaults must be the pit of success, not a cliff.

## `authz`

- Single `authorize()`; fail-closed on unknown action, missing context,
  policy exception, full high-risk audit queue.
- `event.is_admin()` is always false; no IM elevation channel.
- Step-up: bound to account+sid+action+resource, TTL ≤ 5 min, consume-once.
- API keys: explicit capability, no `*`/`NULL` expansion, no `system`
  scope, no data-file manager, high-risk denied.
- Dashboard bind `127.0.0.1`; `trust_proxy_headers` default false; login
  rate limit bounded.
- Platform membership facts: only listed adapters; TTL; never global bind.
- Fail-closed on exception. Operator config is not attacker input; hardcoded
  secrets in repo still are findings. Empty allowlists must not mean "allow
  all".

## `db`

- SQLModel models are schema truth; no Alembic; no startup `ALTER`.
- Domain protocols vs mixins; no cross-store hidden writes.
- Auth tables current-state vs `AuthAuditLog`.
- WAL / busy_timeout; initialize once under a lock.
- Tests lock table count (`EXPECTED_TABLE_NAMES`).

## `pipeline`

- `stage_order.py` sequence unchanged unless the finding is that it is
  wrong.
- Wake routing writes `wake_reasons`; command beats LLM; unknown
  subcommand does not fall through to LLM.
- Stop-propagation and onion middleware unwind.
- `TurnCoalesce` / `TurnWindowManager`: only manager flush events carry
  `route_kind=turn_flush`.
- EventBus bounded queue, task refs, per-config scheduler.
- Group sender concurrency is experimental and default off.

## `command`

- Orbit catalog snapshot atomic replace; hot path reads snapshot only.
- `command_id` identity; `alter_cmd` does not use fossil short names.
- Built-in names ignored unless `resolution_strategy=manual_rename`.
- Lexer does not treat ordinary LLM prompts as commands.
- Diagnostics: stable error codes; zh/en at display edge.

## `platform`

- Discovery owner is the only shared importer of concrete sources.
- Each sampled adapter: normalize, send, disconnect, no leaked tasks.
- XML: `defusedxml` (Satori), not stdlib parsers. Webhook signature
  verification. After a confirmed parser/auth bug, variant-sweep the other
  adapter families.
- WebChat is a platform source and a Dashboard protocol — split findings
  with `webchat`.
- NapCat generated model is not hand-edited.

Sample at least: one bot-API adapter, one webhook, NapCat/OneBot, Satori,
WebChat. Name the skipped ones.

## `provider`

- Lazy map in `provider_modules.py`; no eager import of every source.
- Timeout, retry bound, TLS verify, key not logged.
- Streaming vs non-streaming cancellation.
- Dify/Coze/DashScope/DeerFlow are runners, not chat providers.

## `agent`

- Tool loop emits `agent_stats` after every model call, including
  intermediate.
- MCP: stdio + Streamable HTTP against **2026-07-28** (stateless,
  `MCP-Protocol-Version` / `_meta` version, header/body match or
  `HeaderMismatch`, MRTR). Remote HTTP: Origin check, no redirect
  follow, default deny private/loopback unless `allow_private_network`.
  Do not treat HTTP+SSE or `Mcp-Session-Id` as current product surface.
- Tool permission = user ∩ persona ∩ tool; handoff cannot escalate.
- History sanitizer / compactors do not drop safety-relevant tool errors.
- Runners stay under `agent/runners/`.
- Prompt-injection surfaces: IM, memory, KB, tool output, plugin. A finding
  requires a **named trust boundary** crossed; same-session party tricks are
  not. Guardrail prompts are not controls. Model output is untrusted.
- Tool-argument sinks (SQL/shell/path/HTTP) validated at the handler, not
  trusted because "the model produced JSON".
- Sub-agent / MCP responses inherit least privilege; MCP output is indirect
  injection. `agent_stats` and WebChat events do not leak secrets.
- AI-UX (optional `--ai-ux`): output is model-generated (`ai-transparency`);
  limits are stated (`ai-capability-disclosure`); interrupt / retry / reject
  tool result (`ai-user-control`, `efficient-ai-correction`); irreversible
  computer-use / send / install needs preview (`ai-action-consequences`,
  `critical` if missing); `agent_stats` is request-scoped telemetry, not a
  verified fact (`automation-bias-prevention`, `ai-audit-trails`).

## `star`

- Load from `data/plugins/` + builtin; `initialize`/`terminate`.
- Public SDK only for plugin-facing code.
- Dashboard Extension v1: digest manifest, Actions in `initialize()`,
  sandbox iframe, no auth-state leak, no arbitrary HTTP proxy.
- KV / `data_directory()` not the plugin source tree.
- Plugin README / Extension HTML rendered in Dashboard is untrusted
  (DOMPurify). Skill instructions vs description alignment; no config
  poisoning. Cite `verification.md` skill-scanner bar; do not vendor it.
- Public constructors: insecure values must fail, not only default-secure.
- Agent-facing usability (AUT) of Extension Actions / plugin Skills is
  `not_assessed` unless the user asked. Subject is the interface, not the
  model. Five failure modes: non-discovery, wrong selection, parameter
  cargo-culting, response-schema blindness, auth/error cliff.

## `builtin-stars`

- Behave as plugins (metadata, terminate, no concrete source imports).
- Built-in command availability is per-handler in the command DB.
- Python interpreter / computer-adjacent stars: sandbox and step-up.

## `knowledge-base`

- Vector shape checked before local write.
- Compensating cleanup on every store if metadata commit fails.
- Failed upload is not queryable.
- Parser types (PDF/HTML/…) bound size and timeout.
- Retrieved chunks can carry indirect prompt injection; query applies
  tenant/UMO filter, not only a metadata field on the document.

## `memory`

- Writeback policy cannot silently persist secrets.
- Retrieval is scoped; no cross-UMO leak. Retrieved memory is untrusted
  prompt text; same boundary bar as `agent`.
- Tuning/tasks have cancellation and bounds.

## `persona`

- Persona tool policy intersects user authz.
- Learners cannot escalate.
- Session state owned by `persona_runtime` store.

## `conversation`

- History commit under concurrency (`AssistantHistoryCommitter`).
- Attachments use file tokens; no path escape.
- WebChat threads vs IM conversations stay distinct.

## `cron`

- Overlap policy; uses origin session resource; cannot skip `authorize()`.
- Job payload is data, not `eval`.
- Failure does not storm-retry unbounded.

## `skills`

- Discovery: data/plugins/workspace; workspace is request-scoped.
- Path traversal out of workspace rejected.
- Skills are data, not trusted code, unless the product explicitly runs them.
- Plugin/runtime Skills that claim Agent Skills format: `name` matches
  directory, `description` says when (not) to load, details not dumped
  into `SKILL.md`.
- Uncoached discoverability of a plugin Skill is `not_assessed` unless
  the user asked for an AUT pass (`agent-usability`).

## `computer`

- Local exec / browser / computer-use require the documented high-risk
  actions + WebChat step-up set.
- Workspace bounds; no host-wide FS.
- Timeouts and cancellation.
- Model-chosen paths cannot exceed the user's `authorize()` result. Step-up
  is the control; a system prompt "be careful" is not. Unbounded loops that
  spend or delete are findings even in the attacker's own session
  (operator bill / shared quota). Preview before irreversible computer-use
  (`ai-action-consequences`); missing preview is `critical`.

## `backup`

- Archive path confined to `data/backups`.
- Restore cannot execute files from the archive.
- Partial restore does not leave a mixed schema.

## `dashboard-api`

- Router under `/api/v1`; envelope vs raw responses.
- OpenAPI 3.1.0 source (`openspec/openapi-v1.yaml`), generated Hey API
  client, public JSON, tests, call sites move together. Unique
  `operationId`; mutating routes not accidentally `security: [{}]`.
- Authn on every mutating route; CSRF/SameSite where cookies exist.
- Upload limits; data-file manager path rules (see architecture page).
- Demo mode read-only.

## `dashboard-ui`

- DOMPurify before `v-html`; no unaudited `v-html`. Vue `{{ }}` auto-escape
  is not XSS. Markdown image/link auto-fetch of model output is an
  exfiltration sink only if the client loads remote URLs without CSP.
- i18n keys present (`pnpm i18n:check`).
- Generated OpenAPI client not hand-patched.
- Step-up UX cannot be skipped from the client.
- Vitest + relevant Playwright; do not claim e2e if not run.
- Name the operator task (login, bind adapter, install plugin, backup,
  chat). One primary action per view. Competing primaries →
  `click-cemetery`. Empty/error with no next step → `dead-end-states` /
  `silent-errors`. Same action keeps the same verb (`inconsistent-actions`).
- Keyboard path, visible focus, and accessible name on login, plugin
  install, backup, and chat send. Operator-blocking a11y is `medium`/`high`,
  not `info`.
- Full WCAG 2.2 AA is `未评估` unless axe-core or Playwright a11y ran this
  session. Sample templates: login, chat, plugins, config, backup. Do not
  vendor an a11y scanner into this checkout.
- Live CWV: desktop lab against loopback if Dashboard is up; no CrUX.
  Unrated if it did not run. Cite LCP/INP/CLS, not a Lighthouse 0–100.
- Optional source review: fetch `web-interface-guidelines` for the files
  in scope. Do not inline the rule list. Do not add WebMCP/`llms.txt` to
  raise an Agentic Browsing score.

## `webchat`

- Unique `message_id` per run; no session-wide busy. Replay / follow-up
  must keep that identity.
- Interrupt, follow-up, `run_started`, `agent_stats` keep request identity.
- Guest vs dashboard-session vs IM subject cannot be confused.
- WS authn; origin checks if any.
- AI-UX: chat output is disclosed as model-generated; interrupt / retry is
  obvious; computer-use / send / install from chat has preview; stats are
  not framed as verified facts. Irreversible action without preview is
  `critical` (`ai-action-consequences`).

## `cli`

- Requires `.astrbot` marker; no Dashboard download.
- `plug install` path isolation; does not write the developer's `data/`
  from tests.
- Commands fail closed on missing runtime.

## `sdk-api`

- `astrbot.api` does not import Dashboard or concrete sources.
- Documented plugin guides match exported names.
- No legacy `register` / `event.bot` / `event.client`.
- Security-relevant APIs: 0/empty/null do not disable checks; bytes for
  distinct concepts are not interchangeable; errors fail closed.
- Agent-facing usability of `astrbot.api` names vs plugin guides is
  `not_assessed` unless the user asked for an AUT pass. Uncoached prompt;
  WITH/WITHOUT lift; traces not self-report; a bad score means fix docs/SDK,
  not the model. Five failure modes: non-discovery, wrong selection,
  parameter cargo-culting, response-schema blindness, auth/error cliff.

## `ops-supply-chain`

- Toolchain pins: Python 3.14.6, Node 26.5.0, npm 12.0.2, pnpm 11.21.0.
- `uv.lock` + `requirements.txt` + `pyproject.toml` stay aligned.
  `uv sync --locked` / `uv lock --check` is the contract.
- Compose `build:` + `astrbot:local`; no upstream image substitution.
- Dockerfile: no `.agents/` copy; docs baked to `/help/`.
- CI jobs vs `make check` gap is documented, not hidden.
- Update/download clients verify TLS.
- Actions: `references/verification.md` GHA bar (external attacker, no
  write access). `pull_request_target` + fork checkout; `${{ }}` in `run:`;
  comment commands; unpinned third-party actions **with** secrets; PR-supplied
  `AGENTS.md`/Makefile; agentic-action env-var intermediary.

## Cross-cut (after modules)

- zh/en docs structure; `/help/` first paragraph answers the operator
  question. No public-site SEO suite.
- OpenAPI drift
- Coverage vs missing failure paths
- Secret scanning / `make quality` bandit+audit
- SECURITY.md disclosure path still valid
