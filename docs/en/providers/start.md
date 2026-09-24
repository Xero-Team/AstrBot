# Model Providers

AstrBot separates API sources, concrete models, and Agent execution into three layers:

- A **Provider source** stores the API type, base URL, API key, proxy, and source-level capabilities.
- A **model** references a Provider source and stores the model ID, context window, modalities, and generation parameters.
- An **Agent Runner** controls multi-step execution. The built-in `local` runner uses chat models from the first two layers; Dify, Coze, Alibaba Bailian Applications, and DeerFlow are separate external runners, not ordinary chat Providers.

## Current capability range

The current WebUI exposes these Provider categories:

| Category        | Built-in types and representative integrations                                                                                                                                                                                                                                          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chat Completion | OpenAI Chat Completions and compatible APIs, OpenAI Responses, Anthropic, Google Gemini, plus dedicated OpenCode Go Chat Completions, OpenCode Go Messages, OpenCode Go Responses, Kimi Code, MiniMax Token Plan, Xiaomi, xAI, Zhipu, LongCat, Groq, OpenRouter, and AIHubMix adapters. |
| Speech to Text  | OpenAI Whisper API, self-hosted Whisper, SenseVoice, Mimo, and Xinference.                                                                                                                                                                                                              |
| Text to Speech  | OpenAI, Mimo, Genie, Edge TTS, GPT-SoVITS, FishAudio, DashScope, Azure, MiniMax, Volcengine, Gemini, and ElevenLabs.                                                                                                                                                                    |
| Embedding       | OpenAI, Gemini, NVIDIA, and Ollama.                                                                                                                                                                                                                                                     |
| Rerank          | vLLM, Xinference, Alibaba Bailian, and NVIDIA.                                                                                                                                                                                                                                          |
| Classifier      | JEV System One (`jev_systemone`) for typed `noul`, `choice`, and `score` decisions.                                                                                                                                                                                                     |
| Agent Runner    | Dify, Coze, Alibaba Bailian Applications, and DeerFlow; selected by a profile rather than invoked as a local model.                                                                                                                                                                     |

Templates come from the current code registry and can change in later releases. Treat the list shown under **Providers → Add Provider Source** as authoritative for the running version.

## Recommended configuration flow

1. Open **Providers** and add a source in the Provider Sources section.
2. Select the exact API type and enter its base URL, API key, proxy, and related fields.
3. Fetch models from the source or add a model with the exact model ID.
4. Verify `max_context_tokens`, modalities, and tool-calling capability for each model.
5. Open **Config**, edit the active profile, and select the default chat, STT, TTS, embedding, rerank, or classifier provider where the feature supports it.
6. Use the test action or a real conversation before configuring fallback and retries.

Provider data is stored in two profile arrays:

- `provider_sources` contains shared endpoints and credentials;
- `provider` contains model instances linked through `provider_source_id`.

Do not copy old `provider` objects by hand. The current WebUI coordinates model references when a source is renamed and handles dependent models when a source is removed.

## JEV System One classifier

Under **Providers → Classifier → Add Provider**, choose `jev_systemone`.
Set the HTTPS API base (default `https://api.typesafe.ai`), API key, model
(`jev-latest` by default), and timeout in seconds. This is a standalone entry
in `provider`, with capability `classifier`; it is not a chat model or Agent
Runner. The key list uses its first entry and accepts `$ENV_VAR` references.
Explicit provider/global proxy settings apply; TLS verification stays enabled
and redirects are refused. Testing connectivity makes a paid API request.

The adapter implements [TypeSafe's System One API](https://docs.typesafe.ai/api):
`noul` returns P(yes), `choice` returns a selected option and probability
distribution, and `score` returns a weighted level and legend. Only `choice`
and `score` have a separate `confidence` field. Results include the resolved
model version and input/output token usage. Malformed answers fail validation;
HTTP 429/529 retry at most twice with exponential backoff within the total
timeout. Other HTTP failures do not retry, and error bodies are not exposed.

Adding a classifier does not enable automatic BTW routing. This is the R4
experiment in [#272](https://github.com/Xero-Team/AstrBot/issues/272), pending
comparison under [#122](https://github.com/Xero-Team/AstrBot/issues/122).

## Choosing an API type

- Use **OpenAI Chat Completions** or a matching preset when the service explicitly exposes a compatible Chat Completions endpoint.
- Use **OpenAI Responses** when you need its remote state modes, background responses, or native Web Search. It is not an alias for Chat Completions.
- Use the dedicated **OpenCode Go Chat Completions**, **OpenCode Go Messages**, or **OpenCode Go Responses** types for OpenCode Go, matching the model's endpoint. Do not point official OpenAI, Anthropic, or OpenAI Responses sources at `https://opencode.ai/zen/go/v1`. See [Provider Configuration](./llm) for the protocol map.
- Prefer native Anthropic and Gemini adapters to retain thinking, native search, image output, or safety settings. For Anthropic, set API Base to `https://api.anthropic.com` without `/v1`.
- “OpenAI compatible” only means the request protocol is similar. It does not guarantee compatible tools, vision, audio, streaming usage, or reasoning fields. Test each required capability.

See [Provider Configuration](./llm) for field details. For local models, see [Ollama](./provider-ollama) and [LM Studio](./provider-lmstudio). For external orchestration, see [Agent Runners](./agent-runners).

## Loading keys from environment variables

API-key fields accept `$ENV_VARIABLE_NAME`, such as `$OPENAI_API_KEY`. The variable must exist in the AstrBot process environment. In containers, inject it through a Secret, restricted env file, or orchestration platform instead of baking it into an image or committing it.
