# 配置自定义的模型参数

在 AstrBot WebUI 左侧导航栏中打开 **模型提供商**，编辑你想要自定义的提供商。

在提供商编辑弹窗中，找到 `自定义请求体参数`（`custom_extra_body`）字段。这里添加的键值对会被合并进发送给模型的请求体，因此可以按提供商单独调整 `temperature`、`top_p`、`max_tokens`、`reasoning_effort` 等参数。

WebUI 会预填 `temperature`、`top_p`、`max_tokens` 这几个常用参数的模板，你也可以按同样的方式添加提供商支持的其他参数。不同提供商支持的键不同：Gemini 接受 `temperature`、`max_output_tokens`（或 `max_tokens`/`maxOutputTokens`）、`top_p`、`top_k`、`frequency_penalty`、`presence_penalty`、`stop_sequences`、`response_logprobs`、`logprobs` 和 `seed`，并会在发送请求前拒绝 `reasoning_effort` 等不支持的键。

如果需要自定义 HTTP 请求头（例如传递非标准的认证头），请使用 `自定义请求头`（`custom_headers`）字段，它会被合并进 OpenAI SDK 的 `default_headers` 中。

你也可以直接编辑 `data/cmd_config.json`，修改 `provider` 列表中对应条目：

```json
{
  "provider": [
    {
      "id": "my-provider",
      "custom_extra_body": {
        "temperature": 0.6,
        "top_p": 1.0,
        "max_tokens": 8192
      },
      "custom_headers": {}
    }
  ]
}
```

具体支持哪些参数，请参看对应提供商自己的文档。
