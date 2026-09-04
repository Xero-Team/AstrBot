# Finding schema

Ledger events are JSON Lines. `scripts/audit_ledger.py` validates them.
Do not hand-edit `audit.jsonl` except through the tool.

## Finding ID

```text
AUD-<YYYYMMDD>-<module_id>-<NNN>
```

- Date is the run's UTC start date, not "today" mid-run.
- `module_id` matches `REFERENCE.md`.
- `NNN` is a 3-digit per-module counter, stable for the run.
- Never reuse an ID. Tombestone with `event_type=delete`.

Cross-cutting issues still pick a **primary owner** module. Mention others
in `related_modules`.

## `add-finding` fields

Required:

| Field        | Values / notes                                  |
| ------------ | ----------------------------------------------- |
| `finding_id` | `AUD-…`                                         |
| `module_id`  | catalog id                                      |
| `title`      | Chinese, ≤70 chars, no trailing period          |
| `severity`   | `critical` `high` `medium` `low` `info`         |
| `kind`       | see scoring.md                                  |
| `confidence` | `confirmed` `likely` `suspected` `not_assessed` |
| `location`   | `path:line` or a precise symbol                 |
| `summary`    | one paragraph, Chinese                          |

Optional but expected for `security` and `defect`:

| Field              | Notes                                                                              |
| ------------------ | ---------------------------------------------------------------------------------- |
| `cwe`              | `CWE-nnn`                                                                          |
| `asvs`             | `v5.0.0-x.y.z`                                                                     |
| `iso25010`         | e.g. `security.integrity`                                                          |
| `standard`         | HTTPS URL from `references/standards.md`                                           |
| `standard_clause`  | short locator on that page                                                         |
| `stride`           | `S` `T` `R` `I` `D` `E` (repeatable)                                               |
| `related_modules`  | extra ids                                                                          |
| `impact`           | who is hurt, what is lost                                                          |
| `recommendation`   | concrete, current-fork design                                                      |
| `status`           | default `open`                                                                     |
| `sensitive`        | `true` if detail belongs in `SENSITIVE.md`                                         |
| `contract_verdict` | `implemented` `partial` `contradicted` `stronger-than-spec` `absent` `undecidable` |
| `boundary`         | short name of the trust boundary crossed (required sense for `confirmed` security) |
| `trace`            | repeatable `path:line` from entry to sink                                          |
| `ux_smell`         | optional smell id; closed set in `scoring.md`                                      |
| `ai_ux`            | optional AI-UX slug; closed set in `scoring.md`                                    |

`kind=positive` uses `severity=info` and may omit CWE/ASVS.
Framework-specific `defect` / `security` / `completeness` findings should
set `standard` when a catalog row applies. Omit rather than guess a URL.
`kind=completeness` should set `contract_verdict`. `kind=security` at
`confirmed` should set `boundary` and, when traced, `trace`.
`ux_smell` / `ai_ux` are optional tags. Omit rather than invent a slug.

## Prose in `CHAPTER.md` / `REPORT.md`

Each non-positive finding gets a subsection:

```markdown
### AUD-20260904-authz-001 短标题

| 项         | 值                              |
| ---------- | ------------------------------- |
| 严重程度   | 高（High）                      |
| 类型       | 安全（Security）                |
| 置信度     | 已确认（confirmed）             |
| 位置       | `astrbot/core/auth/foo.py:12`   |
| CWE / ASVS | CWE-285 / v5.0.0-8.2.1          |
| 标准       | `https://…` · `standard_clause` |

**事实：** 代码当前做什么（引用行号）。

**影响：** 谁能滥用，默认配置下是否可触达。

**证据：** 测试名、命令、或跟踪路径。未跑的命令不要写“已验证”。

**建议：** 当前架构下的最小正确修复。不要复活废弃路径。
```

Do not include exploit steps in `REPORT.md` for `critical`/`high` security.
Point to `modules/<id>/SENSITIVE.md`.

## Module chapter minimum

`modules/<id>/CHAPTER.md` must contain:

1. Module promise (3–10 lines)
2. Owner paths and in-scope SHA
3. **Spec** vs **Standards** — two short blocks, not merged (docs/OpenAPI
   promise vs `AGENTS.md` invariants)
4. Diagram links
5. Dimension table (rating + one-line evidence)
6. Findings (or "本模块无未关闭发现")
7. Test/gate commands actually run
8. Pre-conclusion list (`references/verification.md`) and `未评估`

## Cross-run stability

A later run at a new SHA creates new IDs. Optionally set
`supersedes: AUD-…` when it is the same issue. Do not rewrite history in
an old `audit.jsonl`.
