# 群聊上下文感知

群聊上下文感知会记录机器人上次回复之后的群聊消息，并在下一次唤醒 LLM 时把这些消息作为额外上下文注入。它只作用于群聊，默认关闭。

该能力位于配置档的 **配置文件 → 扩展功能 → 群聊上下文感知**。JSON 键仍是历史名称 `provider_ltm_settings`，不要把它当成 Alkaid [长期记忆](./long-term-memory) 的开关。

## 会记录什么

开启 `group_icl_enable` 后，AstrBot 按统一消息来源（UMO）在内存中保存群消息，直到下一次 LLM 请求：

- 文本、@、引用、合并转发摘要、JSON 卡片摘要；
- 可选的群聊图片转述（与主 Agent 当前请求的图片转述分开配置）；
- 指令消息不会记入上下文。

注入完成后，已经交给模型的记录会被清掉，只保留之后新到的消息。`/conversation reset` 会清空该会话的内存缓存。

内存条数由 `group_message_max_cnt` 限制，默认 `300`。重启 AstrBot 会丢失未注入的内存记录。

## 持久化群消息历史

`group_message_history_enable` 是另一条路径：把群消息写入数据库，供 `get_group_message_history` 工具查询。它不会替代上面的内存注入。默认关闭；保留数量由 `group_message_history_max_cnt` 控制，默认 `700`。

## 群聊图片转述

`image_caption` 只给群聊上下文里的图片生成文字描述，需要单独选择 `image_caption_provider_id`。主 Agent 当前请求和引用图片仍使用 `provider_settings.default_image_caption_provider_id`。

- `image_caption_scope`：`all` / `allowlist` / `denylist`
- `image_caption_groups`：只接受完整 UMO
- `image_caption_min_interval`、`image_caption_max_concurrency`：限流
- `image_caption_cache_ttl`：默认 `0`（关闭）
- `image_caption_lazy`：先记占位，真正唤醒 LLM 时再转述

## 和长期记忆的区别

|      | 群聊上下文感知                                     | Alkaid 长期记忆                  |
| ---- | -------------------------------------------------- | -------------------------------- |
| 作用 | 把近期群聊消息注入下一次 LLM 请求                  | 从已完成对话提取事实、画像和事件 |
| 范围 | 当前群会话（UMO）                                  | 用户与消息会话                   |
| 开关 | `provider_ltm_settings.group_icl_enable`，默认关闭 | 当前没有配置档开关               |
