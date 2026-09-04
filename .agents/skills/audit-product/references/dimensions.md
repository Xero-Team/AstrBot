# Audit dimensions

Quality model: ISO/IEC 25010:2023 product quality (nine characteristics)
plus product-specific extras this checkout needs. Cite
<https://iso25000.com/index.php/en/iso-25000-standards/iso-25010>; load
`references/standards.md` row `iso-25010` rather than pasting the model.
Security review method: OWASP ASVS 5.0.0 + STRIDE on trust boundaries.
Secure-development overlay: NIST SSDF (PO/PS/PW/RV) for `ops-supply-chain`.
URLs: `references/standards.md`.

A module chapter must rate every **core** dimension. Mark `未评估` with a
reason rather than omitting the row. Sub-characteristics are prompts, not
a requirement to write a paragraph each.

## Core dimensions (mandatory)

### 1. Functional suitability — 功能适合性（Functional suitability）

ISO: completeness, correctness, appropriateness.

Ask:

- Does the documented feature exist and match runtime?
- Are outputs right for the stated contract (OpenAPI, config, event fields)?
- Is the feature the right one for the job, or a leftover / wrong layer?
- Are error and empty-state behaviors specified and implemented?

AstrBot prompts:

- Pipeline stage order and stop-propagation vs `stage_order.py`
- Wake reasons vs `llm_access.*` (never `group_wake_policy`)
- Command `command_id` identity vs fossil names
- Provider type vs third-party **Agent runner** (`dify`/`coze`/…)
- WebChat `message_id` request identity vs session-wide busy
- Knowledge-base upload: no queryable partial document after failure

### 2. Code correctness — 代码正确性（Code correctness）

Not an ISO characteristic; required for this product audit. Covers defects
that ISO would split across functional correctness, reliability, and
maintainability.

Ask:

- Types, invariants, and ownership match the surrounding code.
- Race, TOCTOU, double-close, lost `CancelledError`.
- Partial writes, revision inversion, stale cache.
- Wrong exception swallowed; `except Exception` without re-raise of cancel.
- Off-by-one, timezone, path-encoding, Windows vs POSIX.
- Tests that assert the wrong thing (false confidence).

AstrBot prompts:

- `save_config_async()` snapshot + monotonic revision
- EventBus retains task refs; bounded queues
- `TurnWindowManager` flush events only from the manager
- DB protocol vs ad-hoc `session.add`
- Frontend sanitization before `v-html`

### 3. Completeness — 功能齐全性（Completeness）

ISO functional completeness, plus product packaging.

Ask:

- User-visible docs (`docs/zh` + `docs/en`) cover the behavior.
- Dashboard can operate the feature or documents CLI-only honestly.
- OpenAPI, generated client, `docs/public/openapi.json`, tests moved together.
- Config metadata exists; secrets marked; redaction/restore works.
- Unfinished code is not reachable from default config.
- Operator story: backup, logs, auth, bind address, upgrade.

A feature that exists only in code, or only in docs, is a finding.

When comparing a documented/OpenAPI/UI promise to runtime, pick one contract
verdict (pass `--contract-verdict` on the finding when it is a gap):

| Verdict              | Meaning                                                 |
| -------------------- | ------------------------------------------------------- |
| `implemented`        | Promise holds on every traced path                      |
| `partial`            | Happy path holds; a sad path does not                   |
| `contradicted`       | Runtime does the opposite of the contract               |
| `stronger-than-spec` | Extra undocumented constraint; next editor can break it |
| `absent`             | No enforcement found; attach what was searched          |
| `undecidable`        | The document is too vague to check (docs finding)       |

`partial` on a shipped promise cannot be completeness `excellent`. `absent`
on a Dashboard/OpenAPI claim is `gap`. Keep Spec (this table) separate from
Standards (`AGENTS.md` invariants) in the chapter.

### 4. Security — 安全性（Security）

ISO: confidentiality, integrity, non-repudiation, accountability,
authenticity, resistance.

Method:

1. Draw trust boundaries (adapter, Dashboard, plugin, MCP, tool, file, LLM).
2. STRIDE each boundary.
3. Map controls to ASVS 5.0.0 where they fit.
4. Walk OWASP Secure Code Review checklists that apply (authn, authz,
   injection, files, crypto, config, logging). Those lists are overlays,
   not automatic findings.

ASVS 5.0.0 chapters to reach for (cite `v5.0.0-x.y.z` only when mapped):

1. Encoding and sanitization
2. Validation and business logic
3. Web frontend security
4. API and web service
5. File handling
6. Authentication
7. Session management
8. Authorization
9. Self-contained tokens
10. Cryptography
11. Secure communication
12. Configuration
13. Data protection
14. Secure coding and architecture
15. Security logging and error handling
16. WebSockets

AstrBot invariants (fail the security rating if broken):

- Dashboard default bind `127.0.0.1`; non-loopback is explicit
- `dashboard.trust_proxy_headers` default false
- Auth rate limit on and bounded
- TLS verify on download/update; no `CERT_NONE` / `verify=False` retry
- Remote MCP rejects private/loopback unless `allow_private_network`
- HTTP clients do not follow redirects on MCP
- DOMPurify before `v-html`; `defusedxml` for untrusted XML
- Generic user-facing agent errors; `safe_error` / `redact_sensitive_text`
- `authorize()` fail-closed; no `event.is_admin()` / `admins_id` revival
- File-token and data-file manager cannot escape `data/`
- Plugin Dashboard Extension: sandboxed iframe, host-managed Actions

Hunting angles (apply on every security walk; sad path first):

1. Timeout, cancel, retry, half-written KB/config, swallowed `CancelledError`
2. Empty / max / `0` / `-1` / missing vs null
3. Implicit trust (DB assumes API validated; renderer assumes write-time sanitize)
4. Wrong order / replay (WebChat follow-up vs `message_id`)
5. Concurrency (two uploads, two `save_config_async`, cron overlap)
6. Two parsers (OpenAPI vs FastAPI vs generated client; name vs MIME vs magic)
7. Round trip (store then retrieve; redaction/restore; KB chunk then query)
8. Defaults and flags (`trust_proxy_headers`, MCP `allow_private_network`, first-start)

Attacker-controlled vs operator-controlled:

- Investigate: IM/plugin/MCP/tool args/upload/WebChat/other-user data, unsigned
  cookies, request bodies
- Not injection sources: `default.py`, env, operator config, compile-time
  constants. Those can still be **insecure defaults** (fallback secret,
  fail-open, `0` timeout).
- Vue `{{ }}` is auto-escaped. Flag `v-html` only when unsanitized untrusted
  HTML reaches it (this checkout requires DOMPurify).

Agent/LLM extras (current: OWASP GenAI LLM Top 10 **2026** + Agentic
Applications 2026 — fetch `standards.md` rows `llm-top-10` / `agentic-top-10`;
do not use archived 2025 LLM numbers such as LLM05 Improper Output Handling):

- Prompt injection is a finding only if it **crosses a trust boundary**.
  Same-session "the model said X to me" is not. Name the boundary.
- The bug is the missing code-level gate, not the model. Guardrail prompts
  are not controls. Model output is untrusted input; trace it to the sink.
- Tool permission = user ∩ persona ∩ tool policy; handoff cannot escalate.
  Shared service credentials with per-user query scoping are not confused
  deputies.
- SSRF via tools, adapters, KB fetch, MCP — only if the URL is attacker-shaped
- Secret leakage into logs, traces, `agent_stats`, WebChat events
- Indirect injection via retrieved KB/memory/plugin README; tenant mix in
  vectors (`LLM09` 2026)
- Excessive agency / computer-use / unbounded tool loops (`LLM03` / `LLM06` 2026)

### 5. Reliability — 可靠性（Reliability）

ISO: faultlessness, fault tolerance, availability, recoverability.

Ask:

- Crash vs degrade; retry bounds; queue bounds
- Shutdown and partial-init cleanup
- DB busy/WAL; compensating cleanup
- Adapter reconnect; provider timeout
- Cron overlap; duplicate send

### 6. Performance efficiency — 性能效率（Performance efficiency）

ISO: time behavior, resource utilization, capacity.

Ask:

- Hot path allocations; N+1 DB; unbounded history into the model
- Event queue 1024; concurrency semaphores
- Embedding/FAISS size; file upload limits
- Dashboard payload size; WS fan-out

Evidence types are not interchangeable (fetch `cwv` in `standards.md`):

| Evidence                       | What it is                 | Use                           |
| ------------------------------ | -------------------------- | ----------------------------- |
| Field / CrUX / first-party RUM | Aggregated real users      | Public-site CWV only          |
| Lab trace / Lighthouse lab     | One stated browser session | Local Dashboard when it ran   |
| Static inspection              | Source hypothesis          | Form a finding at `suspected` |

Rules:

- Loopback / staging Dashboard has **no CrUX**. Missing field data is
  unavailable, never a pass.
- This operator UI is desktop-first. Do not default to mobile CWV.
- Cite LCP / INP / CLS values, not a Lighthouse category 0–100 score
  (weights change; Lighthouse 13+ uses Performance Insights).
- Thresholds apply only if this session measured: LCP < 2.5s, INP < 200ms,
  CLS < 0.1 at the stated percentile/viewport.
- Default live origin is the current-branch lab in `REFERENCE.md`
  (`http://127.0.0.1:6185`). If it is down, start this checkout unless
  the user forbade it. If it still cannot run: `未评估` plus the
  command that would measure it. Do not block the audit on Chrome
  DevTools MCP.
- Do not demand load-test numbers you did not collect.

### 7. Interaction capability — 交互能力（Interaction capability）

ISO 25010:2023 name for usability. Official sub-characteristics:
appropriateness recognizability, learnability, operability, user error
protection, user engagement, inclusivity, user assistance,
self-descriptiveness.

Ask:

- Dashboard i18n (`pnpm i18n:check`); zh/en docs aligned
- Destructive actions need confirm + step-up where required
- Errors are actionable and non-leaking
- Default passwords logged once at first start, not left as `astrbot/astrbot`
- Name the operator task of the screen. One primary action. Empty and
  error states have a next step. Same verb across the flow.
- Named UX smells (optional `--ux-smell`, not a new `kind`):
  `overloaded-screen`, `click-cemetery`, `form-graveyard`,
  `silent-errors`, `dead-end-states`, `mystery-navigation`,
  `contrast-blindness`, `inconsistent-actions`.
- Accessibility:
  - Operator-blocking (no keyboard path, no accessible name on a
    primary control, contrast that hides errors on login / plugin
    install / backup / chat send) is `medium`, or `high` if it blocks
    auth or a destructive action. Not `info`.
  - Full WCAG 2.2 AA of the Dashboard is `未评估` unless an axe-core
    or Playwright a11y run happened this session. Sample by template
    (login, chat, plugins, config, backup), not every Vue file.
  - Record the axe-core version if you compare two scans; rule-set
    drift is not a product regression.
- On `webchat` / `agent` / `computer`, also walk the AI-UX prompts in
  `module-checklist.md` (disclosure, override, irreversible preview).
- On `sdk-api` / `star` / `skills`, agent-facing discoverability is
  `not_assessed` unless the user asked for an AUT pass.

### 8. Maintainability — 可维护性（Maintainability）

ISO: modularity, reusability, analysability, modifiability, testability.

Ask:

- Ownership matches `AGENTS.md` (no Dashboard imports in `astrbot.api`)
- Complexity vs Ruff mccabe 15; no new god-objects
- Generated files not hand-edited (OpenAPI client, NapCat model)
- Tests sit next to the nearest coverage
- Dead legacy shims

### 9. Flexibility — 灵活性（Flexibility）

ISO 25010:2023 (formerly portability): adaptability, scalability,
installability, replaceability. Testability belongs under maintainability
and the extra `test_sufficiency` dimension — do not double-count it here.

Ask:

- POSIX + Windows paths (`pathlib`); ASTRBOT_ROOT
- Source-build compose still works
- Providers/adapters are modules, not hard-wired
- Testability: can you exercise the owner without the world

### 10. Compatibility — 兼容性（Compatibility）

ISO: co-existence, interoperability.

Ask:

- Adapter protocol fidelity (OneBot, Satori, official APIs)
- OpenAPI vs frontend generated client
- Plugin SDK stability (`astrbot.api` only)
- Lockfile/installer matrix in `AGENTS.md`

Do not score "compatible with upstream plugin format" as a goal. This fork
does not preserve legacy plugin APIs.

### 11. Safety — 安全性/危害防护（Safety）

ISO 25010:2023: operational constraints, risk identification, fail-safe,
hazard warning, safe integration.

For this product, safety is **operator and data harm**, not IEC 61508:

- Accidental bind to `0.0.0.0` without warning
- Plugin/pip install, computer-use, local exec without step-up
- Backup import overwriting live data
- Content-safety stage bypass
- Destructive Dashboard actions

If a module cannot cause harm beyond its owner, rate `良好` with a short
reason, not `未评估`.

## Extra product dimensions (mandatory at product level)

Rate these on the product (synthesis) and on modules that own them.

### 12. Observability — 可观测性（Observability）

Logs, traces, stats, audit log. No secrets. High-risk allow fail-closed
when the audit queue is full.

### 13. Operability / packaging — 可运维性（Operability）

`make doctor` / `bootstrap` / `dev` / `run`. Compose source-build.
First-start credentials. Backup. Update path (`zip_updator`) TLS.
Honest "we do not publish images" story.

### 14. Documentation fitness — 文档适合性（Documentation fitness）

Bilingual, in-app `/help/`, no `docs.astrbot.app`. Architecture page
matches code. Plugin guides match SDK.

AEO-lite for in-app help only (fetch `seo-aeo` if citing): the first
paragraph of a `/help/` page should answer the operator question.
zh/en pairs stay structurally aligned. Do not gate the product on
public-site SEO (sitemap, robots.txt, JSON-LD Product, ranking).
`llms.txt` / WebMCP is optional; a Lighthouse Agentic Browsing pass is
not search ranking and not a product requirement.

### 15. Test sufficiency — 测试充足性（Test sufficiency）

Blocking profile, unit vs integration tags, frontend Vitest/e2e. This
checkout uses pytest-asyncio `strict` mode: async tests need an explicit
`asyncio` marker. A 99% function-coverage number with missing failure-path
tests is still a gap.

### 16. Supply chain — 供应链（Supply chain）

Lockfiles, pin matrix, Actions, Dockerfile, npm/pnpm/uv. NIST SSDF PS/PW.
No unpinned brand fetches. Dependabot/audit gates.

## What "treat as a product" adds

Amateur-repo reviews stop at "I spotted a smell". Product audits also ask:

- Can a new operator deploy it from the documented path without tribal knowledge?
- Are defaults safe?
- Is the public contract (docs + OpenAPI + SDK) true?
- Is there a supported way to back up, restore, and report a vuln?
- Are unfinished features dark, gated, or documented as experimental?
- Would you put this on a network you care about?
- Confirm deployment assumptions (loopback Dashboard, no fork-published
  image) before ranking exposure. List **non-capabilities** so severity is
  not inflated to a public SaaS.

Those answers belong in the executive summary, not only in module footnotes.
