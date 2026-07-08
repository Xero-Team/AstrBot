---
outline: deep
---

# Persona Runtime / Memory 下一阶段实现路线图

## 目标

当前实现已经完成最小闭环：

- `persona_runtime` 与 `memory` 是独立子系统。
- 回复后异步写回 runtime state 与 long-term memory。
- 动态 runtime / memory context 进入 `extra_user_content_parts`，不污染 `system_prompt`。
- SQLite 表、CRUD、scope 隔离、事实检索、profile 聚合、operation log、工具删除 / 恢复已经可运行。

下一阶段目标不是复制 MaiBot / A_Memorix，而是在 AstrBot 现有架构上把长期记忆做成可管理、可观察、可纠错、检索质量可逐步提升的正式产品能力。

## 实现原则

- 不把 memory 塞回 `knowledge_base/`。
- 不引入旧记忆系统兼容层、旧插件格式桥接或历史路径 fallback。
- 不把动态记忆、动态人格状态拼进 `system_prompt`。
- 写回、抽取、profile 刷新、导入和调优任务必须异步，不阻塞主回复链路。
- 默认严格隔离。跨群、群私聊共享只能通过显式 policy 开启。
- KISS，先补产品闭环和可观测性，再做复杂图谱和多路检索。
- 优先复用 AstrBot 的 Provider、Dashboard API、OpenAPI 生成链路和现有工具注册机制。

## 阶段 1：Memory 后端 API 与 WebUI 管理闭环

这是最高优先级。当前用户只能通过聊天和 SQLite 验证记忆，前端看不出系统化变化。

### 后端 API

新增 dashboard API，不复用 knowledge base API：

- 需要先在 `astrbot/dashboard/services/auth_service.py` 的 scope 注册表里新增 `memory` scope，并同步更新 `openspec/openapi-v1.yaml` 中的 API key scope 说明；路由侧按现有模式定义 `require_memory_scope(request) -> AuthContext`，内部调用 `await require_scope(request, "memory")`，再用 `Depends(require_memory_scope)`。
- 照搬 `astrbot/dashboard/api/knowledge_bases.py` 的现有惯例：`APIRouter` + `_run` 统一 `ok()/error()` 响应封装 + 独立 `MemoryService` 服务层，业务逻辑不直接写进路由函数，分页沿用 `page`/`page_size` 参数风格。

- `GET /memory/facts`
  - 按 `person_id`、`chat_id`、`status`、关键词分页查询。
- `GET /memory/facts/{fact_id}`
  - 查看事实、证据、状态、operation logs。
- `POST /memory/facts`
  - 手动添加 fact，写入 operation log。
- `PATCH /memory/facts/{fact_id}`
  - 修改 `fact_text`、`fact_type`、`confidence`，写入 operation log。
- `POST /memory/facts/{fact_id}/delete`
  - 软删除。
- `POST /memory/facts/{fact_id}/restore`
  - 恢复。
- `GET /memory/profiles`
  - 查询 profile 列表。
- `POST /memory/profiles/{person_id}/refresh`
  - 异步刷新 profile。
- `GET /memory/operations`
  - 查询 operation log。
- `GET /memory/stats`
  - 返回 facts、profiles、episodes、deleted facts、worker queue size 等统计。

### WebUI

在 Dashboard 中补长期记忆真实页面，而不是只保留入口和翻译。当前源码里有 `AlkaidPage.vue` 和长期记忆翻译，但路由未挂载；实现时需要先选择并打通真实入口，推荐挂载 `/alkaid/long-term-memory` 并补侧边栏入口。如果最终改用独立 `/memory` 路由，也必须保持与 Alkaid 文案和导航一致，不要把人格记忆接到现有 `/knowledge-base` 页面里。

前端实现必须沿用当前 AstrBot Dashboard 风格：

- 使用 Vue 3 + Vuetify，不引入 React / shadcn / MaiBot Dashboard 组件。
- 优先参考 `dashboard/src/views/knowledge-base/`、`dashboard/src/views/PersonaPage.vue`、`dashboard/src/components/shared/*` 的布局、表格、对话框、toast、i18n 写法。
- 使用 `useModuleI18n` 和现有 `features/alkaid/memory.json` 文案体系，按需补齐 zh-CN / en-US / ru-RU 文案。
- API 调用通过 `dashboard/src/api/v1.ts` 和 OpenAPI generated client 接入，不手写绕过统一 HTTP 客户端。

- 记忆列表：搜索、过滤、分页、状态标签。
- 记忆详情：fact 内容、scope、证据、创建 / 更新时间、operation log。
- 删除 / 恢复：显式确认，显示 scope，避免误删其他会话记忆。
- Profile 页：按 person / chat scope 查看聚合画像，支持手动刷新。
- 运行状态卡：worker 状态、队列长度、最近错误、表统计。

### 验收

- WebUI 能看到用户刚写入的记忆。
- WebUI 删除后，聊天工具检索不到该 fact。
- 删除 / 恢复都有 operation log。
- OpenAPI 和 dashboard generated client 同步更新。
- 覆盖 API 单测、服务层单测、前端 smoke 或组件测试。

## 阶段 2：模糊维护工具与删除预览

当前 `maintain_memory` 依赖 `fact_id`。这能保证安全，但对模型和用户不够友好。

### 能力

扩展 `maintain_memory`：

- 支持 `query` / `target_text` 搜索候选记忆。
- 支持 `preview` 动作，只返回候选，不修改数据。
- 支持 `delete` / `restore` 继续要求明确 `fact_id`。
- 当候选只有一个且相似度足够高时，可允许模型直接删除，但必须写入 `reason` 和 operation log。
- 多候选时返回候选列表，要求用户确认。

### 工具返回格式

`search_memory` 和 `maintain_memory preview` 都应返回稳定结构：

```text
- [fact_id=12 status=active confidence=0.64] 用户喜欢猫娘。
```

### 验收

- 用户说“删除关于猫娘的记忆”时，模型能先 preview / search，再删除对应 fact。
- 多条相似记忆时不会批量误删。
- 不同 UMO / 群聊隔离下不会删除其他 scope 的 fact。

## 阶段 3：LLM Fact Extractor

当前正则抽取能跑通闭环，但覆盖面有限。下一步引入异步 LLM 抽取，但保留成本边界。

### 能力

- 新增 memory extraction provider task，例如 `memory_fact_extraction`。
- 抽取输入包含：
  - 当前用户消息。
  - 助手回复。
  - 最近少量对话证据。
  - 当前 scope 与 person id。
- 输出严格 JSON：
  - `fact_text`
  - `fact_type`
  - `confidence`
  - `evidence_quote`
  - `should_store`
  - `reason`
- 正则抽取继续作为低成本 fallback。
- 对低置信度、临时性、玩笑、命令、辱骂等内容默认不写入。

### 去重与更新

- 同 person + chat + fact_text 继续幂等。
- 新增相似文本去重，避免“用户喜欢猫娘”“用户很喜欢猫娘”无限堆积。
- 对冲突事实先不自动删除旧事实，标记为 `superseded` 或记录 conflict log，交给后续纠错链路处理。

### 验收

- 非模板句也能提取，例如“猫娘这种设定我确实挺吃的”。
- 明显临时语境不会写入，例如“开玩笑的我喜欢猫娘”。
- 抽取失败不影响主回复。
- 队列满、Provider 报错、JSON 解析失败都有日志。

## 阶段 4：检索质量升级

不直接上完整 A_Memorix 图谱，先做 AstrBot 低风险检索升级。

### 4.1 SQLite FTS / BM25

优先引入 SQLite FTS 表或轻量 BM25：

- facts 建全文索引。
- episodes 建全文索引。
- profile 不进入大块 prompt，只做小摘要或工具读取。

验收：

- 中文关键词和英文关键词都能稳定召回。
- 检索速度和结果数可控。
- 删除 fact 后索引同步失效。

### 4.2 Embedding 检索

在 FTS 稳定后，接 AstrBot 已有 embedding provider：

- 新增 `memory_fact_embeddings` 或将 embedding metadata 独立存表。
- 写回时异步生成 embedding。
- 检索时融合 keyword score 与 vector score。
- embedding provider 未配置时自动降级到 FTS，不报错。

验收：

- 语义近似问题能召回偏好事实。
- 未配置 embedding 不影响 memory 基础能力。
- 向量生成失败可重试、有状态可查。

## 阶段 5：中期记忆

长期 facts 不能替代上下文压缩。参考 MaiBot 的 mid-term memory，但按 AstrBot 架构重做。

### 能力

- 当历史被截断或压缩时，把被移除的对话生成一条 `memory_episode` 或专门的 `mid_term_memory` 记录。
- 生成 recall cues，供后续按当前 query 召回。
- 注入仍走 `extra_user_content_parts`，只注入短摘要。
- 大块历史不直接塞 prompt，必要时通过工具读取。

### 验收

- 清理 / 压缩上下文后，Bot 仍能通过中期记忆回忆刚才一段讨论。
- 不把中期摘要错误写成人物长期偏好。
- 中期记忆有 TTL 或最大保留数，避免无限膨胀。

## 阶段 6：纠错、反馈与审计

当 LLM 使用了错误记忆时，需要可纠正，而不是只靠删除。

### 能力

- 查询工具返回 `fact_id`、`profile_id`、`episode_id`、source metadata。
- 记录一次工具检索结果与后续回复的关联。
- 用户指出“你记错了”时，工具可创建 correction plan：
  - preview 影响范围。
  - execute 写入新 fact 或标记旧 fact。
  - rollback 撤销纠错。
- operation log 增加 `correction_id` 或关联 payload。

### 验收

- 用户能把错误偏好改正为新偏好。
- 旧事实不会物理消失，审计链可追踪。
- 回滚后检索结果恢复。

## 阶段 7：Persona Runtime 产品化

当前 runtime state 已有状态迁移和 learned assets，但还缺可见管理与更稳定的策略。

### 能力

- Dashboard 查看每个 persona + UMO 的 runtime state。
- 支持重置单个 runtime state。
- 表达 / 黑话 / 行为资产可审核、禁用、删除。
- ProactiveScheduler 先只做判定和日志，不默认主动发消息。
- cooldown、talk frequency、idle count 的变化写入 debug log 或 runtime operation log。

### 验收

- 能看到 persona 在某群的状态变化。
- 删除 learned jargon 后不再注入。
- 主动性判定不绕过平台发送安全边界。

## 暂不做

- 不直接迁入 A_Memorix 全套 paragraph / entity / relation / graph store。
- 不做旧 LPMM / 旧记忆迁移。
- 不默认跨群共享记忆。
- 不把长期记忆接到 knowledge base 页面或 knowledge base 表。
- 不在系统 prompt 中追加动态 persona state 或动态 memory。
- 不做自动对外主动发言，除非主动性判定、权限、冷却、审计全部闭环。

## 推荐实施顺序

1. Memory API + WebUI 最小管理页。
2. 模糊删除预览与 `maintain_memory` 工具升级。
3. Memory stats / self-check / worker 可观测日志。
4. LLM fact extractor。
5. FTS / BM25 检索。
6. Embedding 检索。
7. 中期记忆。
8. 纠错 / feedback / rollback。
9. Persona Runtime 管理页与主动性判定可视化。

## 每阶段必须运行的验证

后端改动：

```bash
uv run pytest tests/unit/test_persona_runtime_memory.py
uv run pytest tests/unit/test_sqlite_database.py
uv run pytest tests/unit/test_astr_main_agent.py
```

涉及 lifecycle / pipeline：

```bash
uv run pytest tests/unit/test_core_lifecycle.py
uv run pytest tests/unit/test_agent_sub_stages.py
```

涉及 API / WebUI / OpenAPI：

```bash
make format
make check
make test
```

必须补真实 smoke：

- 使用临时 SQLite 初始化 `MemoryManager`。
- 写入 fact。
- Web/API 或工具检索 fact。
- 删除 fact。
- 再次检索确认不可见。
- 查询 operation log 确认审计记录存在。

## 当前下一步切入点

建议下一次实现从阶段 1 和阶段 2 合并切入：

- 先补 dashboard memory API。
- 再补最小 WebUI 列表 / 搜索 / 删除 / 恢复。
- 同时把 `maintain_memory` 增强为 preview + delete 两段式。

这样用户能马上验证三件事：

- 前端能看见记忆。
- 前端能删除记忆。
- 聊天里也能通过工具删除记忆。
