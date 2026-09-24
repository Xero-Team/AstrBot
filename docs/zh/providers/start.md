# 模型 Provider

AstrBot 把 API 来源、具体模型和 Agent 执行器分成三层：

- **Provider 来源**保存接口类型、API Base、API Key、代理和类型级能力。
- **模型**引用一个 Provider 来源，并保存模型 ID、上下文窗口、模态和生成参数。
- **Agent 执行器**决定如何运行多轮任务。内置 `local` Runner 使用上述聊天模型；Dify、Coze、阿里云百炼应用和 DeerFlow 是单独的外部 Runner，不是普通聊天 Provider。

## 当前能力范围

WebUI 当前提供以下 Provider 类别：

| 类别            | 内置类型与代表性集成                                                                                                                                                                                                                                             |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chat Completion | OpenAI Chat Completions/兼容接口、OpenAI Responses、Anthropic、Google Gemini，以及 OpenCode Go Chat Completions、OpenCode Go Messages、OpenCode Go Responses、Kimi Code、MiniMax Token Plan、小米、xAI、智谱、LongCat、Groq、OpenRouter、AIHubMix 等专用适配器。 |
| Speech to Text  | OpenAI Whisper API、自托管 Whisper、SenseVoice、Mimo、Xinference。                                                                                                                                                                                               |
| Text to Speech  | OpenAI、Mimo、Genie、Edge TTS、GPT-SoVITS、FishAudio、DashScope、Azure、MiniMax、火山引擎、Gemini、ElevenLabs。                                                                                                                                                  |
| Embedding       | OpenAI、Gemini、NVIDIA、Ollama。                                                                                                                                                                                                                                 |
| Rerank          | vLLM、Xinference、阿里云百炼、NVIDIA。                                                                                                                                                                                                                           |
| Classifier      | JEV System One（`jev_systemone`），提供类型化的 `noul`、`choice` 和 `score` 判定。                                                                                                                                                                               |
| Agent Runner    | Dify、Coze、阿里云百炼应用、DeerFlow；在配置档中选择，不作为本地模型调用。                                                                                                                                                                                       |

模板列表来自当前代码注册表，后续版本可能变化；以 **提供商 → 新增 Provider 来源** 中实际显示的类型为准。

## 推荐配置流程

1. 打开 WebUI 的 **提供商** 页面，在 Provider Sources 区域新增来源。
2. 选择准确的接口类型，填写 API Base、API Key 和代理等字段。
3. 从来源获取模型，或手动新增模型并填写准确模型 ID。
4. 为模型核对 `max_context_tokens`、支持的模态和工具调用能力。
5. 打开 **配置**，编辑当前配置档，在功能支持的位置选择默认聊天、STT、TTS、Embedding、Rerank 或分类器提供商。
6. 使用“测试”功能或真实会话验证，再配置 fallback 和重试。

Provider 数据保存在配置档的两个数组中：

- `provider_sources`：共享端点与凭据；
- `provider`：通过 `provider_source_id` 引用来源的模型实例。

不要手工复制旧版 `provider` 对象。当前 WebUI 会在重命名来源时同步模型引用，并在删除来源前处理关联模型。

## JEV System One 分类器

在 **模型提供商 → 分类器 → 添加提供商** 中选择 **JEV System One**
（类型 `jev_systemone`）。
填写 HTTPS API 地址（默认 `https://api.typesafe.ai`）、API Key、模型
（默认 `jev-latest`）和超时秒数。这是 `provider` 中能力类型为
`classifier` 的独立条目，不是对话模型或 Agent Runner。Key 列表使用首项，
支持 `$ENV_VAR` 环境变量引用。遵循提供商和全局的显式代理设置，保持 TLS
证书校验并拒绝重定向。测试连接会产生付费 API 请求。

适配器实现 [TypeSafe System One API](https://docs.typesafe.ai/api)：
`noul` 返回 P(yes)，`choice` 返回选项和概率分布，`score` 返回加权分数与等级说明。
只有 `choice` 和 `score` 含独立的 `confidence` 字段。结果保留实际模型版本和
输入、输出 token 用量。畸形响应会被拒绝；HTTP 429/529 在总超时内以指数退避
最多重试两次，其他 HTTP 错误不重试，不暴露远端错误正文。

添加分类器不会自动开启 BTW 路由。这是
[#272](https://github.com/Xero-Team/AstrBot/issues/272) 的 R4 实验，仍需在
[#122](https://github.com/Xero-Team/AstrBot/issues/122) 下完成方案比较。

## 选择接口类型

- 服务明确提供 OpenAI Chat Completions 兼容端点时，使用 **OpenAI Chat Completions** 或对应预设。
- 需要 OpenAI Responses 的远端会话状态、后台响应或原生 Web Search 时，选择 **OpenAI Responses**；它不是 Chat Completions 的同义名称。
- 接入 OpenCode Go 时必须选择 **OpenCode Go Chat Completions**、**OpenCode Go Messages** 或 **OpenCode Go Responses** 专用类型，并与模型端点匹配；不要把官方 OpenAI / Anthropic / OpenAI Responses 来源指向 `https://opencode.ai/zen/go/v1`。协议对照见 [Provider 配置](./llm)。
- Anthropic 和 Gemini 应优先使用各自原生适配器，以保留 thinking、原生搜索、图片输出或安全设置。Anthropic 的 API Base 填 `https://api.anthropic.com`，不要带 `/v1`。
- “OpenAI 兼容”只表示请求协议相近，不保证工具调用、视觉、音频、流式 usage 或 reasoning 字段都兼容。逐项测试实际模型能力。

详细字段见 [Provider 配置](./llm)。本地模型见 [Ollama](./provider-ollama) 和 [LM Studio](./provider-lmstudio)，外部编排服务见 [Agent 执行器](./agent-runners)。

## 使用环境变量保存 Key

API Key 字段支持 `$环境变量名称` 形式，例如 `$OPENAI_API_KEY`。环境变量必须存在于 AstrBot 进程环境中；容器部署时应通过 Secret、受限的 env 文件或编排系统注入，而不是写入镜像或提交到仓库。
