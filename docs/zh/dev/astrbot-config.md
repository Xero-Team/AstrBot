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
| `platform_settings`                               | 所有消息平台共用的收发、限流和分段回复行为。                                                                                                                       |
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
| `admission`                                       | 未列入会话和发送者策略；默认 `unlisted_sessions=allow`、`unlisted_senders=allow`。                                                                                 |
| `inbound_coalesce`                                | 可选的连续私聊 LLM 消息有界合并，默认关闭。                                                                                                                        |
| 其他顶层键                                        | 管理员、T2I、代理、日志、时区、插件、知识库、Trace 和指标等。                                                                                                      |

`provider_sources`、`provider` 和 `platform` 中的对象结构由各类型注册的当前模板决定。不要从旧文档复制对象；在 WebUI 创建后再检查保存结果。模型通过 `provider_source_id` 引用来源，重命名或删除来源时应让 WebUI 同步引用。

未知键（包括旧的 `config_version`）会在加载时删除。配置不做任何就地迁移：按当前 `DEFAULT_CONFIG` 和配置档 schema 构建；破坏性变更时删除 `data/cmd_config.json`（以及 `data/config/abconf_*.json`）后重新配置。

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

没有 `session_enabled` / `llm_enabled` / `tts_enabled` 覆盖时，IM 群聊和私聊默认关闭，Dashboard WebChat 默认开启。会话关闭后只透传 `/bot status` 和 `/bot enable`；要开 LLM 需先打开会话。

未列入会话由顶层 `admission.unlisted_sessions` 控制，默认 `allow`。`deny` 只放行规范会话键上已有覆盖的群或私聊。未列入发送者由 `admission.unlisted_senders` 控制，同样默认 `allow`。`deny` 只放行已有 `blocked` 或 `llm_enabled` 覆盖的 IM 主体。用 `/user block`、`/user unblock`、`/user llm on|off`，或 Dashboard [自定义规则](../use/custom-rules) 的发送者目标写入这些覆盖。WebChat、OneBot `notice` / `request` 以及当前实例上拥有 `provider.manage` 的发送者会跳过。旧的 `id_whitelist`、`enable_id_white_list` 和 `wl_ignore_admin_*` 已删除，升级时不做转换。

## `platform_settings`

常用字段如下：

| 键                                        | 默认值                      | 说明                                                                                                        |
| ----------------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `unique_session`                          | `false`                     | 是否为群内成员拆分独立会话。                                                                                |
| `group_sender_concurrency`                | `false`                     | 实验性。同群不同发送者可并行生成，发送仍按群整轮排队。与 `unique_session` 互斥；会关闭同群流式。            |
| `rate_limit`                              | `60` 秒 / `30` 条 / `stall` | 超限时等待（`stall`）或丢弃（`discard`）。                                                                  |
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

配置档的 AI 执行入口。形状为 `{ "runner_type": "local"|"dify"|"coze"|"dashscope"|"deerflow", "config": {...} }`。聊天模型、Prompt、压缩和步数上限都写在这里，不要再放到 `provider_settings`。

### 模型选择与重试

- `agent_runner.config.model.provider_id`：本地 Agent 的默认聊天模型 ID。
- `agent_runner.config.model.fallback_provider_ids`：主模型失败时按顺序尝试的聊天模型 ID。
- `agent_runner.config.model.request_max_retries`：单个模型请求最大重试次数，默认 `5`；fallback 与单模型重试是不同层次。

### Prompt

- 本地与第三方 Runner：`agent_runner.config.prompt_id`。
- 健康模式：`agent_runner.config.safety_mode`。

选择优先级和权限语义见 [Prompt 提示词设定](../use/prompt)。

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
- `agent_runner.config.misc.max_steps`：本地 Agent 单次运行最大 step，默认 `128`，也适用于当前子代理执行。
- `agent_runner.config.max_steps`：第三方 Runner 的 step 上限，默认 `128`。
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

### Prompt、提示词与会话

- `prompt_pool`：本配置档可选 Prompt，`["*"]` 表示全部。
- `prompt_prefix`：用户提示词模板。占位符语法是无逻辑的 `{{name}}`，不是 Jinja2。允许的键只有 `prompt`。模板含 `{{prompt}}` 时替换为用户输入；不含该占位符时，把前缀拼在用户输入前面。Prompt `system_prompt` 和 workspace `EXTRA_PROMPT.md` 不是模板。
- 内置 LLM 模板使用同一套 `{{name}}` 语法。cron 唤醒允许 `cron_job`；后台任务唤醒允许 `background_task_result`；tool-loop 通知允许 `follow_up_lines`、`tool_names`、`tool_name`、`streak`、`overflow_path`、`read_tool_hint`。未知 `{{name}}` 保持字面量，替换值不会再次扫描。
- `identifier`、`group_name_display`：在本轮最后一条 user 消息后附加用户 ID 或群名的 `<system_reminder>`，并写入会话历史。
- `datetime_system_prompt`：开启后在本轮最后一条 user 消息后附加临时当前时间 `<system_reminder>`，不写入会话历史，也不写入 system prompt。

默认 Prompt ID 在 `agent_runner` 中配置。选择优先级见 [Prompt 提示词设定](../use/prompt)。

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

本地模式直接操作 AstrBot 主机，应仅在可信环境使用。沙箱也不是自动授权边界；仍需限制管理员、Prompt 工具和外部网络。

### 搜索与图片

`web_search`、`websearch_provider` 及各 Provider Key 控制内置网页搜索；`web_search_link` 控制是否附加链接。密钥应在 WebUI 中填写。

`image_compress_enabled` 和 `image_compress_options.max_size/quality` 控制请求准备卡口 `prepare_provider_request` 中的图片处理，主智能体聊天路径、SDK `llm_generate` 与 `tool_loop_agent` 共用该卡口。送给模型的图片在此处转为 JPEG，最长边只缩小、从不放大；每张 JPEG 在 Base64 编码前严格小于 512 KiB（524,288 字节）。超过 64 MiB 的原图会在解码前跳过。动画 GIF/WebP 会按 dhash 抽帧，最多 8 帧。关闭压缩时仍会转 JPEG，但不按配置的最长边缩放，仍可能为满足 512 KiB 上限而缩小。Computer Use 使用 CUA 沙箱（`computer_use_runtime=sandbox` 且 `sandbox.booter=cua`）时，静态图默认不缩放以保持像素坐标 1:1，只有超过 512 KiB 才会继续缩小；未缩放且超过 5 MB 仍会告警，超过 20 MB 准备上限则丢弃。主智能体只把适配器引用物化为本地路径，不在组装附件时预编码 JPEG。`max_quoted_fallback_images` 与 `quoted_message_parser` 限制引用消息和转发消息展开深度，避免无限抓取。对 `quoted_message_parser` 而言，`0` 是有效边界：深度限制会保留根层并停止子层递归，`max_forward_fetch=0` 会禁止递归调用 `get_forward_msg`。负数或无效值会回退为默认值；该设置不会全局禁止引用消息回退路径中的直接 `get_msg` 调用。

## BTW 模型选择

本地 Agent 配置启用 `btw.enabled` 后，`btw.conversation_loop.provider_id` 与 `btw.work_loop.provider_id` 分别选择两个循环的对话模型。已配置的循环模型优先于事件或会话的模型选择；留空则沿用当前选择，包括配置档默认模型。没有显式工作循环标记的消息使用对话循环模型。关闭 BTW 后不应用这两个覆盖项。

所选提供商仍须是已配置的对话模型。不存在或类型不适用的循环提供商将回退到事件或会话的模型选择，并输出警告日志，因此单个失效的设置不会让所有请求失败；它不会静默改用另一个循环的模型。回退只涉及对话模型本身：工作循环的 Computer Use 运行时、只读约束和工具目录仍由各自字段决定，不随模型一起回退。已有模型回退和重试设置继续作用于所选主模型。

### Computer Use 边界

启用 BTW 后，对话循环的 Computer Use 固定为 `none`，并约束其子代理转交与显式传入的工具。宿主机 Shell、Python、文件系统、浏览器、CUA 和沙箱 Skill 生命周期工具不会进入对话循环工具目录。普通 Skill 手册仍可通过 `read_skill` 阅读。

`btw.work_loop.computer_use_runtime` 支持 `inherit`（默认）、`none`、`local` 和 `sandbox`。`inherit` 沿用 `provider_settings.computer_use_runtime`。实际运行时同时作用于工作请求及其子代理转交；`none` 也会排除显式声明的电脑工具。关闭 BTW 后沿用现有 Computer Use 配置。这些设置只选择能力，不授予角色，也不绕过授权、WebChat step-up、路径限制或沙箱检查。

## BTW 循环会话历史与工作交接

启用 BTW 后，两个循环各写各的会话历史。对话循环沿用会话当前的对话；工作循环在同一会话下拥有独立对话（首次提交任务时创建），会话的对话列表和 Dashboard 中可以看到这两份对话。两份历史相互独立，因此后台工作的延迟回复不会覆盖聊天回合，反之亦然。

工作循环不读取自己的历史：每次工作任务都从空历史开始。任务由对话循环显式交接：对话循环的模型调用 `submit_work_task` 工具，把自包含的任务提示词交给工作循环，工具立即返回，任务在后台执行，结果仍从结果装饰和发送阶段回给用户。该工具只在启用了 BTW 与工作循环、并且当前是对话循环时出现，工作循环自身不会获得它。提示词必须完整包含所需信息，因为工作循环看不到聊天内容。

对话循环可以读取工作循环的历史：其请求上下文会附带工作循环最近的完整回合（仅面向模型，不会写入任何一份历史），因此聊天可以引用工作结果。交接过程只还原文本回合，工具调用与其结果不会跨越循环边界。关闭 BTW 后，运行只读取所属对话的历史，不创建工作对话，也不注入任何内容。

## JEV 路由实验（R4）

[#272](https://github.com/Xero-Team/AstrBot/issues/272) 新增默认关闭的实验，仍需在
[#122](https://github.com/Xero-Team/AstrBot/issues/122) 下比较各方案。
先配置 [JEV 分类器](../providers/start.md#jev-system-one-分类器)，然后在
**更多功能 → BTW 双循环** 中开启两个循环并设置：

```json
{
  "btw": {
    "enabled": true,
    "work_loop": { "enabled": true },
    "classifier": {
      "enabled": true,
      "provider_id": "jev_systemone",
      "fallback_provider_id": "",
      "confidence_threshold": 0.85,
      "clarify_on_uncertain": false
    }
  }
}
```

提供商 ID 应与实际配置一致。关闭分类或两个提供商字段都留空时，保留既有的显式提交、
对话模型编写任务后转交的行为。实验仅作用于通过准入与会话 AI 开关检查的本地 Agent
普通文本请求。显式 `/work`、插件提供的请求、附件、引用回复和超过 8,000 字符的消息
保留原有路径。

路由使用 `choice`，选项为 `conversation`、`work`、`clarify`、`unavailable`。
能力来自各循环既有工具目录与冻结的 Skill 快照，遵循 Prompt、插件/MCP/Skill 分配、
运行时与入口权限限制，不维护第二套能力注册表。高置信度的 `work` 还要求存在工作循环
独有的能力；转交复用 WorkLoop 的提交、请求身份、投递和执行授权检查，不授予权限，
也不自行选择或调用编码 CLI。

分类器不存在、失败、超时或低置信度时，使用相同输入调用一次对话兜底模型，要求严格
JSON 判定。兜底 ID 留空时采用对话循环模型及其既有的会话/默认模型回退。分类与兜底
调用各自最多 20 秒，包含重试；兜底不执行工具。兜底模型自报的置信度并非 JEV 的校准
分布统计量，共用数值阈值只是实验设置。

兜底仍不确定或失败时留在对话。`clarify` 也默认留在对话；开启 `clarify_on_uncertain`
后改为直接请求补充任务信息。`unavailable` 提示两个循环都缺少所需能力。凡是留在对话
的判定，本次请求均禁用 `submit_work_task`，包括间接调用。用户仍可发送新的显式
`/work`。工作不会再次分类；重复进入、取消、停止或关闭工作循环不会产生重复转交。

### 第三方数据边界

仅将**当前消息文本、已解析的能力名称及简短摘要**发送给 JEV，必要时也发送给兜底模型。
`state` 不含历史对话、Prompt 系统文本、原始工具 schema、Skill 正文、凭据配置、
本地路径元数据或无关配置。文本在截断前脱敏，移除可识别的凭据、token、URL 与绝对/相对路径。
不要在自由文本中写入秘密：规则无法识别所有任意字符串密钥。路由器不记录原始请求或
远端错误正文；请求内结果只记录判定、模型版本、用量、状态与延迟。

### 复现实验

`tests/fixtures/btw_routing/v1.json` 固定基线
`9bac9db64c7e038652f8af349de5c15a4604a835`、21 条评测用例、成对能力、标签与**提议中的**阈值，
不含调参用例。实现时父 Issue 尚无版本化共享语料；这里提供 R1–R4 可共用的候选语料，
不代表其他方案已在此版本上评测。显式 `/work` 为对照。`contracts.json` 单独保存
脚本化响应，回放只验证路由契约，不代表模型准确率。

```bash
uv run python scripts/evaluate_btw_classifier.py \
  --mode contract --output .tmp/jev-routing-contract.json

# 付费真实评测前设置 TYPESAFE_API_KEY。
uv run python scripts/evaluate_btw_classifier.py \
  --mode live --model jev-1.13.0 --repeats 3 \
  --output .tmp/jev-routing-live.json
```

真实对话兜底还需 `BTW_FALLBACK_API_KEY`，以及指向 OpenAI 兼容服务的
`--fallback-api-base`、`--fallback-model`。可选 `--input-price`/`--output-price`
为 JEV 每百万 token 的美元价格；不含缺失用量、失败调用计费与兜底模型费用。
报告包含模型版本、完整提示词/问题、参数、提交版本、工作区状态、数据集哈希、逐例判定、
错误/遗漏转交、延迟、提供商调用数、token 数与重复运行波动。脚本不执行工具，完成率、
澄清质量与重复副作用结果仍需另行监督式评测；确定性生命周期测试验证执行边界。
回放成功不代表采用 R4，也不代表完成父 Issue 的方案比较。

## BTW 插件工具循环分配

在配置档中启用 BTW 后，可通过 **更多功能 → BTW 双循环 → 插件工具循环分配** 为每个已启用的非系统插件选择对话循环、工作循环或两者。未分配的插件默认仅工作循环可用；选择两者会保存显式覆盖，重新选择工作循环会移除覆盖。关闭 BTW 后保留普通工具可用性。

主 Agent 与其子 Agent handoff 应用相同分配，并继续遵守 Prompt、配置档与授权限制。循环分配不会授予工具执行权限。插件事件处理器和显式命令保留原有执行路径；此设置不会把整个插件转换为后台任务。

## BTW MCP 工具循环分配

启用 BTW 后，可通过 **MCP 服务器循环分配** 为每个已启用服务器选择对话循环、工作循环或两者。服务器的所有工具在主 Agent 和子 Agent handoff 中遵循同一分配。没有覆盖条目的服务器默认仅工作循环可用；选择两者会保存显式覆盖，重新选择工作循环会移除覆盖。关闭 BTW 后保留普通 MCP 工具可用性。

分配按配置档保存，只控制工具可见性，不替代 MCP 读写授权，也不改变现有连接、私网访问和重定向限制。

## BTW Skill 循环可见性

启用 BTW 后，可通过 **Skills 循环分配** 为每个已启用的普通 Skill 选择对话循环、工作循环或两者。普通 Skill 默认在两个循环可见；选择单一循环会保存覆盖，重新选择两者会移除覆盖。工作区 Skill 仅在使用 `local` 运行时的工作循环中可用。关闭 BTW 后保留标准 Skill 选择路径。

循环分配在请求 Skill 快照冻结之前筛选已启用的 Skill，因此提示词、`read_skill` 和 Skill 声明的候选工具使用同一选择结果。Prompt 与插件限制继续生效，包括 Prompt 的空 Skill 列表。循环分配不会授予执行权限：Computer Use 为 `none` 时，`read_skill` 仍可读取允许的 Skill 手册，但 Shell 和 Python 仍不可用。

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

## BTW 工作循环的只读边界与委派

`btw.work_loop.read_only` 默认为 `true`。开启后工作循环的工具目录只保留读取与搜索能力：`astrbot_file_read_tool`、`astrbot_grep_tool`、网页搜索、记忆与知识库工具照常可用；Shell、Python、文件写入与编辑、上传下载、浏览器、CUA，以及 `readOnlyHint` 不为真的 MCP 工具都会被移除，`delegate_coding_task` 是唯一的写入途径。判定按语义而非名单：没有声明 `required_actions` 的工具一律视为可写，插件工具也不例外，因为没有东西为它担保。它只收紧能力：文件读取仍要求 `btw.work_loop.computer_use_runtime` 已授予 local 或 sandbox，角色、路径限制、沙箱、WebChat step-up 与逐项循环分配规则都不变。关闭 `read_only` 恢复原有的写入能力。

`btw.work_loop.coding_agents` 声明可委派的本地 CLI 代理，在 Dashboard 的 **更多功能 → BTW 双循环** 页面配置。每个条目包含 `id`、`type`（`claude_code`、`codex` 或 `custom`）、`command`、`model`、`max_output_chars`、`permission_mode`（Claude Code 权限模式，默认 `acceptEdits`）、`sandbox`（Codex 沙箱，默认 `workspace-write`）、`project_dir`、`extra_args`、`env`、`timeout_seconds` 和 `providers`。`permission_mode` 与 `sandbox` 是交给该 CLI 自己执行的策略，不是操作系统级的隔离：默认值让代理只在任务目录内写入，配置了 `project_dir` 时该目录也会显式加入可写范围；`bypassPermissions` 与 `danger-full-access` 必须显式配置。Claude Code 以 `-p` 非交互方式运行，没有终端可以回答权限询问，而 `acceptEdits` 只自动放行编辑：需要跑 shell 命令（测试、git 等）的任务会一直等到 `timeout_seconds` 超时，这类任务必须显式选择 `bypassPermissions`。委派会启动本地进程并向文件系统写入，因此 `delegate_coding_task` 按 `tool.local_exec` 与 `tool.file_write` 授权：这项工作循环的 Computer Use 运行时必须是 `local`。`sandbox` 下放行等于绕过沙箱——这个进程由本机直接拉起，并不在沙箱里——`inherit` 在请求构建前等同 `none`，`provider_settings.computer_use_runtime` 默认的 `none` 会同时关闭文件读取和委派；WebChat step-up 等表面提升与逐项循环分配规则照常适用。

工作循环通过 `delegate_coding_task` 交办一次写入任务：任务文本写入 `<btw.work_loop.workspace_root>/<会话 ID>-<代理 ID>-<运行 ID>/TASK.md`，`workspace_root` 留空时使用数据目录下的 `btw/workspaces`。每次委派都会新建一个带运行 ID 的目录，因此同一会话的两次委派不会互相覆盖。代理在该目录中运行，完整输出记录到同目录的 `output.log`。任务结束后工作循环读回状态、退出码、产物路径与代理的最终消息；产物是运行前后的差集——git 工作树取 `git status --porcelain` 的变化与运行期间的提交，普通目录取运行开始后写入的文件——在报告里以工作区根目录为基准给出相对路径，不暴露本机数据目录的绝对位置，最多 50 项。代理退出后仍留在其进程组或 Job Object 中的子进程会被一并结束，超时、取消与正常结束都是如此，因此一次委派不会留下还在写盘的遗留进程。

每个代理还可以带一份 `providers` 预设列表与 `active_provider`：Dashboard 已不再编辑它们（代理用的 provider 改由 **更多功能 → 第三方agent配置** 页面切换该 CLI 自己的配置），但配置文件里手写的预设仍按下面的规则生效。预设的 `base_url`、`model` 会写进该 CLI 自己的配置层：Claude Code 用 `--settings` 指向数据目录下的 settings 文件，Codex 用 `--profile astrbot-btw-<代理 ID>` 叠加 `$CODEX_HOME/astrbot-btw-<代理 ID>.config.toml`。每个代理各用一份 Codex 配置层，两个代理同时运行时不会互相覆盖。密钥不落盘，只在拉起子进程时通过环境变量传入——Claude Code 读 `ANTHROPIC_AUTH_TOKEN`，Codex 由配置层的 `env_key` 指向按代理 ID 命名的变量——因此持久化的只有端点与模型。切换 provider 不会改写用户的全局 CLI 配置。预设既无 `base_url` 也无 `api_key` 时视为“官方登录”，不写任何配置层，代理沿用用户自己的登录。

同一个页面还维护 `btw.cli_providers`，那是另一份列表：每个 CLI 一份 provider 列表，由操作者手动切换。点「启用」会把选中的 provider 写进该 CLI 在本机的全局配置——Claude Code 写 `~/.claude/settings.json` 的 `env` 块，Codex 在 `~/.codex/config.toml` 顶部写一段受管区块、密钥存进 `~/.codex/auth.json`。首次写入前原文件会被完整备份一次，「取回」用该备份还原并清掉 AstrBot 写入的密钥。代理没有配置自己的 `providers` 预设时，委派任务读的就是这个文件：在这里切换 provider，任务与你手动启动的会话用的是同一份配置。切换改写了不属于 AstrBot 的文件，因此按 `coding_cli.config.write` 授权并要求 step-up。

任务完成后，`btw.work_loop.report_via_conversation`（默认 `true`）让工作循环把结果交给对话循环合成一条汇报：代理的回答在前，随后是完成状态与产物路径。流式结果的中间分片不受影响，只有最终结果带上汇报，且同一次运行只追加一次。关闭此项后结果由工作循环直接投递。

## BTW 编码 CLI 的全局配置切换

`btw.cli_providers` 是 **更多功能 → CLI 全局配置**（`/cli-config`）编辑的 provider 列表。它是普通配置：条目随配置档保存，`api_key` 也存在配置档里，与其他 provider 凭据一样。每个条目包含 `id`、`name`、可选的 `cli`（`claude_code` 或 `codex`；留空表示两个 CLI 都可用，界面上新增的条目总会带上所在分区）、`base_url`、`model`、`note` 和 `api_key`；`id` 在整份列表内唯一。

委派任务不受这里的切换影响：一次运行加载自己那份配置层，不读这些文件。这里切换的是该 CLI 在本机的配置，也就是你手动开会话时用的配置。

这是 AstrBot 唯一一处写进自己数据目录之外的地方。目标文件在第一次写入前备份一次（`.astrbot-backup`，由“收回”还原），写入是原子的（`mkstemp` + `fsync` + `os.replace` + 目录 fsync），持有凭据的文件权限为 `0o600`，响应只报告是否存有密钥、从不返回其值。Claude Code 走 `~/.claude/settings.json` 的 `env`（`ANTHROPIC_BASE_URL`、`ANTHROPIC_MODEL`、`ANTHROPIC_AUTH_TOKEN`），逐键合并、其余内容原样保留。Codex 的 TOML 标准库能读不能写，改写一个解析不了的文件会丢掉用户的注释，因此 AstrBot 的键写进文件顶部一段注释分隔的区块（TOML 要求顶层键排在所有表之前），其余部分逐字节保留，凭据写进 `auth.json`。

两类文件会被拒绝而不是被覆盖：存在但读不成 JSON 对象的 `settings.json`（例如带注释的 JSONC 或数组），以及有起始标记却没有结束标记的 Codex 区块——后者的边界无从得知，猜错会让文件每切换一次就多出一段。状态路由要求 `platform.read`；切换与收回要求高风险动作 `coding_cli.config.write`，因此需要 step-up。

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
- `http_proxy` / `no_proxy`：全局出站代理和直连名单。它们不再写入进程级 `HTTP_PROXY`。Docker 部署时请填写容器能访问到的地址，见 [Docker 部署](/deploy/astrbot/docker#在-docker-中配置-http-代理)。
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
6. 为多个配置档分别验证默认 Provider、Prompt、插件池和会话绑定；默认配置档的值不会自动代表所有配置档。
