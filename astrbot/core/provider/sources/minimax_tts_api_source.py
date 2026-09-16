import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Mapping

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "minimax_tts_api",
    "MiniMax TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderMiniMaxTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.api_base: str = provider_config.get(
            "api_base",
            "https://api.minimax.chat/v1/t2a_v2",
        )
        self.group_id: str = provider_config.get("minimax-group-id", "")
        self.set_model(provider_config.get("model", ""))
        self.lang_boost: str = provider_config.get("minimax-langboost", "auto")
        self.is_timber_weight: bool = provider_config.get(
            "minimax-is-timber-weight",
            False,
        )
        default_timber_weight = [
            {"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 1}
        ]
        raw_timber_weight = provider_config.get("minimax-timber-weight", "")
        if not raw_timber_weight:
            self.timber_weight = default_timber_weight
        else:
            try:
                self.timber_weight = json.loads(raw_timber_weight)
            except json.JSONDecodeError:
                logger.warning(
                    "MiniMax TTS weight configuration is invalid; using defaults."
                )
                self.timber_weight = default_timber_weight

        self.voice_setting: dict = {
            "speed": provider_config.get("minimax-voice-speed", 1.0),
            "vol": provider_config.get("minimax-voice-vol", 1.0),
            "pitch": provider_config.get("minimax-voice-pitch", 0),
            "voice_id": ""
            if self.is_timber_weight
            else provider_config.get("minimax-voice-id", ""),
            "emotion": provider_config.get("minimax-voice-emotion", "auto"),
            "latex_read": provider_config.get("minimax-voice-latex", False),
            "english_normalization": provider_config.get(
                "minimax-voice-english-normalization",
                False,
            ),
        }

        if self.voice_setting["emotion"] == "auto":
            self.voice_setting.pop("emotion", None)

        self.audio_setting: dict = {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "wav",
        }

        self.concat_base_url: str = f"{self.api_base}?GroupId={self.group_id}"
        self.headers = {
            "Authorization": f"Bearer {self.chosen_api_key}",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    def _build_tts_stream_body(self, text: str):
        """构建流式请求体"""
        dict_body: dict[str, object] = {
            "model": self.model_name,
            "text": text,
            "stream": True,
            "language_boost": self.lang_boost,
            "voice_setting": self.voice_setting,
            "audio_setting": self.audio_setting,
        }
        if self.is_timber_weight:
            dict_body["timber_weights"] = self.timber_weight

        return json.dumps(dict_body)

    async def _call_tts_stream(self, text: str) -> AsyncIterator[str]:
        """进行流式请求"""
        try:
            async with (
                aiohttp.ClientSession(headers=self.request_headers) as session,
                session.post(
                    self.concat_base_url,
                    headers=self.headers,
                    data=self._build_tts_stream_body(text),
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response,
            ):
                response.raise_for_status()

                buffer = b""
                while True:
                    chunk = await response.content.read(8192)
                    if not chunk:
                        break

                    buffer += chunk

                    while b"\n\n" in buffer:
                        message, buffer = buffer.split(b"\n\n", 1)
                        if not message.startswith(b"data: "):
                            continue

                        try:
                            data = json.loads(message[6:])
                        except json.JSONDecodeError:
                            logger.warning("MiniMax TTS received invalid SSE JSON.")
                            continue

                        if not isinstance(data, Mapping):
                            logger.warning(
                                "MiniMax TTS received an invalid SSE message."
                            )
                            continue

                        if "extra_info" in data:
                            continue

                        response_data = data.get("data")
                        if response_data is None:
                            continue
                        if not isinstance(response_data, Mapping):
                            logger.warning(
                                "MiniMax TTS received an invalid SSE message."
                            )
                            continue

                        audio = response_data.get("audio")
                        if audio is None:
                            continue
                        if not isinstance(audio, str):
                            logger.warning(
                                "MiniMax TTS received an invalid SSE message."
                            )
                            continue
                        yield audio

        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as exc:
            logger.warning("MiniMax TTS API request failed: %s", safe_error("", exc))
            raise RuntimeError("MiniMax TTS API request failed.") from exc
        except Exception as exc:
            logger.error("MiniMax TTS stream failed: %s", safe_error("", exc))
            raise RuntimeError("MiniMax TTS API request failed.") from exc

    async def _audio_play(self, audio_stream: AsyncIterator[str]) -> bytes:
        """解码数据流到 audio 比特流"""
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            if not isinstance(chunk, str):
                logger.warning("MiniMax TTS returned an invalid audio chunk.")
                raise RuntimeError("MiniMax TTS API returned invalid audio data.")

            normalized_chunk = chunk.strip()
            if not normalized_chunk:
                continue

            try:
                chunks.append(bytes.fromhex(normalized_chunk))
            except ValueError as exc:
                logger.warning(
                    "MiniMax TTS returned invalid audio data: %s",
                    safe_error("", exc),
                )
                raise RuntimeError(
                    "MiniMax TTS API returned invalid audio data."
                ) from exc
        return b"".join(chunks)

    async def get_audio(self, text: str) -> str:
        path: str | None = None
        completed = False
        try:
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            path = os.path.join(temp_dir, f"minimax_tts_api_{uuid.uuid4()}.wav")

            audio_stream = self._call_tts_stream(text)
            audio = await self._audio_play(audio_stream)

            if not audio:
                raise RuntimeError("MiniMax TTS API returned empty audio data.")

            with open(path, "wb") as file:
                file.write(audio)

            completed = True
            return path
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("MiniMax TTS generation failed: %s", safe_error("", exc))
            raise RuntimeError("MiniMax TTS audio generation failed.") from exc
        finally:
            if path is not None and not completed:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    logger.warning(
                        "Failed to remove incomplete MiniMax TTS audio: %s",
                        safe_error("", exc),
                    )
