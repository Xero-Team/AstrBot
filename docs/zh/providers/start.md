# 模型提供商

AstrBot 将“模型服务”和“Agent 执行器”分开处理：

- `服务提供商`：管理模型服务的接口类型、`API Base URL`、`API Key` 和可用模型列表。
- `对话`：为当前配置选择默认对话模型。
- `Agent 执行器`：负责多轮对话、工具调用和编排；其中包含 Dify、Coze、阿里云百炼应用、DeerFlow 等第三方服务集成。

## 当前 fork 的实际支持范围

内置对话模型接入基于以下三种原生接口格式：

- OpenAI / OpenAI 兼容接口
- Anthropic
- Google Gemini

如果某个服务没有单独的接入向导，但它提供 OpenAI 兼容接口，通常直接选择 `OpenAI` 并填写对应的 `API Base URL` 与 `API Key` 即可。

本地模型请参考：

- [Ollama](/providers/provider-ollama)
- [LM Studio](/providers/provider-lmstudio)

第三方 Agent 服务请参考：

- [Agent 执行器概览](/providers/agent-runners)

## 配置流程

1. 打开 WebUI 的 `服务提供商` 页面，点击 `+ 新增服务提供商`。
2. 选择接口类型，填写 `API Base URL`、`API Key` 等配置。
3. 获取模型列表，并启用需要使用的模型。
4. 打开 `对话` 页面，为当前配置选择默认对话模型。
5. 如果使用第三方 Agent 服务，在 `Agent 执行器` 相关页面单独配置，不要和对话模型配置混为一谈。

## 配置存放位置

- 提供商相关配置保存在 `data/cmd_config.json` 的 `provider` 字段中。
- 当前配置使用哪个对话模型，由对应配置文件中的对话模型设置决定。

## 使用环境变量加载 Key

支持使用环境变量加载模型服务提供商的 API Key。在提供商配置页面，将 `API Key` 一栏填写为 `$环境变量名称`，例如 `$OPENAI_API_KEY`。
