# 接入 Telegram

## 支持的基本消息类型

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注                   |
| -------- | ------------ | ------------ | ---------------------- |
| 文本     | 是           | 是           |                        |
| 图片     | 是           | 是           |                        |
| 动画     | 是           | 是           | GIF/动画媒体单独发送。 |
| 语音     | 是           | 是           |                        |
| 视频     | 是           | 是           |                        |
| 文件     | 是           | 是           |                        |

主动消息推送：支持。

## 更新接入范围

每次启动或重建轮询客户端时，AstrBot 都显式订阅 `message`、`channel_post` 和 `business_message`，不继承 Telegram 服务端残留的订阅选择。

| Telegram Update 字段                                               | 处理方式                                                                                                                                     |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `message`                                                          | 接入私聊、群组及主题消息，复用上表的内容类型和相册处理。                                                                                     |
| `channel_post`                                                     | 作为群组消息接入，保留频道及主题路由。以 `sender_chat` 作为发送者，避免把匿名发送的兼容用户当成真实用户。是否触发 LLM 仍由群聊访问规则决定。 |
| `business_message`                                                 | 接入带有 `business_connection_id` 的客户入站私聊；忽略账户所有者发出的消息、`sender_business_bot` 标记的机器人外发消息及不完整的路由。       |
| `edited_message`、`edited_channel_post`、`edited_business_message` | 不订阅、不触发新消息事件，也不修改已保存的上下文。需要重新执行时请发送新消息。                                                               |
| `guest_message`                                                    | 不接入。Guest Bot 消息需要专用的 `answerGuestQuery` / `InlineQueryResult` 回复协议，不能通过普通聊天发送接口回复。                           |
| 其他更新                                                           | 不订阅、不转换为聊天消息，包括按钮回调、成员变更、反应、投票、支付、Business 连接变更及删除通知、boost 和 managed bot 更新。                 |

即使旧订阅中尚未确认的更新在切换后到达，处理器也只接收上述三类消息。每个适配器保留最近 4096 个已接纳的 Update ID，重复投递不会在缓存有效期内再次执行指令或 agent；缓存随轮询客户端重建保留，但不跨进程重启持久化。编辑更新始终忽略。

### Business 会话与回复

Business 聊天与相同 chat ID 的普通 Bot 聊天相互独立。AstrBot 使用 `business:<经过百分号编码的连接 ID>:<chat_id>` 作为 Business 路由，有主题时追加 `#<message_thread_id>`。请保存完整会话目标用于主动发送；连接、聊天和主题信息都会恢复，相册也按该路由隔离。

文本、媒体、输入状态和流式编辑均携带原始 `business_connection_id`。Business 私聊使用发送后编辑的流式方式，因为 `sendMessageDraft` 不支持 Business 连接；同样不执行不支持连接身份的消息反应操作。回复和主动发送仍受 Telegram 的连接权限及最近 24 小时入站消息要求约束。

## 1. 创建 Telegram Bot

首先，打开 Telegram，搜索 `BotFather`，点击 `Start`，然后发送 `/newbot`，按照提示输入你的机器人名字和用户名。

创建成功后，`BotFather` 会给你一个 `token`，请妥善保存。

如果需要在群聊中使用，需要关闭Bot的 [Privacy mode](https://core.telegram.org/bots/features#privacy-mode)，对 `BotFather` 发送 `/setprivacy` 命令，然后选择bot， 再选择 `Disable`。

## 2. 配置 AstrBot

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `telegram`

弹出的配置项填写：

- ID(id)：随意填写，用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- Bot Token: 你的 Telegram 机器人的 `token`。

请确保你的网络环境可以访问 Telegram。你可能需要使用 `配置页->其他配置->HTTP 代理` 来设置代理。

## 原生指令菜单

启用 Telegram 指令注册后，AstrBot 会将当前已启用的内置和扩展插件根指令、根指令组及根别名同步到 Telegram 的原生指令菜单；不符合 Telegram 名称约束的入口会跳过。Telegram 菜单最多接受 100 项，因此 AstrBot 先保留主指令，再分别按名称排序别名，并记录被省略的本地指令数量。Telegram 菜单本身不支持子指令或具名参数，因此选择 `/persona`、`/provider`、`/plugin` 等指令组后，具体子指令和参数仍由 Orbit Command Syntax 解析。

插件加载、卸载、重载、启禁，以及 Dashboard 中的指令启禁、重命名或别名修改都会立即请求刷新菜单。非空菜单会直接提交替换，写入失败时不会先清除现有菜单；当期望指令集合为空时才会清除 Telegram 上残留的旧菜单。自动刷新定时任务会始终对账当前菜单，在网络失败或 Telegram 菜单被外部修改后进行恢复。

## 提及处理

正文和媒体说明会保留表情、空白以及对其他用户的提及。对当前机器人的提及会转换为提及组件，并从纯文本中移除，重复提及也会正确处理。无效的实体范围会被忽略，不会删除原文。提及本身不会开启群聊 LLM 回复；是否回复仍由已配置的群聊访问、回复机器人和续聊规则决定。 Telegram `text_mention` 会保留数值用户 ID 和 UTF-16 偏移；语音和动画说明及媒体元数据也会保留。出站数值提及使用 `tg://user?id=` 链接；Telegram 没有通知全体成员的 Bot API 标记，因此投递时会忽略 `MentionAll`。

## 媒体相册

Telegram 媒体相册的收集独立于原生指令菜单。关闭指令注册或定时刷新不会关闭相册投递。AstrBot 会在每条相册消息后短暂等待其余消息，但即使持续收到新消息，也会在配置的最长收集截止时间到达后开始处理。

为保持适配器响应性，每个实例最多同时收集或处理 128 个相册，每个相册最多保留 10 条不同消息。超过限制的新相册或额外消息会被丢弃。相册处理最多持续 60 秒；Telegram 适配器重启或停止时，未完成的相册同样会被丢弃。这些是内部安全限制，不是 Dashboard 配置项。

发送由 2–10 张兼容图片组成的消息链时，AstrBot 使用有序媒体相册，并将说明放在第一项。GIF、动画、混合消息链或相册请求失败时，会按顺序逐项发送。location、contact、poll、dice、paid media 和 live photo 在形成跨平台消费者契约前保持不支持。

## 流式输出

Telegram 平台支持流式输出。需要在「AI 配置」->「其他配置」中开启「流式输出」开关。

### 私聊流式输出

在普通 Bot 私聊中，AstrBot 使用 Telegram Bot API v9.3 新增的 `sendMessageDraft` API 实现流式输出。这种方式会在私聊界面展示一个「正在输入」的草稿预览动画，体验更接近「打字机」效果，且避免了传统方案的消息闪烁、推送通知干扰和 API 编辑频率限制等问题。

### 群聊流式输出

在群聊中，由于 `sendMessageDraft` API 仅支持私聊，AstrBot 会自动回退到传统的 `send_message` + `edit_message_text` 方案。超过 Telegram 单条 4096 字符限制的回答会按顺序完成并发送为多条消息。若分段提交失败，AstrBot 会停止发送，并在投递回执中记录已接受的前缀、提交失败的片段以及缓冲区中尚未发送的文本，不会自动重试这些文本。若可选的 Markdown 格式化步骤失败，已接受的纯文本分段会保留，流式发送继续进行。

所有 Telegram 出站请求由适配器共享的限流器调度：`telegram_delivery_global_interval` 控制机器人全局间隔，`telegram_delivery_chat_interval` 控制单聊天间隔。草稿、编辑、输入状态和反应遇到 `RetryAfter` 时，会在 `telegram_delivery_retry_budget` 内最多重试 `telegram_delivery_max_retries` 次；普通消息和媒体发送不会自动重试，以避免网络超时造成重复消息。草稿和过期的流式预览会合并，限流等待可被取消。

## 主题会话与路由

启用 Telegram 私聊主题后，同一私聊中的每个主题都会使用独立的 AstrBot 会话。普通私聊仍使用 chat ID；主题会话使用 `<chat_id>#<message_thread_id>` 作为内部路由标识，因此回复、主动消息、输入状态和流式输出都会回到原主题。向主动消息接口提供从该会话保存的完整目标时，也会保留主题路由。

Telegram 群组主题继续按主题隔离；群组的 General topic 保留父群路由，发送时不会显式传递 General topic 的 thread `1`。私聊 General topic 会保留独立会话身份，但同样不会向 Telegram API 显式传递 thread `1`。

:::warning
`sendMessageDraft` 功能需要 `python-telegram-bot>=22.6`。
:::
