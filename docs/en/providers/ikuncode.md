# Connect IkunCode

IkunCode provides an OpenAI Chat Completions-compatible API.

## Configure AstrBot

Open the AstrBot dashboard and go to **Providers → Add Provider Source → IkunCode**. Enter your IkunCode API key. The preset uses the following API Base by default:

```text
https://api.ikuncode.cc/v1
```

You can replace the API Base when using a compatible gateway or deployment. Save the source, then add models using the model IDs provided by IkunCode.

## Model capabilities

IkunCode model capabilities can vary. Verify the selected model's support for tool calls, vision, audio, streaming usage, and reasoning before enabling those features in AstrBot.

## Set as default

Go to **Config → Provider Settings**, select an IkunCode model as the default chat model, and save the configuration.
