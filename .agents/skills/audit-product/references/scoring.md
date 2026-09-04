# Scoring and severity

Do not invent a 0–100 "quality score". Qualitative ratings with written
rationale travel across sessions; fake precision does not.

## Dimension and module ratings

| Rating       | Chinese | Meaning                                                                                              |
| ------------ | ------- | ---------------------------------------------------------------------------------------------------- |
| `excellent`  | 优秀    | Meets the product bar. Tests and docs agree with code. No open high+ issues in this dimension.       |
| `good`       | 良好    | Fit for product use. Residual medium/low issues are documented and not data-loss or authz holes.     |
| `acceptable` | 可接受  | Usable with known gaps. Operator must follow caveats. No unmitigated critical.                       |
| `weak`       | 薄弱    | Below product bar. Completeness, correctness, or security would block a responsible external expose. |
| `gap`        | 缺口    | Missing control or feature the product already claims, or an invariant is broken.                    |
| `unrated`    | 未评估  | Not covered in this run. Requires a reason and a follow-up.                                          |

Rules:

- A module's **overall** rating is the **worst** of {functional suitability,
  code correctness, completeness, security} unless a worse reliability/safety
  finding dominates. Do not average away a security `gap`. Do not average
  Spec vs Standards; report both.
- Completeness `excellent` requires shipped promises at `implemented` (or
  honest CLI-only). `partial` or `absent` on a Dashboard/OpenAPI claim caps
  completeness at `acceptable` or worse.
- `unrated` security on a module that handles input, files, network, tools,
  or secrets is itself a process finding.
- Performance may be `unrated` if no measurement ran; say so. Cite LCP /
  INP / CLS, never a Lighthouse 0–100, as the rating rationale.
- Interaction capability `unrated` is allowed for pure internal libraries
  with no UI or operator surface. Operator-blocking a11y is not `info`.
- Agent-facing usability of `astrbot.api` / MCP / Skills stays
  `not_assessed` unless the user asked for an AUT pass.

## Product-level readiness

Separate from per-dimension ratings. Pick one:

| Readiness            | Chinese          | Meaning                                                                          |
| -------------------- | ---------------- | -------------------------------------------------------------------------------- |
| `internal_ok`        | 可内部使用       | Loopback Dashboard, trusted operators, accepted residual risk.                   |
| `conditional`        | 有条件对外       | External expose only behind TLS/reverse proxy, listed caveats fixed or accepted. |
| `do_not_expose`      | 不建议对外暴露   | Unmitigated critical/high security, data-loss, or authz fail-open.               |
| `not_ready_internal` | 尚不适合内部依赖 | Core flows incorrect or incomplete even on loopback.                             |

This fork's default bind is loopback. "对外" means non-loopback Dashboard,
public WebChat, or hosting untrusted plugins/MCP.

## Finding severity

Impact × likelihood, **in this product's threat model** (self-hosted IM
bridge + local Dashboard + LLM tools), not a generic web app.

| Severity   | Chinese | Use when                                                                                                                                                                                                              |
| ---------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `critical` | 严重    | Authz fail-open, RCE, unauthenticated Dashboard takeover, cross-tenant data read/write, silent DB/KB corruption, private-network MCP/tool SSRF **by default**.                                                        |
| `high`     | 高      | Auth bypass on a secondary surface, secret leak to users/logs, path escape under `data/`, missing compensating KB cleanup, TLS verify off, step-up skip on high-risk actions, privilege escalation via handoff/tools. |
| `medium`   | 中      | Missing server-side validation with limited blast radius, docs/OpenAPI/code drift that causes operator error, unbounded queue in a non-default path, XSS in a sanitised-but-incomplete sink, weak session flags.      |
| `low`      | 低      | Defense-in-depth gap, noisy errors, missing tests for a covered path, i18n miss, complexity, dead code that is not reachable from defaults.                                                                           |
| `info`     | 信息    | Positive note, hardening suggestion, explicit non-goal of this fork.                                                                                                                                                  |

Do not inflate "missing a comment" to `medium`. Do not deflate default-deny
violations to `low`.

If you compute CVSS, record the vector as extra data. The **report severity**
still uses the table above. CVSS often underrates self-hosted localhost
agents with powerful tools.

## Confidence

See `SKILL.md`. Severity and confidence are independent: a `suspected`
`critical` stays suspected until traced.

## Kind

| Kind           | Chinese  | Typical ISO / ASVS hook             |
| -------------- | -------- | ----------------------------------- |
| `defect`       | 缺陷     | functional correctness, reliability |
| `security`     | 安全     | security, ASVS, CWE                 |
| `completeness` | 齐全性   | functional completeness, docs       |
| `architecture` | 架构     | maintainability, ownership          |
| `reliability`  | 可靠性   | reliability                         |
| `performance`  | 性能     | performance efficiency              |
| `operability`  | 可运维   | flexibility, extra operability      |
| `docs`         | 文档     | documentation fitness               |
| `test-gap`     | 测试缺口 | test sufficiency                    |
| `supply-chain` | 供应链   | SSDF, compatibility                 |
| `positive`     | 良好实践 | info-only, no severity required     |

`positive` entries are first-class. Professional reports list what is done
well so maintainers do not rip out working controls. Defense-in-depth gaps
behind a working control are `positive` or `info`, not `high`.

Optional tags (not new `kind` values, not a 0–100 score): `--ux-smell`
and `--ai-ux` on `add-finding`. Keep severity from the table above.

`--ux-smell`: `overloaded-screen` · `click-cemetery` · `form-graveyard` ·
`silent-errors` · `dead-end-states` · `mystery-navigation` ·
`contrast-blindness` · `inconsistent-actions`.

`--ai-ux`: `ai-transparency` · `ai-capability-disclosure` ·
`ai-user-control` · `efficient-ai-correction` · `ai-action-consequences` ·
`agent-task-handoff` · `ai-audit-trails` · `automation-bias-prevention` ·
`ai-accuracy-communication`.

## Finding status

`open` · `accepted` · `fixed` · `false_positive` · `duplicate` · `out_of_scope`

`accepted` requires a user or documented product decision in this run.
Agents must not accept critical/high security on their own.

## Module score record

Every completed module writes:

- overall rating
- ratings for core dimensions 1–11 (or `unrated` + reason)
- extra dimensions that the module owns
- counts of open findings by severity
- 3–8 sentence rationale in Chinese for the chapter header

Product synthesis writes the same for the whole product, plus readiness.

## Anti-patterns

- "Coverage 99% therefore correctness 优秀"
- Averaging nine ISO scores into 7.2/10
- Scoring Dashboard quality from a Lighthouse category number
- Averaging Spec pass with Standards fail into one cheerful rating
- One finding titled "Dashboard 有很多问题"
- Copying AGENTS.md invariants as if they were verified
- Marking every adapter `未评估` because there are many — sample by
  parser class (webhook, WS, XML, official SDK) and say which were skipped
- Treating experimental flags as shipped product without reading defaults
- Rating a framework API from memory without a URL from `references/standards.md`
- Pasting ISO/ASVS/OpenAPI/MCP spec text into the chapter instead of citing it
- Listing every OWASP / LLM Top 10 item as a finding
- Calling prompt injection `confirmed` without a named trust boundary
- Using archived LLM Top 10 **2025** IDs (current overlay is **2026**)
- Exact HTTP/exploit requests in `REPORT.md` (use `SENSITIVE.md`, still no payload)
- CVSS as the report severity (optional extra data only)
