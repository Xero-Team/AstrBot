# Configuring Custom Model Parameters

Open **Providers** in the AstrBot WebUI left sidebar, then edit the provider you want to customize.

In the provider edit dialog, find the `Custom request body parameters` (`custom_extra_body`) field. Any key/value pair you add here is merged into the request body sent to the model, so you can tune parameters such as `temperature`, `top_p`, `max_tokens`, and `reasoning_effort` per provider.

The WebUI pre-fills a template for the common `temperature`, `top_p`, and `max_tokens` parameters; you can add any other parameter your provider supports the same way. Supported keys differ by provider: Gemini accepts `temperature`, `max_output_tokens` (or `max_tokens`/`maxOutputTokens`), `top_p`, `top_k`, `frequency_penalty`, `presence_penalty`, `stop_sequences`, `response_logprobs`, `logprobs`, and `seed`, and rejects unsupported keys such as `reasoning_effort` before sending the request.

If you need to customize HTTP request headers instead (for example, to pass a non-standard auth header), use the `Custom request headers` (`custom_headers`) field, which is merged into the OpenAI SDK's `default_headers`.

You can also edit these fields directly in `data/cmd_config.json`, under the corresponding entry in the `provider` list:

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

For the exact parameters supported, refer to the corresponding provider's own documentation.
