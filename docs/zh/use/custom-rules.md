# 自定义规则

自定义规则按统一消息来源（UMO）或发送者覆盖配置文件，用来处理少量特例。不要为了一个群的提示词或关 TTS 再拆一份配置文件。

UMO 唯一指定某个平台下的一个会话。发送者覆盖用完整主体 ID `im:{平台实例}:{机器人账号}:{发送者 ID}`。两者都可用 `/session info` 查看。配置文件本身见 [配置文件](./config-profiles)。

入口：WebUI **自定义规则**。页面顶部选择 **会话** 或 **发送者**。页面帮助图标指向本页。

## 和配置文件怎么选

| 需求                                       | 用什么                                   |
| ------------------------------------------ | ---------------------------------------- |
| 整个平台或一类群共用模型、唤醒策略、插件集 | 新建或绑定 [配置文件](./config-profiles) |
| 某一个群关掉 LLM、换提示词、换知识库       | 自定义规则（会话）                       |
| 共享群里只禁某个人，或给某人打开 LLM       | 自定义规则（发送者）或 `/user`           |
| 临时停掉当前会话                           | `/bot disable` 或本页的会话启停          |

规则高于配置文件。规则里关掉 LLM 后，配置文件再开也没有用。没有规则时，IM 群聊和私聊的会话、LLM、TTS 默认关闭；Dashboard WebChat 仍默认开启。

## 规则类型

会话规则绑在一个 UMO 上，可以同时包含多类覆盖。发送者规则绑在 `im:` 主体 ID 上，只含服务覆盖里的 `blocked` / `llm_enabled`。

### 服务规则（`session_service_config`）

- 是否处理该会话的消息。关掉约等于把这个 UMO 拉黑。
- 是否对该会话启用 LLM。关掉后不走 AI，指令仍可能执行。
- 是否对该会话启用 TTS。
- 是否完全禁用该会话的所有功能（`session_blocked`）。完全禁用后只放行 `/bot status` 和 `/session unblock`。
- 强制提示词。优先级高于对话选择和配置文件默认提示词，见 [Prompt](./prompt#哪个-prompt-会生效)。
- 展示别名。与 `/session name` 写入同一份 `user_alias`，不是单独的 `custom_name` 字段。

聊天里的 `/bot enable`、`/bot disable`、`/tts enable`、`/tts disable`、`/session block`、`/session unblock` 仍按 UMO 写服务规则。IM 里的 `/llm enable` 和 `/llm disable` 写的是规范会话键，所以隔离会话开启时会关掉整个群的 LLM。Dashboard 自定义规则页仍按 UMO 保存提示词和 TTS，但会把 `llm_enabled` / `session_enabled` / `session_blocked` 双写到规范会话键。`/bot status` 可以查看当前会话的整体开关、LLM、TTS 和完全禁用状态。这些指令需要 `session.manage` 或 `session.block`，见 [内置指令](./command)。

`unlisted_sessions=deny` 时，准入阶段看规范会话键上的覆盖。IM `/llm` 和本页 Dashboard 规则都会列入该键。会话是否启用、是否完全禁用仍由后面的会话状态阶段按 UMO 处理。

### 发送者覆盖（sender）

发送者覆盖写在 `scope=sender`、`scope_id=Subject.im.id`（`im:{平台实例}:{机器人账号}:{发送者 ID}`）上，只认 `blocked` 和 `llm_enabled`。它对这个机器人实例上的所有会话生效，包括未开启隔离会话的共享群，不是 `UMO×UID`。提示词、TTS、知识库、Provider、插件禁用仍只属于会话规则。

本页 **发送者** 目标和 `/user block`、`/user unblock`、`/user llm on|off` 读写同一行 preference。Dashboard 要填完整 `im:` 主体 ID；聊天里的 `/user` 还可以用当前会话铸造裸发送者 ID。见 [内置指令](./command)。保存后立即生效，不必重启。删除该行后，该发送者不再被列入。

未写入的 `llm_enabled` 跟随会话。Dashboard 发送者编辑器提供“跟随会话 / 启用 / 禁用”三态，只写入你显式选择的值，并且只有勾选“拉黑”时才会写入 `blocked`，因此直接保存未改动的规则不会改变准入结果。把已写入的值改回“跟随会话”会删除该字段；删除整条规则会移除整行。

### 插件规则（`session_plugin_config`）

为这个 UMO 单独禁用插件。未列入禁用列表的插件保持启用状态。三层同时存在时：

1. 插件页把插件全局禁用：这里勾上也不会加载。
2. 配置文件 `plugin_set`：限制该文件可用插件。
3. 本规则：再按会话禁用插件。

详见 [插件](./plugin)。

### 知识库规则（`kb_config`）

- `kb_ids`：覆盖配置文件的 `knowledge_base.names`。空列表表示这个会话不使用知识库。
- `top_k`、是否重排序：只影响这个会话的检索。

详见 [知识库](./knowledge-base#接到会话)。

### Provider 覆盖

可以为该 UMO 指定聊天模型、STT、TTS。未指定时跟随配置文件。语音总开关仍受服务规则和配置文件影响，见 [语音 STT / TTS](./speech)。

## 操作步骤

1. 打开 **自定义规则**，选择 **会话** 或 **发送者**，点添加规则。
2. 会话：选择已出现过的 UMO，或按平台 / 类型 / 会话填写。发送者：粘贴完整 `im:` 主体 ID。
3. 只改需要覆盖的项。发送者行只有拉黑和 LLM。
4. 保存后立即生效，通常不必重启。
5. 删除规则即回到配置文件或未列入行为。

会话页支持按 UMO 搜索、批量删除，以及给规则分组。发送者页支持按主体 ID 搜索和删除，没有分组或批量改 Provider。

## 常见误配

1. 规则关掉了会话或 LLM，群里表现为「机器人不理人」，但 `llm_access` 看起来是对的。先看 `/bot status`。
2. 用规则指定了提示词，却还在配置文件里改默认提示词，当前群不会跟着变。
3. `kb_ids` 填了已删除的知识库 ID，检索会被跳过。
4. 为每个群都建一份配置文件，规则表却是空的。
5. 想禁某个人却去改会话规则或旧白名单。按人一律走发送者覆盖；不要把 `im:` ID 填进 UMO。
