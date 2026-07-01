# Model Providers

AstrBot treats model services and agent orchestration as separate concerns:

- `Providers`: manage endpoint type, `API Base URL`, `API Key`, and available model list.
- `Conversation`: choose the default chat model for the current configuration.
- `Agent Runners`: handle multi-turn execution, tool calling, and orchestration; this includes third-party integrations such as Dify, Coze, Alibaba Bailian Applications, and DeerFlow.

## What this fork actually supports

The built-in chat model path supports these native API formats:

- OpenAI / OpenAI-compatible APIs
- Anthropic
- Google Gemini

If a service does not have its own dedicated guide but exposes an OpenAI-compatible API, select `OpenAI` and fill in its `API Base URL` and `API Key`.

For local models, see:

- [Ollama](/en/providers/provider-ollama)
- [LM Studio](/en/providers/provider-lmstudio)

For third-party orchestration services, see:

- [Agent Runners Overview](/en/providers/agent-runners)

## Configuration Flow

1. Open WebUI `Providers` and click `+ Add Provider`.
2. Choose the API type and fill in `API Base URL`, `API Key`, and related fields.
3. Fetch the model list and enable the models you want to use.
4. Open `Conversation` and choose the default chat model for the current configuration.
5. If you use a third-party orchestration service, configure it in the `Agent Runners` section separately instead of mixing it with chat-model setup.

## Where the Configuration Lives

- Provider-related settings are stored in the `provider` field of `data/cmd_config.json`.
- The selected default chat model is stored in the active configuration file.

## Using Environment Variables for Keys

You can load provider API keys from environment variables. In the provider configuration form, set the `API Key` field to `$ENV_VARIABLE_NAME`, for example `$OPENAI_API_KEY`.
