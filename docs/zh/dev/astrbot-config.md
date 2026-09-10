# AstrBot 配置参考

AstrBot 的配置会随 Provider、平台适配器和 Agent 能力持续演进。本页记录当前稳定的配置分组、默认行为和运维边界，不维护一份手抄的“完整默认配置”。

当前代码的权威来源是：

- 默认值：`astrbot/core/config/default.py` 中的 `DEFAULT_CONFIG`；
- WebUI 字段元数据：同文件中的 `CONFIG_METADATA_3` 和 `CONFIG_METADATA_3_SYSTEM`；
- 加载、完整性检查和密码迁移：`astrbot/core/config/astrbot_config.py`。

## 配置文件位置与加载行为

默认配置文件是运行根目录下的 `data/cmd_config.json`。设置 `ASTRBOT_ROOT` 后，路径变为 `$ASTRBOT_ROOT/data/cmd_config.json`。

WebUI 创建的其他配置档位于 `data/config/abconf_<uuid>.json`。消息会话与配置档的绑定由配置管理器维护；不要通过重命名文件来移动绑定关系。

配置文件由 Python 标准 JSON 解析器读取，因此必须是**严格 JSON**：

- 布尔值使用 `true` / `false`；
- 不允许注释；
- 不允许尾随逗号；
- 字符串和键必须使用双引号。

启动时，AstrBot 会递归补上缺失的当前默认键、调整顺序，并删除不在当前默认结构中的未知键。手动添加未被当前代码支持的字段并不能扩展配置。

> [!TIP]
> 优先使用 WebUI：配置档相关设置位于 **配置文件**，Provider 和模型位于 **提供商**，平台实例位于 **机器人**，进程级设置按类别位于 **设置**。直接编辑 JSON 后应重启 AstrBot，并先保留一份副本。

## 顶层结构

| 键                                                | 用途                                                                                                                                                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `config_version`                                  | 当前核心配置结构版本，默认 `3`，不要手动降级。                                                                                                                     |
| `platform_settings`                               | 所有消息平台共用的收发、白名单、限流和分段回复行为。                                                                                                               |
| `provider_sources`                                | API 端点和凭据等 Provider 来源。由“提供商”页面维护。                                                                                                               |
| `provider`                                        | 具体聊天、STT、TTS、Embedding、Rerank 等模型实例。                                                                                                                 |
| `agent_runner`                                    | 当前配置档的 Agent 执行器类型及其内联配置。                                                                                                                        |
| `provider_settings`                               | 当前配置档的 AI 开关、检索、流式输出、Computer Use 等共用行为。                                                                                                    |
| `subagent_orchestrator`                           | 子代理 handoff 编排。                                                                                                                                              |
| `provider_stt_settings` / `provider_tts_settings` | 语音转文本和文本转语音默认模型及开关。                                                                                                                             |
| `provider_ltm_settings`                           | [群聊上下文感知](../use/group-chat-context)（内存群聊上下文、图片转述、持久化群消息历史）。JSON 键仍为历史名称；不是 Alkaid 长期记忆开关。群聊随机主动回复已移除。 |
| `content_safety`                                  | 内置关键词和可选外部内容安全检查。                                                                                                                                 |
| `dashboard`                                       | WebUI 监听、认证、限流和 TLS；账户身份及 TOTP 权威状态由 Dashboard 数据库保存。                                                                                    |
| `platform` / `platform_specific`                  | 平台实例，以及 Lark、Telegram、Discord 等平台特异行为。                                                                                                            |
| `command_prefixes`                                | 指令头前缀，默认 ["/"]。                                                                                                                                           |
| `llm_access`                                      | 当前配置档的私聊和群聊 LLM 访问策略；默认 `private=prefix`、`group=prefix`、`prefixes=["/"]`。                                                                     |
| `inbound_coalesce`                                | 可选的连续私聊 LLM 消息有界合并，默认关闭。                                                                                                                        |
| 其他顶层键                                        | 管理员、T2I、代理、日志、时区、插件、知识库、Trace 和指标等。                                                                                                      |

`provider_sources`、`provider` 和 `platform` 中的对象结构由各类型注册的当前模板决定。不要从旧文档复制对象；在 WebUI 创建后再检查保存结果。模型通过 `provider_source_id` 引用来源，重命名或删除来源时应让 WebUI 同步引用。

## 入站路由

用户向步骤见 [群聊何时会理我](../use/group-wake)。`command_prefixes` 和 `llm_access` 都读取事件实际选中的配置档。`command_prefixes` 只负责指令头，不会与 LLM 前缀自动拼接。`llm_access.prefixes` 的每一项都是用户实际输入的完整字符串，按词边界和最长匹配处理。非空 LLM 前缀会在同一配置档占用其第一个指令根；如果与已启用指令冲突，Dashboard 会拒绝保存。

| 键                                   | 可选值                    | 说明                                                                                             |
| ------------------------------------ | ------------------------- | ------------------------------------------------------------------------------------------------ |
| `llm_access.private`                 | `open` / `prefix` / `off` | 默认 `prefix`。私聊始终允许、必须带 LLM 前缀，或不打开新的 LLM 回合；已有续片仍可继续。          |
| `llm_access.group`                   | `open` / `prefix` / `off` | 群聊 LLM 的基础门禁。提及不是门禁；旧值 `mention` / `prefix_or_mention` 运行时按 `prefix` 处理。 |
| `llm_access.reply_to_bot`            | `true` / `false`          | 将“回复机器人”作为群聊 LLM 访问的额外 OR 条件。                                                  |
| `inbound_coalesce.enable`            | `true` / `false`          | 启用有界回合窗口，默认关闭；当前实现只合并私聊消息。                                             |
| `inbound_coalesce.wait_seconds`      | 数字                      | 缓冲回合的静默等待时间。                                                                         |
| `inbound_coalesce.max_total_seconds` | 数字                      | 缓冲回合的最长生命周期，不因新片段而延长。                                                       |
| `inbound_coalesce.max_typing_wait`   | 数字                      | 输入停止通知丢失时，自动恢复暂停回合的保护时间。                                                 |

路由顺序是先匹配指令，再判断 LLM 访问。命中指令时只执行指令；裸指令组输出帮助；未知子指令输出 Orbit 诊断且不会回落到 LLM。否则事件通过 LLM 门禁或被丢弃。通知和请求属于透传事件。启用合并后，私聊窗口中的后续片段不再要求重复 LLM 前缀；收到指令会丢弃缓冲回合。NapCat 的 `input_status` 只暂停或恢复回合窗口，不会进入消息 Pipeline。

## `platform_settings`

常用字段如下：

| 键                                        | 默认值                      | 说明                                                                                                        |
| ----------------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `unique_session`                          | `false`                     | 是否为群内成员拆分独立会话。                                                                                |
| `group_sender_concurrency`                | `false`                     | 实验性。同群不同发送者可并行生成，发送仍按群整轮排队。与 `unique_session` 互斥；会关闭同群流式。            |
| `rate_limit`                              | `60` 秒 / `30` 条 / `stall` | 超限时等待（`stall`）或丢弃（`discard`）。                                                                  |
| `enable_id_white_list`                    | `true`                      | 启用 ID 白名单；管理员是否绕过由两个 `wl_ignore_admin_*` 字段控制。                                         |
| `reply_prefix`                            | `""`                        | 所有回复的前缀。                                                                                            |
| `reply_with_mention` / `reply_with_quote` | `false`                     | @ 用户或引用原消息，实际能力取决于适配器。                                                                  |
| `forward_threshold`                       | `1500`                      | OneBot `aiocqhttp` 适配器的长回复转发阈值；其他平台是否支持取决于适配器。                                   |
| `segmented_reply`                         | 见默认配置                  | 非流式结果的分段、间隔、清理规则。                                                                          |
| `path_mapping`                            | `[]`                        | 将平台事件中的容器路径映射到 AstrBot 可访问路径，格式为 `原路径:目标路径`。该功能仍在收发 pipeline 中使用。 |
| `ignore_bot_self_message`                 | `false`                     | 忽略机器人自身消息。`ignore_at_all` 仍会写入磁盘，但不参与内置 LLM 门禁。                                   |

`path_mapping` 示例：

```json
{
  "platform_settings": {
    "path_mapping": [
      "/app/.config/QQ:/var/lib/docker/volumes/napcat_data/_data"
    ]
  }
}
```

这是局部示意，不应覆盖完整文件。Windows 驱动器号本身含冒号，建议通过 WebUI 配置并在实际平台消息上验证。

## `agent_runner`

配置档的 AI 执行入口。形状为 `{ "runner_type": "local"|"dify"|"coze"|"dashscope"|"deerflow", "config": {...} }`。聊天模型、Persona、压缩和步数上限都写在这里，不要再放到 `provider_settings`。

### 模型选择与重试

- `agent_runner.config.model.provider_id`：本地 Agent 的默认聊天模型 ID。
- `agent_runner.config.model.fallback_provider_ids`：主模型失败时按顺序尝试的聊天模型 ID。
- `agent_runner.config.model.request_max_retries`：单个模型请求最大重试次数，默认 `5`；fallback 与单模型重试是不同层次。

### Persona

- 本地 Runner：`agent_runner.config.persona.persona_id`。
- 第三方 Runner：`agent_runner.config.persona_id`。
- 健康模式：`agent_runner.config.persona.safety_mode`。

选择优先级和权限语义见 [Persona 人格设定](../use/persona)。

### 上下文压缩

这些字段位于 `agent_runner.config.compression`：

| 键                    | 默认值              | 说明                                                    |
| --------------------- | ------------------- | ------------------------------------------------------- |
| `overflow_strategy`   | `llm_compress`      | `llm_compress` 或 `truncate_by_turns`。                 |
| `keep_recent_ratio`   | `0.15`              | 原样保留最近上下文的 token 比例，范围限制为 `0`–`0.3`。 |
| `provider_id`         | `""`                | 留空时使用当前会话聊天模型。                            |
| `instruction`         | 内置五点指令        | 摘要提示词。                                            |
| `max_turns`           | `-1`                | 压缩前最多保留的对话轮数；`-1` 不限制。                 |
| `trim_turns`          | `1`                 | 按轮截断时一次丢弃的轮数。                              |
| `fallback_max_tokens` | 运行时默认 `128000` | 模型未配置窗口且内置元数据无法识别时的兜底值。          |

完整行为见 [自动上下文压缩](../use/context-compress)。

### 步数、工具与代理

- `agent_runner.runner_type`：`local` 使用内置 Agent；也可选择 Dify、Coze、DashScope 或 DeerFlow。第三方 Runner 的密钥和应用 ID 写在 `agent_runner.config` 中。
- `agent_runner.config.misc.max_steps`：本地 Agent 单次运行最大 step，默认 `30`，也适用于当前子代理执行。
- `agent_runner.config.max_steps`：第三方 Runner 的 step 上限，默认 `30`。
- `agent_runner.config.misc.tool_call_timeout`：单次工具调用超时秒数，默认 `120`。
- `agent_runner.config.misc.tool_schema_mode`：`full` 发送完整工具 schema；`skills_like` 使用较轻的两阶段 schema，只藏参数，不改变工具目录。
- `agent_runner.config.misc.sanitize_context_by_modalities`：按当前模型能力清理历史中的不支持模态和工具结构，会改变模型实际看到的上下文。
- `agent_runner.config.proxy_mode` / `proxy_url`：第三方 Runner 的出站代理；`inherit` 跟随全局代理，`direct` 明确直连，`custom` 仅使用 `proxy_url`。

## `provider_settings`

### Provider 选择与重试

- `enable`：是否启用 AI Provider 处理，默认 `true`。
- `provider_pool`：本配置档可用 Provider 范围，`["*"]` 表示全部。
- `default_image_caption_provider_id` 和 `image_caption_prompt`：主 Agent 当前请求和引用图片的转述，不受群聊历史限流影响。
- `provider_ltm_settings.image_caption_*`：只作用于[群聊上下文感知](../use/group-chat-context)的历史图片转述。`image_caption_scope` 为 `all` / `allowlist` / `denylist`；`image_caption_groups` 只接受完整 UMO；`image_caption_min_interval` 和 `image_caption_max_concurrency` 限制间隔与全局并发。`image_caption_cache_ttl` 默认 `0`（关闭），缓存按 UMO+内容隔离。`image_caption_lazy` 默认关闭。
- 群聊 JSON 卡片会进入群聊上下文，并在普通 LLM 请求缺少文本 prompt 时作为 `[Shared Card]` 卡片摘要。

API Key 属于敏感配置。不要把真实 `cmd_config.json`、截图、日志或备份提交到 Git；日志和 Trace 也可能包含 Provider ID、请求错误或工具输出。

### Persona、提示词与会话

- `persona_pool`：本配置档可选 Persona，`["*"]` 表示全部。
- `prompt_prefix`：用户提示词模板。占位符语法是无逻辑的 `{{name}}`，不是 Jinja2。允许的键只有 `prompt`。模板含 `{{prompt}}` 时替换为用户输入；不含该占位符时，把前缀拼在用户输入前面。Persona `system_prompt` 和 workspace `EXTRA_PROMPT.md` 不是模板。
- 内置 LLM 模板使用同一套 `{{name}}` 语法。cron 唤醒允许 `cron_job`；后台任务唤醒允许 `background_task_result`；tool-loop 通知允许 `follow_up_lines`、`tool_names`、`tool_name`、`streak`、`overflow_path`、`read_tool_hint`。未知 `{{name}}` 保持字面量，替换值不会再次扫描。
- `identifier`、`group_name_display`、`datetime_system_prompt`：向提示词加入用户 ID、群名或当前时间。

默认 Persona ID 在 `agent_runner` 中配置。选择优先级见 [Persona 人格设定](../use/persona)。

### 工具展示

- `show_tool_use_status` / `show_tool_call_result`：向用户显示工具状态及结果摘要。
- `buffer_intermediate_messages`：非流式多 step 运行时合并中间文本。
- `proactive_capability.add_cron_tools`：向本地 Agent 提供主动任务/Cron 工具。

### 流式输出

- `streaming_response`：启用 Provider 流式响应。
- `unsupported_streaming_strategy`：平台不支持原生流式回复时，使用 `realtime_segmenting` 实时分段，或 `turn_off` 关闭该次流式回复。
- 会话级 `/flow enable|disable|unset|status` 可覆盖全局值。有效优先级为 `event.extra["enable_streaming"]` > 会话覆盖 > `provider_settings.streaming_response`。请求开始时固定有效值，运行中的 Agent 不会因中途执行 `/flow` 改变模式。

旧字段 `provider_settings.streaming_segmented` 已删除，不要重新加入。

### Computer Use 与沙箱

- `computer_use_runtime`：`none`、`local` 或 `sandbox`，默认 `none`。
- `computer_use_require_admin` 已不再作为运行时授权开关。电脑能力按 `tool.computer_use`、`tool.local_exec`、`tool.file_read` 和 `tool.file_write` 等动作统一授权。WebChat 高风险实例工具仍要 step-up；IM 上绑了该配置 `instance_operator` 则免 step-up。
- `sandbox.booter`：`shipyard_neo` 或 `cua`，其余字段保存 endpoint、token、profile、TTL 或 CUA 系统/遥测/本地模式配置。

本地模式直接操作 AstrBot 主机，应仅在可信环境使用。沙箱也不是自动授权边界；仍需限制管理员、Persona 工具和外部网络。

### 搜索与图片

`web_search`、`websearch_provider` 及各 Provider Key 控制内置网页搜索；`web_search_link` 控制是否附加链接。密钥应在 WebUI 中填写。

`image_compress_enabled` 和 `image_compress_options.max_size/quality` 控制请求准备卡口 `prepare_provider_request` 中的图片处理，主智能体聊天路径、SDK `llm_generate` 与 `tool_loop_agent` 共用该卡口。送给模型的图片在此处转为 JPEG，最长边只缩小、从不放大；动画 GIF/WebP 会按 dhash 抽帧，最多 8 帧。关闭压缩时仍会转 JPEG，但不缩放。主智能体只把适配器引用物化为本地路径，不在组装附件时预编码 JPEG。`max_quoted_fallback_images` 与 `quoted_message_parser` 限制引用消息和转发消息展开深度，避免无限抓取。对 `quoted_message_parser` 而言，`0` 是有效边界：深度限制会保留根层并停止子层递归，`max_forward_fetch=0` 会禁止递归调用 `get_forward_msg`。负数或无效值会回退为默认值；该设置不会全局禁止引用消息回退路径中的直接 `get_msg` 调用。

## BTW 模型选择

本地 Agent 配置启用 `btw.enabled` 后，`btw.conversation_loop.provider_id` 与 `btw.work_loop.provider_id` 分别选择两个循环的对话模型。已配置的循环模型优先于事件或会话的模型选择；留空则沿用当前选择，包括配置档默认模型。没有显式工作循环标记的消息使用对话循环模型。关闭 BTW 后不应用这两个覆盖项。

所选提供商仍须是已配置的对话模型。不存在或类型不适用的循环提供商沿用现有模型选择错误路径，不会静默改用另一个循环的模型。已有模型回退和重试设置继续作用于所选主模型。

### Computer Use 边界

启用 BTW 后，对话循环的 Computer Use 固定为 `none`，并约束其子代理转交与显式传入的工具。宿主机 Shell、Python、文件系统、浏览器、CUA 和沙箱 Skill 生命周期工具不会进入对话循环工具目录。普通 Skill 手册仍可通过 `read_skill` 阅读。

`btw.work_loop.computer_use_runtime` 支持 `inherit`（默认）、`none`、`local` 和 `sandbox`。`inherit` 沿用 `provider_settings.computer_use_runtime`。实际运行时同时作用于工作请求及其子代理转交；`none` 也会排除显式声明的电脑工具。关闭 BTW 后沿用现有 Computer Use 配置。这些设置只选择能力，不授予角色，也不绕过授权、WebChat step-up、路径限制或沙箱检查。

## BTW 插件工具循环分配

在配置档中启用 BTW 后，可通过 **配置文件 → BTW 双循环 → 插件工具循环分配** 为每个已启用的非系统插件选择对话循环、工作循环或两者。未分配的插件默认仅工作循环可用；选择两者会保存显式覆盖，重新选择工作循环会移除覆盖。关闭 BTW 后保留普通工具可用性。

主 Agent 与其子 Agent handoff 应用相同分配，并继续遵守 Persona、配置档与授权限制。循环分配不会授予工具执行权限。插件事件处理器和显式命令保留原有执行路径；此设置不会把整个插件转换为后台任务。

## BTW MCP 工具循环分配

启用 BTW 后，可通过 **MCP 服务器循环分配** 为每个已启用服务器选择对话循环、工作循环或两者。服务器的所有工具在主 Agent 和子 Agent handoff 中遵循同一分配。没有覆盖条目的服务器默认仅工作循环可用；选择两者会保存显式覆盖，重新选择工作循环会移除覆盖。关闭 BTW 后保留普通 MCP 工具可用性。

分配按配置档保存，只控制工具可见性，不替代 MCP 读写授权，也不改变现有连接、私网访问和重定向限制。

## BTW Skill 循环可见性

启用 BTW 后，可通过 **Skills 循环分配** 为每个已启用的普通 Skill 选择对话循环、工作循环或两者。普通 Skill 默认在两个循环可见；选择单一循环会保存覆盖，重新选择两者会移除覆盖。工作区 Skill 仅在使用 `local` 运行时的工作循环中可用。关闭 BTW 后保留标准 Skill 选择路径。

循环分配在请求 Skill 快照冻结之前筛选已启用的 Skill，因此提示词、`read_skill` 和 Skill 声明的候选工具使用同一选择结果。Persona 与插件限制继续生效，包括 Persona 的空 Skill 列表。循环分配不会授予执行权限：Computer Use 为 `none` 时，`read_skill` 仍可读取允许的 Skill 手册，但 Shell 和 Python 仍不可用。

## 子代理、语音与知识库

- `subagent_orchestrator.main_enable`：启用 handoff。
- `remove_main_duplicate_tools`：只移除主 Agent 与子 Agent 重叠的工具；默认 `false`。
- `router_system_prompt` 和 `agents`：路由提示词与子 Agent 定义。推荐通过专用页面维护，详见 [子代理编排](../use/subagent)。
- `provider_stt_settings`：STT 总开关和默认模型。
- `provider_tts_settings`：TTS 模型、双输出、文件服务和 `0`–`1` 触发概率。
- `kb_names`、`kb_fusion_top_k`、`kb_final_top_k`：默认知识库和检索数量。
- `kb_agentic_mode`：将知识库检索作为工具交给模型自主调用。

Alkaid [长期记忆](../use/long-term-memory) 当前没有对应的启停配置；不要把 `provider_ltm_settings` 当作长期记忆开关。群聊近期消息注入见 [群聊上下文感知](../use/group-chat-context)。

## BTW 对话入口

`btw.enabled` 默认为 `false`。开启后，普通且已通过准入的 AI 请求经对话循环进入现有 Agent 执行器，不绕过消息准入、会话 AI 开关或插件请求处理。关闭 BTW 时，流水线直接使用当前 Agent 请求路径，并保留其能力。

自动分类器候选将分别评估。开启此入口不会选定自动路由方案。

工作执行器还需要开启 `btw.work_loop.enabled`，默认同样为 `false`。它复用 Agent 执行器并记录排队、运行、完成、失败、取消状态。`btw.work_loop.max_concurrent` 限制正在执行的任务数，默认 `2`，不限制等待队列长度。`btw.work_session.max_age_seconds` 默认保留终态记录 `3600` 秒；活动任务不会过期，终态过期记录在下次会话操作时清除。调度器接入后台服务后，由运行时拥有工作任务的执行和清理。

后台工作在执行前确认接收，再通过当前回复装饰与发送阶段回送结果，包括回复内容检查；不重复运行入站阶段。WebChat 持续使用原请求标识，确认消息不会结束请求。事件临时文件保留到工作完成、失败或取消后再释放。配置档替换、删除以及运行时关闭会取消并回收其工作任务。

## WebUI 与认证

`dashboard` 的关键默认值：

| 键                       | 默认值        | 说明                                                                                    |
| ------------------------ | ------------- | --------------------------------------------------------------------------------------- |
| `enable`                 | `true`        | 启用 WebUI/API。                                                                        |
| `username`               | `astrbot`     | 初始用户名。                                                                            |
| `host`                   | `127.0.0.1`   | 默认只监听 loopback。远程访问必须显式改为 `0.0.0.0` 或指定接口，并配置防火墙/反向代理。 |
| `port`                   | `6185`        | HTTP(S) 监听端口。                                                                      |
| `trust_proxy_headers`    | `false`       | 是否信任 `X-Forwarded-For` / `X-Real-IP`；只应在受控反向代理后启用。                    |
| `auth_rate_limit.enable` | `true`        | 登录、TOTP 等认证端点限流。                                                             |
| `totp.*`                 | 由 WebUI 管理 | 为配置导出保留的 Dashboard TOTP 快照，不是账户认证的权威来源。                          |
| `ssl.enable`             | `false`       | 由 AstrBot 直接终止 TLS；证书、私钥和可选 CA 使用对应路径字段。                         |

密码以 PBKDF2 哈希存放在 `pbkdf2_password`。新写入会把 `password` 留空。已有部署里 `password` 中的 MD5 值仍可用于登录，直到下次改密。不要在 JSON 中写明文，也不要手工生成或交换哈希。忘记密码时使用：

```bash
uv run astrbot run --reset-password
```

源码入口也支持 `uv run main.py --reset-password`。启动日志会输出新生成的临时密码，并要求登录后修改。

Dashboard 账户有稳定的 `account_id`，其 TOTP 密钥、恢复码哈希和受信任设备均按账户保存。安全页面会同步 `dashboard.totp` 快照，供配置导出和界面使用，但登录和高风险操作只验证账户记录。不要手工编辑该快照、在账户之间复制 TOTP 字段，或把它当作丢失恢复码后的绕过方式。

## 系统、日志与输出装饰

- `t2i`、`t2i_word_threshold`：将超过阈值的**输出结果**渲染为图片；`t2i_active_template` 由模板管理页面维护。
- `t2i_use_file_service`：用文件 token URL 暴露渲染结果，需要正确设置 `callback_api_base`。
- `http_proxy` / `no_proxy`：全局出站代理和直连名单。它们不再写入进程级 `HTTP_PROXY`。
- Telegram 会将该显式路由同时用于 Bot API 请求和 `getUpdates` 长轮询。没有适用代理时，两个客户端都会直连且不会继承进程代理变量。
- Provider / Platform 使用三态 `proxy_mode`：`inherit` 跟随全局配置，`direct` 明确直连并忽略环境变量代理，`custom` 只使用本项 `proxy_url`。空字符串不再同时表示继承和直连。
- GitHub 镜像默认不提供。插件 `download_url` 和镜像前缀必须是公开 HTTPS origin，私网和非 HTTPS 会被拒绝。
- `platform_settings.segmented_reply` 仍是默认关闭的体验分段。Telegram / Discord / 企业微信的平台硬限制分段由发送层负责，二者不要混用。
- `log_level`、`log_file_*`：控制台 Loguru sink、根 logger、未单独覆盖的插件 logger，以及轮转文件日志。`log_level` 会同步到终端输出，不只写文件。文件日志走同一脱敏出口：已识别的密钥字段、Bearer、URL 和绝对路径会在写入前替换。Cookie、私聊和自定义 secret 不保证被剥离；分享前仍需人工检查。
- `trace_enable`：Trace 采集总开关；`trace_log_*` 控制独立 Trace 文件。
- `temp_dir_max_size`：`data/temp` 上限（MiB），默认 `1024`；后台定期清理旧文件。
- `timezone`：IANA 时区名称，默认 `Asia/Shanghai`。
- `callback_api_base`：外部服务访问 AstrBot 回调/文件 URL 的公开基地址，不改变监听地址。
- `plugin_set`：配置档可用插件，`["*"]` 为全部，空列表为不使用插件。
- `disable_metrics`：关闭指标采集。内置命令可在 Dashboard 的命令管理页面逐项启用或停用。

## 进程级环境覆盖

少量启动参数可以用环境变量覆盖；它们不是任意配置键到环境变量的通用映射。

| 环境变量                                                                                   | 用途                                                   |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| `ASTRBOT_ROOT`                                                                             | 迁移运行根目录。                                       |
| `DASHBOARD_HOST` / `ASTRBOT_DASHBOARD_HOST`                                                | 覆盖 WebUI 监听地址。                                  |
| `DASHBOARD_PORT` / `ASTRBOT_DASHBOARD_PORT`                                                | 覆盖 WebUI 端口。                                      |
| `DASHBOARD_SSL_ENABLE` / `ASTRBOT_DASHBOARD_SSL_ENABLE`                                    | 覆盖 WebUI TLS 开关。                                  |
| `DASHBOARD_SSL_CERT`、`DASHBOARD_SSL_KEY`、`DASHBOARD_SSL_CA_CERTS` 及对应 `ASTRBOT_` 前缀 | 覆盖 TLS 文件。                                        |
| `ASTRBOT_DASHBOARD_INITIAL_PASSWORD`                                                       | 首次初始化或显式重置时提供初始密码；必须满足密码校验。 |

容器中发布 `6185` 端口并不会覆盖默认 loopback 监听，必须同时设置 host。详见 [Docker 部署](../deploy/astrbot/docker)。

## 修改配置时的检查清单

1. 先确认当前 `DEFAULT_CONFIG` 和 WebUI 元数据中确实存在该字段。
2. 通过 WebUI 修改，或停止 AstrBot 后编辑严格 JSON。
3. 不在 Issue、日志或 Git diff 中暴露凭据、TOTP secret、JWT secret 和访问 token。
4. 重启后查看日志是否出现字段被删除、Provider 加载失败或平台重载失败。
5. 修改监听、代理头、TLS、Computer Use、MCP 或回调地址后，重新做网络边界测试。
6. 为多个配置档分别验证默认 Provider、Persona、插件池和会话绑定；默认配置档的值不会自动代表所有配置档。
