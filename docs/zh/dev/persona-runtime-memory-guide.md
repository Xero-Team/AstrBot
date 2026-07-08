---
outline: deep
---

# AstrBot 与 MaiBot 深度对比及 Runtime 人格 / 长期记忆改造指南

## 文档目的

本文面向维护者，目标不是做泛泛而谈的项目介绍，而是回答四个具体问题：

- `AstrBot` 和 `MaiBot` 在架构、功能、安全性、性能上的差异是什么。
- 为什么 `AstrBot` 当前更适合作为通用平台，而 `MaiBot` 更适合作为陪伴型人格体。
- 这个 fork 应该从 `MaiBot` 身上重点学习什么。
- 如果要把这些能力落到 `AstrBot`，应当如何分阶段改造。

本文重点关注两件事：

1. 人格不是 prompt，而是 runtime。
2. 长期记忆不是向量检索，而是完整的产品子系统。

## 调研基准

为了避免“凭感觉评分”，本文使用四套基准做综合判断：

### 1. ISO/IEC 25010

用于评估软件质量的核心维度：

- 功能适合性
- 性能效率
- 兼容性
- 易用性
- 可靠性
- 安全性
- 可维护性
- 可移植性

### 2. ATAM

用于分析架构权衡，尤其关注：

- 扩展性
- 模块边界清晰度
- 改造成本
- 新能力接入点是否稳定

### 3. OWASP ASVS / LLM 应用安全视角

重点看：

- 提示注入影响范围
- 工具调用约束
- 长期记忆污染
- 跨会话 / 跨群记忆泄漏
- 后台自治任务的滥用风险

### 4. SRE 视角

重点看：

- 响应延迟
- 失败率
- 队列积压
- 后台任务恢复能力
- 可观测性和回滚能力

## 总体结论

一句话总结：

- `AstrBot` 更强在“平台型 Bot 基础设施”。
- `MaiBot` 更强在“陪伴型 runtime 人格体 + 长期记忆产品化”。

如果目标是：

- 多平台、多 Provider、多插件、多工具、多部署方式，`AstrBot` 更优。
- 主动聊天、关系演化、表达学习、黑话沉淀、人物画像、Episode 记忆，`MaiBot` 更优。

## 多维度评分

> 以下评分是代码走读后的定性判断，不是基于压测或量化基准得出的分数。为避免用小数点包装伪精确性，统一用「高 / 中高 / 中 / 中低 / 低」五档表示；对于没有做过对照压测、无法负责地下判断的性能项，单独标记为「未实测」。

### 以“平台型机器人底座”为目标

| 维度       | AstrBot fork | MaiBot | 说明                                                  |
| ---------- | ------------ | ------ | ----------------------------------------------------- |
| 架构扩展性 | 高           | 中高   | `AstrBot` 的平台适配、Provider、插件、Pipeline 更成熟 |
| 功能广度   | 高           | 中高   | `AstrBot` 的通用功能面明显更广                        |
| 安全治理   | 高           | 中高   | `AstrBot` 的 WebUI、API Key、TOTP、错误脱敏更完整     |
| 运维可控性 | 中高         | 中高   | 两者生命周期和平台治理都较清晰，未做量化对比          |
| 性能稳态   | 未实测       | 未实测 | 双方均未做过对照压测，不给判断                        |
| 可维护性   | 中高         | 中高   | `AstrBot` 模块边界更标准化，但未做量化对比            |
| 综合       | 高           | 中高   | 平台型场景下 `AstrBot` 更优                           |

### 以“陪伴型人格体”为目标

| 维度                   | AstrBot fork                                   | MaiBot | 说明                                                                                                                                                                                                                   |
| ---------------------- | ---------------------------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 人格运行时深度         | 低                                             | 高     | `AstrBot` 当前仍以静态 persona（`Personality` TypedDict）为主，无运行时状态机；`MaiBot` 有 `MaisakaHeartFlowChatting` 状态机（`_agent_state`/`_talk_frequency_adjust`/空闲与等待计数），但**没有独立情绪（mood）模型** |
| 主动性与时机感         | 中低（已有实验性 cron 主动任务，但非人格驱动） | 高     | `MaiBot` 有基于 @提及、未读消息阈值、未查看时长、消息间隔统计的主动回合触发；`AstrBot` 目前的主动能力是任务到点执行（`FutureTaskTool`），不是对话热度驱动                                                              |
| 表达 / 黑话 / 行为学习 | 低                                             | 高     | `MaiBot` 已有独立 `expression_learner` / `jargon_learner` 管线                                                                                                                                                         |
| 长期记忆产品深度       | 低                                             | 高     | `MaiBot` 的人物画像、Episode、回滚、调优管线均已在代码中确认存在                                                                                                                                                       |
| 记忆边界控制           | 低（暂无对应系统）                             | 中高   | `MaiBot` 用 `chat_id` + `shared_chat_ids` 控制检索范围，可配置群间共享，非简单二元隔离                                                                                                                                 |
| 关系连续性             | 低                                             | 中高   | `MaiBot` 更像持续存在的角色，而不是单轮问答 Agent                                                                                                                                                                      |
| 综合                   | 低                                             | 高     | 陪伴型场景下 `MaiBot` 明显领先                                                                                                                                                                                         |

## 代码级对比

## `AstrBot` 的现状与优势

### 1. 架构主干清晰

`AstrBot` 的主流程非常标准：

- 平台适配器接入消息
- `EventBus` 分发事件
- `PipelineScheduler` 驱动 Stage 链
- `ProcessStage` 负责 Agent / 插件处理
- `RespondStage` 发回平台

核心接入点：

- `astrbot/core/core_lifecycle.py`
- `astrbot/core/event_bus.py`
- `astrbot/core/pipeline/stage_order.py`
- `astrbot/core/pipeline/scheduler.py`

这种结构非常适合继续长功能，不需要推翻重来。

### 2. Persona 目前仍然偏“静态配置”

当前人格的核心问题不是“没有 persona”，而是 persona 还是一个静态配置对象。

现状大致是：

- 在 `astrbot/core/persona_mgr.py` 中维护 persona 数据
- 在 `astrbot/core/astr_main_agent.py` 中把 persona prompt 直接拼进 `req.system_prompt`

这意味着：

- 人格是“设定文本”，不是“运行中的行为系统”
- 当前轮动态状态和人格没有清晰分层
- 表达偏好、黑话、行为倾向没有独立生命周期

### 3. 已经有正确方向的局部认知

`AstrBot` 文档已经明确说明：

- 不要把每轮变化的动态内容持续追加到 `system_prompt`
- 动态内容更适合放到 `req.extra_user_content_parts`
- 长期记忆和大型外部知识更适合走 tool

相关文档：

- `docs/en/dev/star/guides/listen-message-event.md`

这很重要，说明 `AstrBot` 已经知道正确原则，只是还没有把它变成一个正式子系统。

### 4. 知识库强，但不是“人格记忆系统”

`AstrBot` 的 `knowledge_base/` 设计是典型文档知识库：

- 文档分块
- 稀疏 / 稠密检索
- RAG 辅助回答

这是“知识管理”，不是“人物记忆管理”。

当前缺少的不是 embedding，而是：

- 人物画像
- 关系事实
- Episode
- 写回
- 回滚恢复
- 共享边界控制
- 调优任务

### 5. 已经有一个实验性的“主动 Agent”机制，但方向和本文要补的不同

`AstrBot` 并非完全没有主动能力。`docs/zh/use/proactive-agent.md` 描述的主动 Agent 系统已经落地：

- 主 Agent 可以调用 `FutureTaskTool` 给自己注册未来的 Cron 任务
- 到时由 Cron 唤醒并执行，再通过 `send_message_to_user` 工具主动推送文本/图片/文件
- 官方标注为**实验性功能**，仅部分平台支持真正的主动推送

这套机制是“任务到点执行”驱动的（用户或 Agent 显式设了一个未来任务），不是“对话热度 / 人格状态驱动”的（不会因为“最近气氛热络”或“有未回应的话题”而自己决定要不要开口）。本文后面要补的 `ProactiveScheduler` 解决的是后一种问题，两者不冲突、可以共存，但改造时不要把它们混为一谈，也不要重新发明 Cron 任务这一层。

## `MaiBot` 的现状与优势

### 1. 人格是 runtime，不是 prompt

`MaiBot` 最值得学习的点，不是 prompt 文案，而是运行时结构。核心实现在 `src/maisaka/runtime.py` 的 `MaisakaHeartFlowChatting` 类（配合 `src/maisaka/focus/runtime_mixin.py`），真实持有的状态包括：

- `_agent_state`（running / wait / stop）
- `_talk_frequency_adjust`（回复频率倍率，近似“表达欲”，但不是独立的情绪模型）
- `_consecutive_idle_count` / `_consecutive_wait_count`（连续空闲/等待计数）
- `_forced_turn_enabled` / `_forced_turn_reason`（强制唤醒回合及原因）
- `_focus_cooldown_wakeup_scheduled`（focus 冷却唤醒调度）

需要澄清两点，避免照抄出错的字段设计：

- **没有独立的情绪（mood）字段**。`MaiBot` 不维护类似“当前情绪”的显式状态，只有回复频率倍率这类行为参数。
- **“关注对象”是聊天/群级别的 focus 槎位（见 `focus_mode_manager`），不是单个用户**。不存在按 `user_id` 记录“当前关注谁”的字段。

这让角色不是“本轮像谁”，而是“长期怎么行动”，但具体落地的状态字段比“情绪 + 关注用户”朴素得多。

### 2. 主动性是系统能力，不是幻觉

`MaiBot` 的主动聊天并不是在 prompt 里写“你要主动一点”，而是有独立的调度入口（`MaisakaHeartFlowChatting._queue_proactive_turn` / `enqueue_proactive_task`）和唤醒逻辑（`focus/runtime_mixin.py`）。经代码核实，真实的触发信号是：

- `@` 提及（`is_at` / `_arm_forced_turn`）
- 未读消息数超过阈值（`FOCUS_EVENT_UNREAD_COUNT_THRESHOLD = 3`）
- 距上次查看超过冷却时长（`focus_cool_time`）
- 最近消息平均间隔的统计触发空窗补偿（`_get_recent_average_external_message_interval`）
- 插件显式调用 `enqueue_proactive_task`

“用户点名频率”“是否存在未闭合话题”这类信号在代码里**没有找到对应实现**，属于此前草拟时的推测，已从后文“输入信号建议”中去掉，不作为参考设计。这类设计比提示词稳定得多，核心价值在于“信号可枚举、可配置”，而不是具体信号列表本身。

### 3. 记忆已经产品化

`MaiBot` 的长期记忆能力不是“向量检索 + 总结”这么简单，而是一个完整域，经代码核实均已存在：

- 检索模式 `search / time / hybrid / episode / aggregate`。但注意实现分层：`SearchExecutionService` 只原生识别 `search/time/hybrid` 三种 `query_type`；`episode`（`episode_retrieval_service.py`）和 `aggregate`（`aggregate_query_service.py`）是上层工具（`src/maisaka/builtin_tool/query_memory.py`）分流到的独立 service，不是同一个执行器内部的分支。对外呈现的五种模式名字是一致的，但底层不是单一统一入口。
- 人物画像（`person_profile_service.py`，自动聚合 + 人工覆盖两层，机制属实）
- Episode 管理（`episode_service.py` / `episode_segmentation_service.py`，确认存在，并非摘要占位）
- 调优任务（`retrieval_tuning_manager.py`，有 precision/balanced/recall 目标和验证阈值，确认存在）
- 删除恢复（`metadata_store.py` 的回收站表 + `restore_entity_by_hash` 等方法，确认存在软删除+恢复）
- 共享边界控制（`SDKMemoryKernel` 用 `chat_id` + `shared_chat_ids` 控制检索范围，可配置群间共享，不是简单的群聊/私聊二元隔离）
- 写回 worker（表达学习、黑话学习均由 `runtime.py` 的 `_run_trimmed_history_learning` 并行调度）

需要澄清一点：学习管线有**审核记录**（`expression_review_store.py` 记录 AI 审核结果及人工 reject）和**功能开关**（`_enable_expression_learning` 等配置项），但没有找到自动置信度阈值门控这类机制——回滚更多体现在人工 reject/rescue，而不是系统自动打分后拒绝。后文涉及“学习器策略”的限制条款按这个真实情况调整。

这说明它已经把“记忆”当成产品，而不是实现细节，但不代表检索模式是单一统一入口，也不代表学习管线有自动置信度门控。

## 差距本质

两边的本质差异不是模型，也不是 prompt，而是设计抽象层级不同。

`AstrBot` 当前更像：

- 消息驱动的通用 Agent 平台
- 人格是可选配置
- 记忆是上下文附加信息

`MaiBot` 更像：

- 持续存在的聊天体
- 人格是 runtime 状态机
- 记忆是独立业务系统

因此，要补齐差距，不能只“新增几个 prompt 字段”，而是要补 runtime 和 memory 两个系统。

## 改造总原则

在本 fork 内推进时，建议遵守以下原则：

1. 不做 legacy compatibility shim。
2. 不把 `knowledge_base/` 魔改成“人物记忆系统”。
3. 不把动态人格状态长期塞进 `system_prompt`。
4. 不把学习结果直接覆盖静态 persona。
5. 不把长期记忆写回放在主请求链路同步执行。
6. 默认严格隔离群聊 / 私聊记忆边界。

## 方向一：把 Persona 从静态配置升级为 Runtime

## 目标模型

建议把人格拆成三层：

### 1. Persona Seed

静态设定层，负责：

- 世界观
- 基调
- 角色规则
- 明确边界

它仍然可以保留在现有 `Persona` 表附近。

### 2. Persona Runtime State

运行时状态层，负责：

- 当前活跃倾向（对应 MaiBot 的 `_talk_frequency_adjust` 一类回复频率倍率，不建议叫“情绪”，这是行为参数不是情绪模型）
- 当前会话状态（running / wait / stop，对应 MaiBot 的 `_agent_state`；如需区分“空闲中但仍可唤醒”的内部状态，建议在 `extra_state` 中派生 `idle` 概念，而不是直接冒充上游原始枚举值）
- 连续空闲 / 等待计数
- 主动发言冷却
- 当前关注的聊天流（是“群/会话”级别的槎位，不是“关注某个用户”）

这是会变的，不应该进入长期静态设定。是否要做“情绪”这种更复杂的心理状态模型，可以作为后续独立课题，不建议在第一阶段和 MaiBot 已验证的行为参数混在一起，避免引入一个连参照对象都没有实现的概念。

### 3. Persona Learned Assets

学习资产层，负责：

- 表达方式偏好
- 黑话 / 圈内词
- 行为倾向
- 避免用语
- 关系偏好

这层必须可审计、可关闭、可回滚。

## 目标目录结构

建议新增：

```text
astrbot/core/persona_runtime/
  __init__.py
  manager.py
  models.py
  state_store.py
  injector.py
  proactive_scheduler.py
  signals.py
  learners/
    expression.py
    jargon.py
    behavior.py
```

## 运行时注入策略

### 应该放到 `system_prompt` 的内容

- 稳定不频繁变化的人设根规则
- 安全边界
- 全局行为约束

### 应该放到 `extra_user_content_parts` 的内容

- 当前活跃倾向 / 会话状态（不是“情绪”）
- 当前关系热度
- 当前关注的聊天流
- 最近 relevant memory 摘要
- 当前轮建议表达风格

### 应该走 tool 的内容

- 大段长期记忆
- 按需检索的人物画像
- Episode 历史
- 低频但高价值的外部上下文

## Persona 核心数据表建议

建议在 `astrbot/core/db/po.py` 新增以下表：

### `persona_session_states`

字段建议：

- `id`
- `persona_id`
- `umo`
- `agent_state`（running / wait / stop；若要引入 `idle`，建议作为 `extra_state` 中的派生状态而不是主枚举）
- `talk_frequency_adjust`（回复频率倍率，不叫 `mood`，避免暗示存在情绪模型）
- `consecutive_idle_count`
- `cooldown_until`
- `last_interaction_at`
- `last_proactive_at`
- `extra_state`

作用：

- 表示某个 persona 在某个聊天流里的实时状态。`focus_user_id` 这种“关注单个用户”的字段不建议加，MaiBot 的 focus 也是聊天流级别的槎位，不是用户级别；如果确实需要记录“当前更关注谁”，应作为 `extra_state` 里的可选扩展字段，而不是主表的一等字段。

### `persona_expression_assets`

字段建议：

- `id`
- `persona_id`
- `scope`
- `trigger_scene`
- `style_text`
- `source_message_id`
- `score`
- `enabled`

作用：

- 存储“在什么场景下倾向用什么表达”。

### `persona_jargon_assets`

字段建议：

- `id`
- `persona_id`
- `scope`
- `term`
- `meaning`
- `source_message_id`
- `score`
- `approved`
- `enabled`

作用：

- 存储黑话和特定语域表达。

### `persona_behavior_policies`

字段建议：

- `id`
- `persona_id`
- `scope`
- `situation`
- `preferred_action`
- `avoid_action`
- `confidence`
- `enabled`

作用：

- 存储行为偏好，如“被连续追问时简短回应”。

## 代码接入点

### 生命周期初始化

在 `astrbot/core/core_lifecycle.py` 中初始化：

- `PersonaRuntimeManager`
- `ProactiveScheduler`
- learner worker

建议与 `ConversationManager`、`PlatformMessageHistoryManager` 同级注入。

### LLM 请求前

在 `astrbot/core/astr_main_agent.py` 现有 persona 注入逻辑附近拆成两步：

1. 注入静态 `Persona Seed`
2. 注入动态 `Persona Runtime Context`

其中第二步不要再拼 `system_prompt`，而是写入 `req.extra_user_content_parts`。

### 回复完成后

在 `astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py` 的历史保存之后：

- 异步投递表达学习
- 异步投递黑话学习
- 异步投递行为学习
- 异步更新 `persona_session_states`

## 主动发言设计

### 不建议的方案

- 在 prompt 里写“你要主动一点”
- 固定 cron 定时群发
- 每次空闲都自动开口

这些方案不可控，而且会迅速造成噪音。

### 建议方案

新增 `ProactiveScheduler`，只做“是否进入主动回合”的判断。它和 `AstrBot` 现有的实验性主动 Agent（`FutureTaskTool` + `send_message_to_user`，见前文“已经有一个实验性的主动 Agent 机制”）不是同一层：现有机制响应的是“到某个时间点执行一个已注册的任务”，`ProactiveScheduler` 响应的是“当前对话状态是否值得主动开口”，两者应该独立存在，`ProactiveScheduler` 判断为“是”后可以复用现有的发送工具，但不应该复用 Cron 注册逻辑。

输入信号建议（对齐 MaiBot 已验证存在的信号，不臆造未实现的概念）：

- 最近消息平均间隔（对应 MaiBot 的 `_get_recent_average_external_message_interval`）
- `@` 提及 / 点名（对应 MaiBot 的 `is_at` / `_arm_forced_turn`）
- 未读消息数是否超过阈值
- 距上次查看是否超过冷却时长
- 是否处于冷却期
- 会话是否允许主动发言

“bot 最近是否被正向互动”“是否存在未闭合话题”这两条在 MaiBot 代码中未找到对应实现，本文不再作为参考信号；如果确实想做，应视为 `AstrBot` 自己的创新点，单独设计和验证，不要包装成“MaiBot 已经这样做了”。

输出结果不要直接发消息，而是：

1. 生成内部主动事件
2. 投递到现有主流程
3. 仍然使用统一的 Agent 处理与发送逻辑

这样可以最大限度复用现有架构。

## 学习器策略

建议第一阶段只做“弱自治学习”。需要说明一点：下面的“限制”里，“审核记录”“开关”是 MaiBot 已验证存在的机制（`expression_review_store.py` 记录审核结果、`_enable_expression_learning` 等配置开关），但“自动置信度阈值门控”在 MaiBot 代码中没有找到对应实现——它的回滚更依赖人工 reject，不是系统自动打分拒绝。以下限制条款按这个真实情况写，不再声称参照了 MaiBot 的置信度机制。

### 表达学习

目标：

- 从高质量历史中抽取“场景 -> 表达风格”

限制：

- 只学习 bot 自身输出
- 保留审核记录（谁审核、是否通过、是否人工修改），不做自动置信度打分拒绝
- 不直接覆盖静态 prompt
- 提供独立开关，可整体关闭

### 黑话学习

目标：

- 识别稳定出现的圈内词、简称、梗

限制：

- 至少多次复现
- 默认需要人工审核或白名单启用
- 必须允许快速禁用

### 行为学习

目标：

- 学习“什么时候追问、什么时候停、什么时候简答”

限制：

- 不学习价值观
- 不从对抗性样本中学习
- 不在低样本场景强行归纳
- 提供独立开关，可整体关闭

## 方向二：把长期记忆做成产品子系统

## 为什么不能直接复用 `knowledge_base/`

`knowledge_base/` 解决的是“文档如何被切块与检索”，而长期记忆要解决的是：

- 谁的事实被记住
- 记忆来自哪段对话
- 是否允许跨会话共享
- 是否可以删除 / 恢复 / 保护
- 是否形成画像
- 是否形成 Episode

这两者的数据模型、生命周期和安全边界都不同。

因此建议独立新增：

```text
astrbot/core/memory/
  __init__.py
  manager.py
  models.py
  retrieval/
    manager.py
    ranker.py
  writeback/
    worker.py
    fact_extractor.py
    episode_builder.py
    profile_refresher.py
  policy/
    scope.py
  tools/
    memory_tools.py
  tuning/
    task_manager.py
```

## 记忆系统目标对象

至少应包含以下对象：

### 1. Person Facts

人物事实，例如：

- 用户喜欢什么
- 用户讨厌什么
- 用户近期正在做什么
- 用户和 bot 的关系线索

### 2. Person Profiles

人物画像，不是原始事实堆，而是聚合后的可用快照。

### 3. Episodes

将多条消息归纳成一次事件或阶段性事件，便于跨轮引用。

### 4. Scope Policies

定义记忆能否在不同聊天流之间共享。

### 5. Operation Logs

所有删除、恢复、冻结、保护、回滚都必须有操作记录。

### 6. Tuning Tasks

用于调检索参数、评估召回质量，而不是盲目改 top-k。

## Memory 核心数据表建议

### `memory_facts`

字段建议：

- `id`
- `person_id`
- `chat_id`
- `scope_id`
- `fact_text`
- `fact_type`
- `source_message_id`
- `evidence_message_ids`
- `confidence`
- `status`
- `ttl_at`

### `memory_profiles`

字段建议：

- `id`
- `person_id`
- `chat_scope`
- `profile_text`
- `source_version`
- `is_override`
- `updated_at`

### `memory_episodes`

字段建议：

- `id`
- `episode_id`
- `chat_id`
- `title`
- `summary`
- `participant_ids`
- `start_at`
- `end_at`
- `source_message_ids`
- `status`

### `memory_scope_policies`

字段建议：

- `id`
- `scope_type`
- `owner_scope_id`
- `target_scope_id`
- `sharing_mode`
- `enabled`

### `memory_operation_logs`

字段建议：

- `id`
- `operation_id`
- `operator`
- `target_type`
- `target_id`
- `action`
- `reason`
- `payload`
- `created_at`

### `memory_tuning_tasks`

字段建议：

- `id`
- `task_id`
- `task_type`
- `target_scope`
- `candidate_config`
- `evaluation_result`
- `status`

## 检索模式设计

建议明确支持以下模式，不要只提供一个“搜索记忆”：

### `search`

普通语义检索，适合查常规事实。

### `time`

按时间窗检索，适合“最近”“上周”“昨天”。

### `hybrid`

时间 + 语义联合召回，适合“最近提到的某件事”。

### `episode`

按事件召回，适合“那次一起讨论迁移方案时说过什么”。

### `aggregate`

按人物、主题、聊天流做聚合摘要，适合构造画像和阶段总结。

## 写回链路设计

### 总原则

写回一定要异步，不要阻塞主回复链路。

### 建议流程

1. 主链路完成消息处理。
2. 历史持久化完成。
3. 将候选消息投递到 `MemoryWritebackWorker`。
4. worker 依次执行：
   - 事实提取
   - Episode 聚合
   - 画像刷新
   - 操作记录写入
5. 失败任务可重试，必要时可人工重放。

### 去重策略

必须至少支持：

- `external_id` 幂等
- `source_message_id` 去重
- 高相似事实合并
- 同一 Episode 窗口内聚合

## 人物画像设计

画像建议由三层组成：

### 1. 自动画像

由高置信事实和活跃 Episode 自动聚合。

### 2. 人工覆盖画像

用于修正自动画像中的偏差。

### 3. 注入摘要

注入到当前轮上下文的不是完整画像，而是裁剪后的内部参考块。

建议遵循这条原则：

- 画像只作为内部推理参考
- 不要要求模型逐字复述画像
- 当前对话内容优先级高于历史画像

## Episode 设计

Episode 应被视为“可引用事件对象”，而不是普通摘要。

应至少支持：

- 自动生成
- 待处理队列
- 重建
- 查看状态
- 根据 source message 回溯

适合用来解决的问题：

- “我们上次争论过什么”
- “这个用户最近一周主要在忙什么”
- “这个群最近的主线话题是什么”

## 跨群 / 私聊边界控制

这是长期记忆系统最容易出事的地方，必须默认保守。

以下三档模式是给 `AstrBot` 设计的简化版本，不是 MaiBot 原样实现。MaiBot 实际是按 `chat_id` + `shared_chat_ids` 做更细粒度的“哪些聊天流之间互相可召回”配置（`SDKMemoryKernel._resolve_allowed_chat_ids`），不是全局三档开关。这里选择三档模式是为了降低第一阶段的配置复杂度，之后如果需要更细粒度的共享组，再扩展到类似 MaiBot 的按 chat 配置。

### 推荐的三档模式

#### `isolated`

- 默认模式
- 私聊、群聊、不同群之间都不共享

#### `group-shared`

- 只有显式配置到同一共享组的聊天流可以共享召回范围

#### `global-shared`

- 只有管理员明确开启时才允许全局共享

### 强制要求

- 默认值必须是 `isolated`
- 共享只扩大检索范围，不改写原始写入归属
- 所有共享策略必须可审计

## 对当前代码库的具体修改建议

## 第一批新增模块

建议直接新增两个一级模块：

- `astrbot/core/persona_runtime/`
- `astrbot/core/memory/`

不要把这些逻辑继续塞到：

- `persona_mgr.py`
- `knowledge_base/`
- `conversation_mgr.py`

这些模块应继续保持各自职责边界。

## 第一批改动文件

### `astrbot/core/core_lifecycle.py`

新增初始化与关闭逻辑：

- `PersonaRuntimeManager`
- `MemoryManager`
- `MemoryWritebackWorker`
- `ProactiveScheduler`

### `astrbot/core/astr_main_agent.py`

拆分人格注入：

- 静态 persona seed 继续保留
- 动态 runtime context 单独注入
- 长期记忆摘要单独注入

### `astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py`

在历史落盘后追加异步投递：

- runtime state 更新
- learner 任务
- memory writeback 任务

### `astrbot/core/db/po.py`

新增上述数据表定义。

### `astrbot/core/db/sqlite.py`

补充新表访问和迁移支持。

### `astrbot/core/tools/`

新增长期记忆工具，而不是复用知识库工具。

建议工具至少包括：

- `search_memory`
- `get_person_profile`
- `query_episode`
- `maintain_memory`

## WebUI / API 建议

如果只做后台能力，不给可视化入口，后期基本不可维护。

建议至少补三类页面：

### 1. Persona Runtime 管理

- 当前会话状态
- 主动发言开关
- 学习开关
- 黑话审核

### 2. Memory 管理

- 事实查询
- 画像查看与 override
- Episode 查看
- 删除 / 恢复 / 冻结 / 保护

### 3. Scope Policy 管理

- 当前聊天流边界
- 共享组配置
- 风险提示

## 分阶段实施路线

## Phase 1：打底座

目标：

- 建立 runtime 和 memory 两个独立子系统
- 不影响现有主流程稳定性

范围：

- 新表：`persona_session_states`、`memory_facts`、`memory_profiles`、`memory_operation_logs`
- 新 manager 和 worker
- 动态上下文改走 `extra_user_content_parts`

完成标准：

- 不增加显著主链路延迟
- 能完成基础事实写回和画像查询

## Phase 2：让人格真正活起来

目标：

- 增加主动性和学习能力

范围：

- `ProactiveScheduler`
- 表达学习
- 黑话学习
- 行为学习
- 会话级 `talk_frequency_adjust` / `agent_state` / `cooldown`

完成标准：

- 白名单会话中可控地主动发言
- 学习结果可关闭、可审计

## Phase 3：把长期记忆做成产品

目标：

- 补齐 Episode、检索模式、边界策略、回滚与调优

范围：

- `episode` / `aggregate` 检索
- 回滚恢复
- tuning task
- scope policy

完成标准：

- 记忆具备完整管理能力，不再只是底层检索组件

## 风险与防线

## 1. Prompt Cache 被破坏

风险：

- 如果把动态人格状态和记忆摘要持续拼进 `system_prompt`，会导致 provider 侧缓存失效。

防线：

- 静态设定留在 `system_prompt`
- 动态上下文走 `extra_user_content_parts`
- 大块记忆走 tool

## 2. 跨群记忆泄漏

风险：

- 一个群的信息被另一个群检索到。

防线：

- 默认 `isolated`
- 共享组显式配置
- 所有召回记录带 scope 审计信息

## 3. 学习污染

风险：

- 恶意用户诱导 bot 学脏话、错误事实、异常行为。

防线：

- 黑话学习默认审核
- 行为学习只学习经审核样本或多次复现样本
- 学习资产可快速禁用和回滚

## 4. 后台任务堆积

风险：

- 写回和 learner 队列失控，拖垮系统。

防线：

- 队列限长
- 超时与重试上限
- 失败告警
- 可暂停后台写回

## 测试建议

## 单元测试

- runtime 状态迁移
- scope policy 裁剪
- 事实去重
- 画像刷新
- operation log 回滚

## 集成测试

- 一轮对话后是否正确写入 fact / profile / episode
- 不同群之间是否错误共享召回结果
- 主动发言是否遵守 cooldown

## 性能测试

- 写回队列积压
- 检索 P95 延迟
- 动态注入对 TTFT 的影响

## 安全测试

- 提示注入导致错误记忆写入
- 恶意黑话污染
- 共享组越权读取

## 最终建议

如果这个 fork 只想继续做“更现代的 AstrBot”，那么当前路线已经足够强。

但如果目标是把它推进到“陪伴型人格体”方向，那么最关键的不是继续调 prompt，而是补齐以下两个正式子系统：

1. `persona_runtime`
2. `memory`

应当学 `MaiBot` 的，不是某条提示词，而是两种设计思想：

- 人格是持续运行的行为系统
- 长期记忆是可运营、可审计、可回滚的产品能力

这两点一旦补上，`AstrBot` 的平台底座优势才有可能转化成更强的上层人格体验。
