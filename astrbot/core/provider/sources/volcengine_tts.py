import asyncio
import base64
import json
import uuid
from pathlib import Path

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

_AUDIO_GENERATION_ERROR = "Volcengine TTS audio generation failed"


@register_provider_adapter(
    "volcengine_tts",
    "火山引擎 TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderVolcengineTTS(TTSProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.api_key = provider_config.get("api_key", "")
        self.appid = provider_config.get("appid", "")
        self.cluster = provider_config.get("volcengine_cluster", "")
        self.voice_type = provider_config.get("volcengine_voice_type", "")
        self.speed_ratio = provider_config.get("volcengine_speed_ratio", 1.0)
        self.api_base = provider_config.get(
            "api_base",
            "https://openspeech.bytedance.com/api/v1/tts",
        )
        self.timeout = provider_config.get("timeout", 20)

    def _build_request_payload(self, text: str) -> dict:
        return {
            "app": {
                "appid": self.appid,
                "token": self.api_key,
                "cluster": self.cluster,
            },
            "user": {"uid": str(uuid.uuid4())},
            "audio": {
                "voice_type": self.voice_type,
                "encoding": "mp3",
                "speed_ratio": self.speed_ratio,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson",
            },
        }

    async def get_audio(self, text: str) -> str:
        """异步方法获取语音文件路径"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer; {self.api_key}",
        }
        payload = self._build_request_payload(text)
        file_path: Path | None = None
        completed = False

        try:
            async with (
                aiohttp.ClientSession(headers=self.request_headers) as session,
                session.post(
                    self.api_base,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=self.timeout,
                ) as response,
            ):
                response_text = await response.text()
                if response.status != 200:
                    raise RuntimeError(f"Volcengine TTS HTTP status {response.status}")

                resp_data = json.loads(response_text)
                if not isinstance(resp_data, dict):
                    raise ValueError("Volcengine TTS response must be an object")
                encoded_audio = resp_data.get("data")
                if not isinstance(encoded_audio, str):
                    raise ValueError("Volcengine TTS response did not contain audio")

                audio_data = base64.b64decode(encoded_audio, validate=True)
                if not audio_data:
                    raise ValueError("Volcengine TTS returned empty audio")

                temp_dir = Path(get_astrbot_temp_path())
                temp_dir.mkdir(parents=True, exist_ok=True)
                file_path = temp_dir / f"volcengine_tts_{uuid.uuid4()}.mp3"
                file_path.write_bytes(audio_data)
                completed = True
                return str(file_path)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Volcengine TTS generation failed: %s", safe_error("", exc))
            raise RuntimeError(_AUDIO_GENERATION_ERROR) from None
        finally:
            if file_path is not None and not completed:
                try:
                    file_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning(
                        "Failed to remove incomplete Volcengine TTS audio: %s",
                        safe_error("", exc),
                    )
