import asyncio
import uuid
from pathlib import Path

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "GSVI TTS audio generation failed"


@register_provider_adapter(
    "gsvi_tts_api",
    "GSVI TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGSVITTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.api_base = provider_config.get("api_base", "http://127.0.0.1:8000")
        self.api_base = self.api_base.removesuffix("/")
        self.version = provider_config.get("version", "v4")
        self.character = provider_config.get("character")
        self.prompt_text_lang = provider_config.get("prompt_text_lang", "中文")
        self.emotion = provider_config.get("emotion", "默认")
        self.text_lang = provider_config.get("text_lang", "中文")

    async def get_audio(self, text: str) -> str:
        path = Path(get_astrbot_temp_path()) / f"gsvi_tts_{uuid.uuid4()}.wav"
        url = f"{self.api_base}/infer_single"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "dl_url": self.api_base,
            "version": self.version,
            "model_name": self.character,
            "prompt_text_lang": self.prompt_text_lang,
            "emotion": self.emotion,
            "text": text,
            "text_lang": self.text_lang,
        }

        completed = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiohttp.ClientSession(headers=self.request_headers) as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status != 200:
                        logger.error(
                            "[GSVI TTS] Synthesis request failed with status %s",
                            response.status,
                        )
                        raise RuntimeError(_REQUEST_ERROR)
                    response_data = await response.json()
                    if not isinstance(response_data, dict):
                        raise ValueError("GSVI TTS returned an invalid response")
                    if response_data.get("msg") != "合成成功":
                        raise ValueError("GSVI TTS did not confirm synthesis")
                    audio_url = response_data.get("audio_url")
                    if not isinstance(audio_url, str) or not audio_url:
                        raise ValueError("GSVI TTS returned no audio URL")

                    async with session.get(audio_url) as audio_response:
                        if audio_response.status != 200:
                            logger.error(
                                "[GSVI TTS] Audio download failed with status %s",
                                audio_response.status,
                            )
                            raise RuntimeError(_REQUEST_ERROR)
                        audio = await audio_response.read()
                        if not isinstance(audio, bytes) or not audio:
                            raise ValueError("GSVI TTS returned empty audio")
                        with open(path, "wb") as output:
                            output.write(audio)
            completed = True
            return str(path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[GSVI TTS] Request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        finally:
            if not completed:
                path.unlink(missing_ok=True)
