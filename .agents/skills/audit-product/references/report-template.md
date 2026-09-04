# Chinese report template

Write `REPORT.md` in Simplified Chinese. Keep identifiers verbatim.
Fill from the ledger; do not leave placeholder prose.

Copy this outline. Delete a section only if the run's scope makes it
meaningless, and say so under 范围.

```markdown
# Xero-Team/AstrBot 产品审计报告

| 项              | 值                                                                                                  |
| --------------- | --------------------------------------------------------------------------------------------------- |
| 产品            | AstrBot（Xero-Team fork）                                                                           |
| 仓库            | `Xero-Team/AstrBot`                                                                                 |
| 审计对象提交    | `<full SHA>`                                                                                        |
| 分支            | `<branch>`                                                                                          |
| 运行编号        | `<run-id>`                                                                                          |
| 方法            | ISO/IEC 25010:2023 + OWASP ASVS 5.0.0 + STRIDE + 本仓库不变量；标准目录见 `references/standards.md` |
| 报告日期（UTC） | `<YYYY-MM-DD>`                                                                                      |
| 范围            | 全量 / 模块列表                                                                                     |
| 审计方          | 智能体（agent）按 `.agents/skills/audit-product`                                                    |

## 1. 管理层摘要

用不超过一页回答：

- 这是什么产品，默认部署形态（回环 Dashboard、源码构建）。
- 总体就绪度：可内部使用 / 有条件对外 / 不建议对外暴露 / 尚不适合内部依赖。
- 最严重的 5 个发现（ID + 一句话）。
- 已经做得好、不应拆掉的控制（3–7 条）。
- 若只做三件事，按顺序做什么。

禁止在摘要里出现未写入台账的新问题。

## 2. 范围、方法与限制

### 2.1 范围内

模块表（ID、路径、状态、模块总评）。

### 2.2 范围外

例如：上游 PyPI 发行、未连接的真实 IM 账号、付费模型供应商账号、生产数据目录。
默认活体目标是当前分支 `http://127.0.0.1:6185`（验收测试环境账户，口令见
技能 `REFERENCE.md`，不要写入本报告；生产环境禁止使用）。未运行的动态
测试要写明。本机 Dashboard 未测的 Core Web Vitals、未跑的 axe-core 抽样、
未做的智能体可用性测试（AUT）标 `未评估`，不要写成通过。

### 2.3 方法

- 对照源：代码、OpenAPI、默认配置、中英文文档、测试、Makefile 门禁。
- 每个模块：承诺 → 分解 → 维度 → 失败路径 → 契约对照 → 发现 → 评分。
- 图：archify，事实来自当前代码。

### 2.4 限制

上下文分片、未跑的门禁、抽样的适配器、未做的负载测试。置信度为
`suspected` 的项不得在摘要里写成已确认漏洞。

## 3. 产品画像与威胁模型

### 3.1 运行时画像

链接总览架构图。用短段落描述：适配器 → EventBus → Pipeline → Star/Agent →
Respond；Dashboard/WebChat 控制面；`RuntimeServices` 与生命周期所有权。

### 3.2 信任边界

至少列出：不可信 IM 输入、插件、MCP、工具、浏览器、反向代理、本地文件、
LLM 输出、备份导入。对每条做 STRIDE 摘要（不必每个字母都有发现）。

### 3.3 资产

凭据、会话、对话、知识库向量、记忆、主机命令、内网、Dashboard 账户。

## 4. 质量总览

ISO/IEC 25010:2023 九特性 + 额外产品维的矩阵：行 = 维度，列 = 评级，
单元格 = 一句话证据。再给模块 × 四硬维（功能适合、代码正确、齐全、安全）矩阵。

## 5. 发现总览

计数表：严重/高/中/低/信息 × 类型。

| ID  | 模块 | 严重程度 | 类型 | 置信度 | 标题 |
| --- | ---- | -------- | ---- | ------ | ---- |

只列 `open`。`positive` 放到第 8 节。

## 6. 分模块审计

每个模块一节，或链到 `modules/<id>/CHAPTER.md` 并在此保留：承诺、图、
总评、维度表、该模块高+发现。全量报告不得只有链接没有总评。

### 6.x `<module_id>` 中文名

契约（Spec）与规范（Standards）分两块写，禁止平均成一句总评。
章节最低要求见 `finding-schema.md`；独立证伪与变体检索见
`verification.md`。

## 7. 横切问题

OpenAPI 漂移、中英文档不对齐、CI 门禁盲区、生成物手改、密钥扫描、
默认配置不安全组合、同一根因在多适配器/工具上的变体。

## 8. 良好实践与加固说明

从 `kind=positive` 汇总。写清位置，避免空泛“代码不错”。
已被上一层挡住的纵深防御缺口放这里，不要抬成高危发现。

## 9. 残余风险与路线图

- 按 P0 / P1 / P2 排列，映射发现 ID。
- P0：对外暴露或数据损坏前必须处理。
- 明确哪些是 fork 政策下的**非目标**（例如不上架 PyPI）。

## 10. 附录

- A. 实际执行的命令与退出码
- B. 图清单（archify 类型、源 JSON、HTML）
- C. 术语
- D. 台账路径与 `validate` 结果
- E. 引用的官方标准（URL + 条款 id；未抓取的标 `UNVERIFIED`）
```

## Executive-summary tone

Write as if a maintainer must decide whether to bind Dashboard off-loopback
or ship to operators. No cheerleading. No "总体来说还行" without readiness
enum.

## Length

A full-product `REPORT.md` should be long enough that a module is not a
stub: typically 150–400 lines for the roll-up, plus per-module chapters of
80–250 lines. If a chapter is under ~40 lines, the module was not audited.

## Linking diagrams

```markdown
[运行时所有权](diagrams/runtime.html)
```

HTML is for local viewing. Do not claim the figure is in `/help/` unless the
user asked to promote it into bilingual docs (then follow `archify` + docs
rules).
