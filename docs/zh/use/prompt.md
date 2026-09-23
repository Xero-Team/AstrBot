# Prompt 提示词设定

Prompt 决定 Agent 在一次会话中采用的系统提示词、预设对话、工具、Skills 和错误回复。你可以在 WebUI 左侧的 **提示词设定** 页面创建 Prompt，并用文件夹组织大量角色。

## Prompt 包含什么

- **Prompt ID**：唯一标识。会话、配置档、子代理和定时任务都通过它引用 Prompt，因此创建后应尽量保持稳定。
- **系统提示词**：定义角色、目标、边界和回复方式。不要在其中保存密钥或其他不应发送给模型的机密。
- **自定义报错回复**：当前 Prompt 的 LLM 请求失败时优先向用户发送的文本；留空则使用系统默认错误消息。
- **预设对话**：按“用户、助手”成对排列的 few-shot 示例，条数必须为偶数。它们会加入模型上下文，但不会作为真实会话消息写回历史。
- **工具 / MCP 工具**：`null` 表示允许所有当前可用工具，明确的名称列表表示只允许这些工具，空列表表示不允许普通工具。空列表仍保留 `read_skill`，以便读取本请求已启用的 Skill 手册。
- **Skills**：语义与工具相同；可以使用全部、只使用选定项或不使用任何 Skill。空 Skills 列表同时禁用工作区 Skill。

工具和 Skills 是权限边界，不只是提示词优化。对 Shell、文件写入、浏览器、外部账号和管理类工具，应采用最小权限，并在模型或插件变化后重新检查选择结果。

## 哪个 Prompt 会生效

本地 Agent Runner 按以下优先级解析 Prompt：

1. **会话管理**中针对该消息会话设置的强制 Prompt；
2. 当前对话记录选择的 Prompt；
3. 当前配置档的默认 Prompt：本地与第三方 Runner 均读取 `agent_runner.config.prompt_id`。

会话规则适合为某个平台、群组或用户固定角色。没有强制规则时，WebChat 可以在对话级切换 Prompt。显式选择“不使用 Prompt”时，不会再应用配置档默认 Prompt。

Prompt 更新后，运行时缓存会立即刷新；通常不需要重启 AstrBot。已经保存的历史消息不会因 Prompt 修改而重写，后续模型请求会使用新配置。

## 对话指令

管理员可以使用 `/prompt status` 查看当前状态、`/prompt list` 列出 Prompt、`/prompt show <prompt_id>` 查看详情、`/prompt set <prompt_id>` 切换当前对话，或用 `/prompt unset` 显式停用 Prompt。仅输入 `/prompt` 会显示子指令树。

## 文件夹与删除

文件夹只用于 WebUI 组织和排序，不改变 Prompt 的运行权限或作用域。删除文件夹时，其中的 Prompt 会移动到根目录，而不是一起删除。

删除 Prompt 会移除 Prompt 定义，但不会自动改写所有外部引用。删除前请检查：

- 配置档的默认 Prompt；
- 会话管理规则和已有对话选择；
- 子代理、Cron 任务或插件中保存的 Prompt ID。

## 导入与导出

Prompt 卡片菜单可以导出 JSON，页面顶部可以导入 JSON。当前格式只交换：

```json
{
  "prompt_id": "researcher",
  "system_prompt": "You are a careful research assistant.",
  "begin_dialogs": ["Summarize this source.", "Please provide the source."]
}
```

导出文件**不包含**工具、Skills、自定义错误回复、文件夹、排序或长期记忆。

导入时：

- 必须存在非空字符串 `system_prompt`；
- `begin_dialogs` 中只有字符串项会保留；
- 导入到当前打开的文件夹；
- ID 冲突时会自动追加 `_imported`、`_imported_2` 等后缀；
- 工具和 Skills 会被设置为“全部可用”。

> [!WARNING]
> Prompt JSON 属于提示词输入，导入第三方文件前应先人工审阅。导入后立即重新配置工具和 Skills；否则该 Prompt 会继承所有当前可用能力。导出文件也不能作为完整备份。

完整迁移应使用 AstrBot 的[运行数据备份](../deploy/astrbot/backup)，而不是只导出 Prompt JSON。恢复后还应核对插件、MCP、Skills 和 Provider 是否仍存在，因为 Prompt 只保存这些能力的名称引用。

## 与其他功能的关系

- [子代理编排](./subagent)：子 Agent 可以绑定 Prompt，并继承其提示词、预设对话和工具；当前不会继承隔离的 Prompt Skills。
- [Skills](./skills)：Prompt 可以缩小当前会话可见的 Skill 集合。
- [长期记忆](./long-term-memory)：长期记忆按用户和消息会话存储，不包含在 Prompt 导出文件中，也不会因为删除 Prompt 而自动清除。
