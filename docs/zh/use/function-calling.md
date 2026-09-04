---
outline: deep
---

# 函数调用（Function-calling）

函数调用让模型在同一轮对话里调用外部工具，例如网页搜索、待办、知识库检索、沙箱或插件提供的工具。

入口：WebUI **插件 → 工具**（管理行为面板）。MCP 和 Skills 是旁边的标签，见 [MCP](./mcp) 和 [技能](./skills)。

## 和指令的区别

|          | 工具                                 | 指令                                                                                      |
| -------- | ------------------------------------ | ----------------------------------------------------------------------------------------- |
| 谁触发   | 模型按 schema 选择                   | 用户打 `command_prefixes` 开头的命令                                                      |
| 在哪管理 | **插件 → 工具**                      | **指令管理**                                                                              |
| 稳定 ID  | 工具名（插件工具、MCP 工具另有前缀） | `command_id`，格式 `插件名:原指令路径`（空格换成点），例如 `builtin_commands:plugin.list` |

`command_id` 只用于指令的启用、重命名和权限覆盖，**不是**工具开关。不要在工具面板里找 `command_id`。指令说明见 [内置指令](./command) 和 [WebUI 指令管理](./webui#指令管理)。

## 打开或关闭工具

在工具面板可以：

1. 打开或关闭工具总开关；
2. 逐个允许或禁止内置工具、插件工具和 MCP 工具；
3. 打开原生并行执行（默认关闭）。

最终能否调用还要过三道关：用户授权 ∩ Persona 允许的工具 ∩ 工具自身策略。Persona 里把工具设成空列表，等于这个角色不能用工具，见 [Persona](./persona)。子 Agent handoff 不能提升调用者的权限。

高风险工具（本机 Shell、文件写入、浏览器、Computer Use、可写 MCP）还要满足 [授权管理](./authorization) 和 ChatUI step-up。IM 消息不会继承 Dashboard `root`。

## 哪些模型能用

主流在 2025 年后发布的对话模型通常支持函数调用，例如 GPT-5.x、Gemini 3.x、Claude 4.x、DeepSeek v3.2（deepseek-chat）、Qwen 3.x。较老的 DeepSeek-R1、Gemini 2.0 thinking 类常常不支持。

服务端报 `tool call is not supported` / `function calling is not supported` / `tool use is not supported` 时，AstrBot 多数情况下会自动去掉工具再试。也可以在面板里先关掉全部工具，或换支持工具的模型。Provider 上的「工具调用」开关必须和服务实际能力一致，见 [服务提供商配置](/providers/llm)。

插件除了传统指令，也可以同时暴露工具。市场里的插件是否真的提供工具，以该插件自己的说明为准。

常见调用示意：

![函数调用示例](https://files.astrbot.app/docs/source/images/function-calling/image.png)

![工具结果示例](https://files.astrbot.app/docs/source/images/function-calling/image-1.png)

## 原生并行工具调用

同一轮模型响应里，彼此独立的调用可以并行执行。默认关闭。需要先打开总开关，再逐个允许工具。

下列工具不能开并行：有副作用、直接向用户发消息、Handoff、后台任务，或明确要求串行。

即使完成顺序不同，写回模型上下文的结果仍保持调用顺序。MCP 工具使用按服务器划分的并发限制（默认 1），允许某个工具并行，不会自动让有共享状态的 MCP 服务器并发执行。

## 知识库的 Agentic 检索

配置档打开 `kb_agentic_mode` 后，知识库检索变成工具 `astr_kb_search`，由模型决定何时查询。关闭时（默认），检索结果会直接注入当前请求。见 [知识库](./knowledge-base#agentic-检索)。

## 常见误配

1. 在 **指令管理** 里找工具开关。
2. 模型不支持 function calling，却开着一堆工具。
3. Persona 把工具列表留空，面板上看起来是开的。
4. 打开并行后，MCP 服务器仍串行，因为每服务器并发默认是 1。
