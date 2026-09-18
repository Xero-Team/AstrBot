# 平台处理

配置文件的 **平台配置** 和 **扩展功能** 里，有一组所有消息平台共用的收发行为。它们在 [唤醒检查](./group-wake) 之后生效：策略已经放行的消息，仍可能被未列入会话或未列入发送者策略、限流或内容安全丢掉。

入口：WebUI **配置文件 → 平台配置**。分段回复在 **扩展功能**。这些字段属于当前配置文件，见 [配置文件](./config-profiles)。

## 未列入会话和发送者

| 字段                          | 默认    | 说明                                                                |
| ----------------------------- | ------- | ------------------------------------------------------------------- |
| `admission.unlisted_sessions` | `allow` | `allow` 放行没有覆盖的会话；`deny` 只放行已有会话覆盖的群或私聊     |
| `admission.unlisted_senders`  | `allow` | `allow` 放行没有覆盖的发送者；`deny` 只放行已有发送者覆盖的 IM 主体 |

默认 `allow`：新群和新私聊都会进入后续流水线。改成 `deny` 后，只有规范会话键上已有覆盖、或本配置档升级列入集里的会话会被响应。覆盖来自 IM `/llm`、Dashboard [自定义规则](./custom-rules) 写入的 `llm_enabled` / `session_enabled` / `session_blocked`。升级时旧白名单按配置档记入列入集，不会把 `session_enabled` 写到偏好里。

群准入用的是规范会话键（`session:{平台实例}:group:{群 ID}`），不是隔离会话改写后的 UMO。私聊用 `session:{平台实例}:private:{对方 ID}`。发送者覆盖写在 `im:{平台实例}:{机器人账号}:{发送者 ID}` 上，对本机器人实例全局生效。WebChat、OneBot 的 `notice` / `request`，以及当前实例上拥有 `provider.manage` 的发送者，会跳过这一关。默认 `unlisted_senders=allow`：没有发送者覆盖的人仍然放行。改成 `deny` 后，只有已写入 `blocked` 或 `llm_enabled` 的发送者会被列入。Dashboard [自定义规则](./custom-rules) 的发送者目标和 `/user block`、`/user unblock`、`/user llm on|off` 写入同一份发送者覆盖。写入任意 `blocked` 或 `llm_enabled` 都会列入该发送者。

旧的 `id_whitelist`、`enable_id_white_list` 和 `wl_ignore_admin_*` 已删除，Dashboard 写入这些字段会失败。升级时：空列表或关闭的白名单变成 `allow`；非空且开启的列表变成 `deny`，并把条目列入该配置档。裸 ID 会按该配置档里每个 `platform[].id` 展开成群会话键。隔离会话 UMO 会按 `sender_id_group_id` / `sender_id%group_id` 解开成群 ID。

## 速率限制

默认：60 秒内 30 条。超出后：

- `stall`（默认）：等待
- `discard`：直接丢弃

限流按会话计。隔离会话开启后，群成员各自计数。

## 内容安全

内置关键词检查默认开启，可追加正则关键词。可选接入百度内容审核（需要自行安装 `baidu-aip`）。`also_use_in_response` 会连模型回复一起检查。

被拦下的消息不会进入 LLM。不要把内容安全当成唤醒开关。

## 入站回合合并

`inbound_coalesce.enable` 默认关闭。开启后，私聊里连续的 LLM 消息会在有界窗口内合并成一轮；当前实现**不合并群聊**。

| 字段                | 作用                               |
| ------------------- | ---------------------------------- |
| `wait_seconds`      | 静默多久视为一轮说完               |
| `max_total_seconds` | 窗口最长寿命，不会因新片段无限延长 |
| `max_typing_wait`   | 输入状态丢失时的保护超时           |

后续片段不必重复 LLM 前缀。收到指令会丢弃缓冲回合。NapCat 的 `input_status` 只暂停或恢复窗口，不进入消息流水线。

## 分段回复

默认关闭。只对非流式结果切段发送，可限制为仅 LLM 结果。间隔可以是随机时间，或按字数取对数。当前 `forward_threshold`（默认 1500 字）仅对 OneBot 的 `aiocqhttp` 适配器生效，会把长回复改成转发节点；其他平台是否支持取决于适配器。

流式回复、以及开启群发送者并发的群，不会按这段规则切。

## 文本转图像

`t2i` 默认关闭。超过 `t2i_word_threshold`（默认 150 字）时，可以把长文本渲染成图片再发送。模板和中文字体在 **设置** 里维护；容器内必须实际安装对应字体。乱码排查见 [FAQ](/faq#t2i-中文乱码)。

## 其他常用项

- **回复前缀 / @ 发送人 / 引用原消息**：实际能力取决于适配器。
- **忽略机器人自身消息**：某些平台会把机器人在其他端发的消息再推回来。
- **权限不足时回复**：用户没权限执行指令时是否提示。
- **只打指令前缀是否触发等待**：由 `empty_mention_waiting` 控制，见 [群聊何时会理我](./group-wake#只打了指令前缀、没有正文)。

飞书 / Telegram / Discord 的预回应表情在「其他配置」里，按平台分开。
