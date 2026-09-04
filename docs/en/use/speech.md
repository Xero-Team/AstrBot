# Speech STT / TTS

Speech is two steps: create models on **Providers**, then turn on the profile switches and pick defaults. A Provider without the profile switch will not transcribe or speak.

Provider types and secrets are in [Provider configuration](/en/providers/llm#tts-and-elevenlabs). This page only covers wiring them to a profile and session.

## Profile switches

Open **Config → AI → Models**.

| Field                                       | Dashboard label    | Default | Role                                   |
| ------------------------------------------- | ------------------ | ------- | -------------------------------------- |
| `provider_stt_settings.enable`              | Speech recognition | Off     | Transcribe user audio before the model |
| `provider_stt_settings.provider_id`         | Default STT model  | Empty   | Profile default STT                    |
| `provider_tts_settings.enable`              | Voice replies      | Off     | Speak model text                       |
| `provider_tts_settings.provider_id`         | Default TTS model  | Empty   | Profile default TTS                    |
| `provider_tts_settings.trigger_probability` | TTS probability    | `1`     | `0`–`1`; below 1 randomly skips        |
| `provider_tts_settings.dual_output`         | Dual output        | Off     | Send text and audio                    |
| `provider_tts_settings.use_file_service`    | File service       | Off     | Deliver audio through the file service |

These fields belong to the current profile. Different groups can bind different profiles and voices. See [Configuration profiles](./config-profiles).

## Session overrides

You do not need a profile per group:

1. **Custom rules**: disable TTS for one UMO, or pin chat / STT / TTS models. Rules outrank the profile. See [Custom rules](./custom-rules).
2. **Commands**: `/provider list` shows LLM, STT, and TTS. `/provider set stt <index>` and `/provider set tts <index>` switch the current session. Requires `provider.use`. See [Built-in commands](./command#providers-and-models).

With no rule, the session follows the profile: if the profile enabled STT/TTS, the session processes it.

## Setup order

1. Add STT and TTS sources and models on **Providers**, save, and test.
2. Open the target profile, enable speech recognition and/or voice replies, pick defaults, save.
3. Confirm the group is bound to that profile.
4. Add a custom rule or `/provider set` only for exceptions.
5. Send voice on the target platform, then ask the model to reply with audio.

Whether QQ, Telegram, or another adapter can play the file is adapter-defined. A successful Provider test is not enough.

## Common misconfigurations

1. TTS exists on Providers, but the profile switch is still off.
2. A custom rule disabled TTS for the session.
3. Trigger probability is low, so voice seems intermittent.
4. An ElevenLabs / MiMo model name was retired upstream; saved Provider rows are not rewritten.
5. You edited `default`, but the group uses another profile.
