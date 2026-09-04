# 语音 STT / TTS

语音要分两段配：先在 **提供商** 页创建模型，再在 **配置文件** 里打开总开关并选默认模型。只创建 Provider、不打开配置文件开关，会话不会转写或播报。

Provider 类型和密钥见 [服务提供商配置](/providers/llm#tts-与-elevenlabs)。本页只说明怎么接到配置文件和会话。

## 配置文件开关

入口：WebUI **配置文件 → AI 配置 → 模型**。

| 字段                                        | Dashboard 名称     | 默认 | 作用                         |
| ------------------------------------------- | ------------------ | ---- | ---------------------------- |
| `provider_stt_settings.enable`              | 语音识别           | 关闭 | 把用户语音转成文字再送给模型 |
| `provider_stt_settings.provider_id`         | 默认语音转文本模型 | 空   | 本配置文件的默认 STT         |
| `provider_tts_settings.enable`              | 语音回复           | 关闭 | 把模型文字转成语音发出       |
| `provider_tts_settings.provider_id`         | 默认文本转语音模型 | 空   | 本配置文件的默认 TTS         |
| `provider_tts_settings.trigger_probability` | TTS 触发概率       | `1`  | `0`–`1`，小于 1 时按概率跳过 |
| `provider_tts_settings.dual_output`         | 双输出             | 关闭 | 同时发送文字和语音           |
| `provider_tts_settings.use_file_service`    | 使用文件服务       | 关闭 | 通过文件服务下发音频         |

这些字段属于当前配置文件。不同群可以绑定不同配置文件，从而使用不同的声音或识别模型。见 [配置文件](./config-profiles)。

## 会话级覆盖

不必为每个群拆配置文件：

1. **自定义规则**：为指定 UMO 关闭 TTS，或指定聊天 / STT / TTS 模型。规则高于配置文件。见 [自定义规则](./custom-rules)。
2. **指令**：`/provider list` 查看 LLM、STT、TTS；`/provider set stt <序号>`、`/provider set tts <序号>` 切换当前会话。需要 `provider.use`。见 [内置指令](./command#provider-与模型)。

未写规则时，会话默认跟随配置文件：配置文件开了 STT/TTS，会话就处理。

## 使用顺序

1. 在 **提供商** 新增 STT、TTS 来源和模型，保存并测试。
2. 打开目标配置文件，启用「语音识别」和/或「语音回复」，选好默认模型，保存。
3. 确认该群绑定的是这份配置文件。
4. 需要特例时，再加自定义规则或用 `/provider set`。
5. 在目标平台发一条语音，看是否转写；让模型回一条，看是否出语音。

音频最终能不能在 QQ、Telegram 等平台播放，取决于适配器，不能只看 Provider 测试成功。

## 常见误配

1. 提供商页已经有 TTS，配置文件总开关仍关着。
2. 自定义规则关掉了该会话的 TTS，配置文件再开会被覆盖。
3. 触发概率设得很低，听起来像「有时不语音」。
4. ElevenLabs / MiMo 等模型名已在服务商侧下线，已保存的 Provider 条目不会自动改写。
5. 改了 `default`，当前群绑定的是另一份配置文件。
