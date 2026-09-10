# 接入 IkunCode

IkunCode 提供兼容 OpenAI Chat Completions 的接口。

## 在 AstrBot 中配置

打开 AstrBot 管理面板，进入 **提供商 → 新增 Provider 来源 → IkunCode**，填写 IkunCode API Key。该预设默认使用以下 API Base：

```text
https://api.ikuncode.cc/v1
```

如需使用兼容网关或其他部署地址，可以修改 API Base。保存来源后，按照 IkunCode 提供的模型 ID 添加模型。

## 模型能力

IkunCode 不同模型的能力可能不同。启用 AstrBot 的对应功能前，请确认所选模型是否支持工具调用、视觉、音频、流式 usage 和 reasoning。

## 设为默认模型

进入 **配置文件 → 提供商设置**，将 IkunCode 模型设为默认聊天模型，然后保存配置。
