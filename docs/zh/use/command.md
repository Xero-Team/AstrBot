# 内置指令

AstrBot 的指令通过插件机制注册。内置指令统一采用“单数名词根命令 + 完整动词子命令 + 长选项”的 CLI 命名方式，例如 `/plugin list`、`/conversation create` 和 `/provider set llm 1`。旧短名（`/plugin ls`、`/op`、`/reset`、`/flow on` 等）不是别名，不会匹配。`/help` 只列出当前启用的声明名，或 Dashboard 手动重命名后的名字。

使用 `/help` 查看当前已经启用的根指令及其一层子命令；使用 `/help --image` 或 `/help -i` 请求图片版帮助。如果修改了唤醒前缀，所有示例中的 `/` 也要替换为实际前缀。

## Orbit 指令参数语法

AstrBot 使用 **Orbit Command Syntax** 解析已注册指令的参数。Orbit 不是 shell，也不会执行 shell。只有消息命中完整指令名、指令组或别名后才会严格解析参数；完全未知的根指令仍可进入普通插件过滤器或 LLM。

Orbit 支持确定性的 POSIX quoting 和 escaping 子集：

- 只有 ASCII 空格和 Tab 分隔参数。
- 单引号内所有字符都是字面值。
- 双引号内的反斜杠只转义 `$`、反引号、反斜杠、双引号和换行；其他反斜杠会原样保留。
- 未引用的反斜杠转义下一个字符；反斜杠加换行会执行 line continuation。
- 相邻的引用和未引用片段属于同一个参数，例如 `ab"cd"'ef'` 得到 `abcdef`。
- `""` 和 `''` 都会产生一个空参数。Unicode 原样保留，指令匹配区分大小写。

Orbit 不执行变量、命令、算术或波浪号展开，也不执行 glob、重定向、管道、列表或子 shell。任何未转义且不在单引号内的 `$` 或反引号，以及未引用的词首 `~`、`*`、`?`、`[`、`|`、`&`、`;`、`<`、`>`、`(`、`)`、词首 `#` 和换行都会返回结构化语法错误。

需要把这些字符作为普通数据传入时，请引用或转义：

```text
/session name '$HOME'
/session name "a|b"
/session name \*.txt
/session name "C:\Users\bot"
/session name '^user#[0-9]+$'
/plugin install 'https://example.com?a=1&b=2#readme'
```

已声明的 option 可以位于位置参数前后，支持 `--name=value`。`--` 会终止 option 解析，例如 `/session name -- -x` 会把 `-x` 当作普通参数。`-1` 等负数可以直接用于数值位置参数。

## 指令与 LLM 路由

指令由配置档的 `command_prefixes`（默认 `["/"]`）标记，并在已启用的指令 catalog 中匹配。路由总是先匹配指令，再判断 LLM 访问：命中指令时只执行指令，裸指令组显示帮助，未知子指令返回 Orbit 诊断，不会被当作 LLM 提示词。非指令消息遵循当前配置档的 `llm_access` 策略；其中的前缀是用户实际输入的完整字符串，不会与 `command_prefixes` 自动拼接。群聊何时会进 LLM 见 [群聊何时会理我](./group-wake)。

已启用的指令路径、别名、子路径和非空 LLM 前缀根共享同一作用域命名空间。发生冲突时，路径会被拒绝或从运行时 catalog 排除，直到 Dashboard 重命名只剩一个所有者，或指令更新 API 记录接管。Dashboard 会高亮冲突并提供重命名，没有接管按钮。内置 LLM 状态指令是 `/llm status`、`/llm enable` 和 `/llm disable`；`/chat` 不是它们的兼容别名。

## 指令列表

### 帮助

- `/help`：显示当前启用的根指令、一层子命令和版本信息。
- `/help --image` 或 `/help -i`：生成图片版帮助。

### 机器人状态

- `/bot status [this|UMO]`：显示目标会话的版本、整体开关、LLM 开关和 TTS 开关。省略参数或使用 `this` 表示当前会话；指定 UMO 时需要 `instance_operator` 及以上权限。
- `/bot enable [this|UMO]`：启用目标会话。省略参数或使用 `this` 表示当前会话；指定 UMO 时需要 `instance_operator` 及以上权限。
- `/bot disable [this|UMO]`：停用目标会话。省略参数或使用 `this` 表示当前会话；指定 UMO 时需要 `instance_operator` 及以上权限。
- `/bot leave`：提示退群确认。需要 `session.manage`，且只能在群聊中使用。
- `/bot leave --confirm` 或 `/bot leave -c`：确认后退出当前群。当前平台未声明 `leave_group` 时会拒绝。

`enable` 和 `disable` 都是幂等操作，写入已有的 `session_enabled`，作用范围是目标 UMO（与 `/llm` 相同）。会话关闭后，流水线会停止普通事件，但仍放行 `/bot status` 和 `/bot enable`，以便从聊天重新打开。`/bot status` 还会显示完全禁用状态。`/session block [this|UMO]` 和 `/session unblock [this|UMO]` 由 `instance_operator` 及以上权限使用，完全禁用目标会话的所有功能；完全禁用后只放行 `/bot status` 和 `/session unblock`。裸 `/bot` 只显示子指令树。

### 会话信息

- `/session info [this|UMO]`：显示 UMO、用户 ID、授权主体（`im:{platform}:{bot}:{sender}`）、平台 ID、消息类型和会话 ID。省略参数或使用 `this` 表示当前会话；指定 UMO 时需要 `instance_operator` 及以上权限，并显示目标会话的自动名称和别名。
- `/session name [--target UMO]`：显示自动名称和已保存别名，需要 `session.manage`。指定 `--target` 时需要 `instance_operator` 及以上权限。
- `/session name [--target UMO] <名称>`：设置展示别名，需要 `session.manage`。名称由 `GreedyStr` 接收，可以包含空格。
- `/session name [--target UMO] --clear`：清除展示别名。

唤醒阶段在 `is_wake` 确定后会把自动名写入存储；手动别名优先，自动 upsert 不覆盖 `user_alias`。

使用 `/session info` 得到的用户 ID 可以通过 `/admin grant` 授予当前会话的 `session_admin`。这不是全局 operator。群聊开启 `unique_session` 时，该指令也会显示群 ID；群准入和 `/llm disable` 用的是这个群会话，不是改写后的个人 UMO。

### 跨会话监听与发送

- `/session watch [监听会话|this] <被监听会话> [秒数]`：把被监听会话后续收到的消息转发到监听会话，需要 `session.watch`。监听会话可省略或写 `this`，表示当前会话。时长 1–864000 秒（最多 10 天），默认 43200 秒（12 小时），按墙钟计算。到期后会在监听会话发送结束通知。
- `/session watches [监听会话|this]`：查看你创建的监听和剩余时间。省略参数或写 `this` 表示当前会话作为监听端。
- `/session unwatch [监听会话|this] <被监听会话>`：停止你创建的指定监听。监听会话可省略或写 `this`。
- `/session connect <UMO>`：把当前会话无期限连接到目标会话，需要 `session.watch`。目标会话的新消息会一直转发，直到 `/session disconnect` 或 `/session unlink`。每个主体在每个监听会话只能有一条连接，再次连接会替换目标。省略 UMO 可查看当前连接。指令不接受秒数。
- `/session disconnect`：断开当前会话的无期限连接，需要 `session.read`。
- `/session pair <UMO>`：在当前会话与目标之间建立两条无期限的有向边，需要 `session.watch`。两端适配器都必须已加载且可主动发送。只转发真人消息，跳过 Bot 自己的发言和回显，避免回环。对岸看到的是**目标侧 Bot 账号**在说话，并带上与 watch 相同的本地化来源头（发送者名和源平台）。不伪造源发送者的平台身份，也不把消息灌进目标入站管道。不绑定 `/send`；省略 UMO 的 `/send` 仍只走 `connect`。指令不接受秒数。每主体最多 8 对（16 条 `pair` 边），与 16 条 connect 并列，不挤占 watch 配额。同一对端点再次 `pair` 会保留原来的 `pair_id` 和两条 `rule_id`。对已有 watch/connect 建 pair 会替换那两条方向上属于该主体的旧边。已写入的无头 pair 保持原样，需要重新 `unpair` 再 `pair` 才会带上来源头。
- `/session unpair [UMO]`：删除共享 `pair_id` 的两条边，需要 `session.read`。恰好一对且当前会话是其中一端时可省略 UMO；0 对提示没有；多于一对必须带 UMO。
- `/session links`：列出可见的监听、连接和 pair，包含 `rule_id`、类型和剩余时间或无期限；pair 额外显示 `pair_id`。权限与 `watches` 相同（`session.read`）。创建者只看到自己的规则；当前会话配置上的 `instance_operator` 额外看到两端任一配置 id 属于当前会话配置的规则；`operator` / `root` 看到全部。
- `/session unlink <rule_id>`：按 12 位小写十六进制 id 撤销一条监听或连接。创建者可撤自己的规则（角色被撤后仍可）。本配置 `instance_operator` 可撤两端任一配置属于当前会话配置的规则；`operator` / `root` 可撤全部。目标是 `kind=pair` 时拒绝并提示使用 `unpair`，两条边都还在。
- `/session filter <rule_id>`：查看一条有向边的 match/except 过滤。权限与 `links` 相同（`session.read` 加运营附加范围）。
- `/session filter <rule_id> match|except subject|role|text <值>`：向该边追加一条过滤。同一维度为 OR，维度之间为 AND，命中 except 则丢弃。`text` 把行内剩余内容当作 Python `re.search` 模式（最长 256 字符，默认 Unicode 且大小写敏感，忽略大小写用 `(?i)`）。非法模式在保存时拒绝。`role` 是发送者在**源会话**上的 AstrBot 授权角色（`guest` / `member` / `session_admin` / `session_owner` / `instance_operator` / `operator` / `root`），不是平台群身份。查不到当 `guest`。每一维最多 16 条。创建者在撤权后仍可改自己的边，运营附加范围与 `unlink` 相同。pair 的两条边可分别过滤，拆对仍走 `unpair`。
- `/session filter <rule_id> clear [match|except|all]`：清空一侧或两侧。省略范围等于 `all`。`clear` 清的是整个 match 或 except 侧，不能单删一条；要改就先 `clear` 再加。
- `/send <UMO> [内容]`：借助目标平台的 Bot 账号发送文字和同一条消息中的附件，需要 `session.send`。可以只附图片而不填写正文；不会占用 `reply` 指令。
- `/send [内容]`：在 `/session connect` 之后，不写 UMO 也会发往已连接的目标会话。可以只附图片。`pair` 不会成为 `/send` 的默认目标。

监听、连接、配对和发送要求当前身份拥有同一配置下的 `instance_operator` 权限。群管理员、私聊会话所有者身份不能替代它。监听内容对接收会话的所有成员可见；仅转发开始监听之后收到的消息，不读取历史。空的 match 与 except 会转发全部真人消息。`watch` / `connect` / `pair` 创建指令不解析过滤 flag，事后用 `/session filter` 设置。主体过滤用 `Subject.im` 重建：平台实例取源路由 `platform_id`，`bot_account_id` 取源适配器 `self_id`，`sender_id` 取 `SenderSnapshot.id`。正文只拼接 `PortablePart` 文本，忽略媒体和 `NativeContent`；纯媒体在写了 `match.text` 时不转，只写 `except.text` 则放行。规则写入 SQLite，进程重启后未过期的监听、全部连接和全部 pair 仍在；过期监听会在启动或到期时清除并通知监听端。每人最多 16 条监听、16 条连接和 8 对 pair。每次转发都会重新检查权限，撤权后停止投递。对同一对会话再次 `/session watch` 会保留 `rule_id` 并重置时长。同一方向的 watch 与 connect 会互相替换。任一条目标方向已是 pair 时，`watch` / `connect` 会拒绝并提示先 `unpair`，不会拆成半对。

正文保留消息链中的图文先后顺序；不能混排的目标拆成多条消息。跨平台提及转成文字，引用优先通过已接受消息的 ID 映射还原；映射不存在时附引用摘要。无法解析的附件和不支持的原生内容会保留文字占位。平台自己的卡片、私有语法和小程序不能保证在别的平台重现。源消息是已展开的合并转发、且目标声明 `forward` 时，对岸看到合并转发卡片：节点作者是原节点的 `uin` / `name`，发言账号仍是目标 Bot。目标不支持时仍为带作者标签的线性转录。

`send` 的参数仍遵循上文 Orbit 语法；正文从消息链中移除指令头后提取，保留原文和附件位置。返回结果区分平台接受、部分接受、拒绝和状态未知；“接受”不表示收件人已读。部分接受或未知时，请先检查目标会话再决定是否重发。

LINE 等需要公网媒体 URL 的目标要求配置可访问的 HTTPS `callback_api_base`。转发媒体使用有期限的文件令牌副本，不能把源 Bot 的私有文件 ID 直接交给另一平台。微信公众号当前不能作为主动发送目标；其他平台还可能受账号模式、推送 Webhook、会话状态或服务端权限限制。

本阶段没有 Dashboard 管理面。创建、查看、停止监听以及跨会话发送只能通过上述 IM 指令完成。指令管理页可以启用或禁用这些指令，但不能列出或操作监听。WebChat 里也可以发送这些指令，效果与其他 IM 会话相同。

### 对话

- `/conversation create`：创建并切换到新对话。
- `/conversation reset`：清空当前对话上下文，同时清理对应的第三方 Agent Runner 会话状态和该会话的[群聊上下文感知](./group-chat-context)内存缓存。
- `/conversation stats`：显示当前对话的输入、缓存输入和输出 Token 统计。
- `/conversation history [--page N|-p N]`：显示当前对话历史。
- `/conversation list [--page N|-p N]`：列出对话。
- `/conversation switch <序号>`：切换到列表中的对话。
- `/conversation rename <新标题>`：重命名当前对话，标题可以包含空格。
- `/conversation delete`：删除当前对话。
- `/conversation create-for <会话 ID>`：为指定群会话创建新对话，需要 `session.assign` 和 `session.manage`。

`reset`、`delete`、`create`、`switch`、`rename` 始终声明 `session.manage`。私聊对端是当前会话的 `session_owner`，因此可以直接 `/conversation reset` 等管理指令；群聊仍需要 `session_admin` 及以上。Dashboard 中的指令权限配置优先于默认行为。

### 运行任务

- `/work <任务内容>`：将后面的文本显式提交给 BTW 工作循环，不需要 `/chat` 前缀或自动分类。要求 `session.read`，并在当前配置中启用 `btw.enabled` 和 `btw.work_loop.enabled`。指令标识为 `builtin_commands:work`；仍遵循指令引号规则。
- `/work` 或 `/work status`：查看当前配置与会话中最新任务的内容及状态：排队中、执行中、已完成、已失败、已取消或投递未确认。`投递未确认` 表示任务本身已结束，但平台没有确认接收其结果。仅当参数全部为 `status` 时查询，忽略大小写；`/work status 重构` 会提交任务。要求 `session.read`。状态保存在内存中，重启或配置重载、移除后清空；终态任务按 `btw.work_session.max_age_seconds` 过期，默认 3600 秒。
- `/task stop`：请求停止当前会话中正在运行的 Agent 或第三方 Agent Runner 任务，不删除历史。本地运行会停止消费执行器并记为已取消；这里只结束本地等待，第三方服务已经接受的任务不会被远端撤销。

### Provider 与模型

- `/provider list`：列出 LLM、TTS 和 STT Provider，以及当前选中项和可达性状态。
- `/provider set llm <序号>`：切换 LLM Provider。
- `/provider set tts <序号>`：切换 TTS Provider。
- `/provider set stt <序号>`：切换 STT Provider。
- `/model list`：列出当前 LLM Provider 可用模型。
- `/model set <名称或序号>`：切换模型；名称也可以解析到其他已配置 Provider。

这些指令需要 `provider.use`；跨会话指定时还需要 `session.assign`。

### 会话变量

- `/variable set <键> <值>`：设置 Agent Runner 输入变量。
- `/variable unset <键>`：删除输入变量。

### LLM 聊天状态

- `/llm status`：显示当前会话是否启用 LLM 聊天。
- `/llm enable`：启用当前会话的 LLM 聊天。
- `/llm disable`：停用当前会话的 LLM 聊天。

这些指令需要 `session.manage`。`enable` 和 `disable` 都是幂等操作。`/llm` 只控制是否启用 LLM，与流式模式无关。IM 里写入的是规范会话键，因此隔离会话开启时会关掉整个群的 LLM。Dashboard 自定义规则会把 LLM 开关双写到同一把规范键。

### 发送者准入

- `/user block <sender_id>`：拉黑该发送者。对本机器人实例上的所有会话生效。
- `/user unblock <sender_id>`：解除拉黑。
- `/user llm on <sender_id>`：为该发送者打开内置 LLM（可覆盖会话级关闭）。
- `/user llm off <sender_id>`：为该发送者关闭内置 LLM；匹配到的指令仍会执行。

`sender_id` 必填。用 `/session info` 里的 UID（按当前机器人铸成 `im:{平台}:{机器人}:{发送者}`），或直接粘贴完整授权主体 ID。省略或空参数只显示用法，不会操作自己。多余参数是绑定错误，不会算进 ID。这些指令需要 `session.manage`。被拉黑的发送者在准入阶段被丢掉，只放行 `/user unblock` 和 `/bot status`。会话被完全禁用时，发送者 `llm_enabled=true` 不能救活事件。

### TTS 状态

- `/tts status`：显示当前会话是否启用 TTS。
- `/tts enable`：启用当前会话的 TTS。
- `/tts disable`：停用当前会话的 TTS。

这些指令需要 `session.manage`。`enable` 和 `disable` 都是幂等操作。`/bot status` 可以同时查看会话、LLM 和 TTS 开关。

### 会话流式输出

- `/flow enable`：当前会话强制流式。
- `/flow disable`：当前会话强制非流式。
- `/flow unset`：删除会话覆盖，重新跟随全局 `provider_settings.streaming_response`。
- `/flow status`：查看覆盖值和当前有效模式。

这些指令需要 `session.manage`。没有无参数切换，避免跨平台解析歧义。

### 会话管理员

- `/admin list`：列出当前会话可见的角色绑定。
- `/admin grant <用户 ID>`：授予当前会话的 `session_admin`，不是全局 operator。
- `/admin revoke <用户 ID>`：撤销当前会话的 `session_admin`。

三个子指令都需要 `identity.manage`。当前会话的 owner 只能管理本会话的 `session_admin` / `member`，不能委派 owner。角色说明见 [授权管理](./authorization)。

### Persona

- `/persona status`：显示默认 Persona 和当前对话实际使用的 Persona。
- `/persona list`：列出 Persona。
- `/persona show <persona_id>`：显示 Persona 的系统提示词。
- `/persona set <persona_id>`：为当前对话选择 Persona。
- `/persona unset`：让当前对话显式不使用 Persona。

Persona 子指令需要 `agent.manage`。仅输入 `/persona` 会显示子指令树。

### 插件

- `/plugin list`：列出已加载插件。
- `/plugin show <插件名>`：显示插件版本、作者和已注册指令。
- `/plugin enable <插件名>`：启用插件，需要 `extension.manage`。
- `/plugin disable <插件名>`：停用插件，需要 `extension.manage`。
- `/plugin install <仓库 URL>`：安装插件，需要 `extension.plugin_install` 和 Dashboard step-up。

插件加载、卸载、重载或启禁后，AstrBot 会立即重建指令 catalog，并刷新已启用的 Telegram/Discord 原生命令入口。
