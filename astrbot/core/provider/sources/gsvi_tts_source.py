import asyncio
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.outbound_http import (
    OutboundRequestPolicy,
    download_to_path,
)

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "GSVI TTS audio generation failed"
_DEFAULT_PORTS = {"http": 80, "https": 443}


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

    async def _download_audio(self, audio_url: str, path: Path) -> None:
        parsed = urlsplit(audio_url)
        scheme = parsed.scheme.lower()
        audio_host = (parsed.hostname or "").lower()
        api = urlsplit(self.api_base)
        api_scheme = api.scheme.lower()
        api_host = (api.hostname or "").lower()
        if scheme not in {"http", "https"} or not audio_host:
            raise ValueError("GSVI TTS returned an invalid audio URL")
        try:
            audio_port = parsed.port or _DEFAULT_PORTS[scheme]
            api_port = api.port or _DEFAULT_PORTS.get(api_scheme)
        except ValueError as exc:
            raise ValueError("GSVI TTS returned an invalid audio URL") from exc

        if (
            api_host
            and scheme == api_scheme
            and audio_host == api_host
            and audio_port == api_port
        ):
            # Only the configured provider origin receives provider headers
            # (including custom authorization). A redirect could leave that
            # origin, so it must not be followed.
            async with aiohttp.ClientSession(
                headers={"User-Agent": "AstrBot", **self.request_headers},
            ) as download_session:
                async with download_session.get(
                    audio_url,
                    ssl=True,
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "[GSVI TTS] Audio download failed with status %s",
                            response.status,
                        )
                        raise RuntimeError(_REQUEST_ERROR)
                    audio = await response.read()
                    if not isinstance(audio, bytes) or not audio:
                        raise ValueError("GSVI TTS returned empty audio")
                    with open(path, "wb") as output:
                        output.write(audio)
            return

        policy = OutboundRequestPolicy(
            allowed_schemes=frozenset({"http", "https"}),
            allowed_hosts=None,
            allowed_ports=None,
            allow_private_network=False,
            max_redirects=0,
            max_url_length=2048,
            max_response_bytes=64 * 1024 * 1024,
            timeout_seconds=60.0,
        )
        await download_to_path(audio_url, path, policy)

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
            post_headers = {**self.request_headers, **headers}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=data, headers=post_headers
                ) as response:
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

                    await self._download_audio(audio_url, path)
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
