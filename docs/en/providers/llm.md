# Provider Configuration

Configure model services in WebUI at `Providers -> + Add Provider`.

> [!TIP]
> If the service you want is not listed explicitly but provides an OpenAI-compatible API, you can usually select `OpenAI` and connect it by overriding `API Base URL`.

![image](https://files.astrbot.app/docs/source/images/llm/image.png)

![image](https://files.astrbot.app/docs/source/images/llm/image-1.png)

## Important Distinction

- `Providers` registers model endpoints and credentials.
- `Conversation` selects the default chat model for the current configuration.
- `Agent Runners` is a separate path for third-party orchestration services such as Dify, Coze, and Alibaba Bailian Applications.

> Provider settings are stored in the `provider` field of `data/cmd_config.json`.
