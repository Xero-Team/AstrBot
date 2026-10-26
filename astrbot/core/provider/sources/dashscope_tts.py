import asyncio
import base64
import uuid
from pathlib import Path

import aiohttp
import dashscope
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

try:
    from dashscope.aigc.multimodal_conversation import MultiModalConversation
except (
    ImportError
):  # pragma: no cover - older dashscope versions without Qwen TTS support
    MultiModalConversation = None

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter

_REQUEST_ERROR = "Dashscope TTS audio generation failed"
MAX_AUDIO_DOWNLOAD_BYTES = 50 * 1024 * 1024


@register_provider_adapter(
    "dashscope_tts",
    "Dashscope TTS API",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderDashscopeTTSAPI(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key: str = provider_config.get("api_key", "")
        self.voice: str = provider_config.get("dashscope_tts_voice", "") or ""
        self.set_model(provider_config["model"])
        self.timeout_ms = float(provider_config.get("timeout", 20)) * 1000

    async def get_audio(self, text: str) -> str:
        model = self.get_model()
        if not model:
            raise RuntimeError("Dashscope TTS model is not configured.")

        path: Path | None = None
        completed = False
        try:
            if self._is_qwen_tts_model(model):
                audio_bytes, ext = await self._synthesize_with_qwen_tts(model, text)
            else:
                audio_bytes, ext = await self._synthesize_with_cosyvoice(model, text)

            if not isinstance(audio_bytes, bytes) or not audio_bytes:
                raise ValueError("Dashscope TTS returned empty audio")

            temp_dir = Path(get_astrbot_temp_path())
            temp_dir.mkdir(parents=True, exist_ok=True)
            path = temp_dir / f"dashscope_tts_{uuid.uuid4()}{ext}"
            with open(path, "wb") as output:
                output.write(audio_bytes)
            completed = True
            return str(path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[Dashscope TTS] Request failed: %s", safe_error("", exc))
            raise RuntimeError(_REQUEST_ERROR) from None
        finally:
            if path is not None and not completed:
                path.unlink(missing_ok=True)

    def _resolve_voice(self, model: str) -> str:
        """Return a voice that belongs to the selected TTS model family."""
        voice = self.voice.strip()
        if self._is_qwen_tts_model(model):
            if not voice:
                logger.warning(
                    "No voice specified for Qwen TTS model, using default 'Cherry'.",
                )
                return "Cherry"
            if voice == "loongstella":
                logger.warning(
                    "The CosyVoice default voice 'loongstella' is not valid for "
                    "Qwen TTS; using default 'Cherry'.",
                )
                return "Cherry"
            return voice
        return voice or "loongstella"

    def _call_qwen_tts(self, model: str, text: str):
        if MultiModalConversation is None:
            raise RuntimeError(
                "dashscope SDK missing MultiModalConversation. Please upgrade the dashscope package to use Qwen TTS models.",
            )

        kwargs = {
            "model": model,
            "headers": self.request_headers.copy(),
            "messages": None,
            "api_key": self.chosen_api_key,
            "voice": self._resolve_voice(model),
            "text": text,
        }
        return MultiModalConversation.call(**kwargs)

    async def _synthesize_with_qwen_tts(
        self,
        model: str,
        text: str,
    ) -> tuple[bytes | None, str]:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, self._call_qwen_tts, model, text)
        audio_bytes = await self._extract_audio_from_response(response)
        if not audio_bytes:
            raise ValueError("Dashscope Qwen TTS returned no audio")
        ext = ".wav"
        return audio_bytes, ext

    async def _extract_audio_from_response(self, response) -> bytes | None:
        output = getattr(response, "output", None)
        audio_obj = getattr(output, "audio", None) if output is not None else None
        if not audio_obj:
            return None

        data_b64 = getattr(audio_obj, "data", None)
        if data_b64:
            try:
                audio = base64.b64decode(data_b64, validate=True)
                return audio or None
            except ValueError, TypeError:
                logger.warning("[Dashscope TTS] Invalid base64 audio data")
                return None

        url = getattr(audio_obj, "url", None)
        if url:
            return await self._download_audio_from_url(url)
        return None

    async def _download_audio_from_url(self, url: str) -> bytes | None:
        if not url:
            return None
        timeout = max(self.timeout_ms / 1000, 1) if self.timeout_ms else 20
        try:
            async with (
                aiohttp.ClientSession(
                    headers={"User-Agent": self.request_headers["User-Agent"]}
                ) as session,
                session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response,
            ):
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if "audio" not in content_type.lower():
                    logger.warning(
                        "[Dashscope TTS] Audio download returned unexpected content type: %s",
                        content_type,
                    )
                    return None
                data = bytearray()
                while True:
                    chunk = await response.content.read(64 * 1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_AUDIO_DOWNLOAD_BYTES:
                        logger.warning(
                            "[Dashscope TTS] Audio download exceeded size limit"
                        )
                        return None
                return bytes(data)
        except asyncio.CancelledError:
            raise
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            logger.warning(
                "[Dashscope TTS] Audio download failed: %s", safe_error("", exc)
            )
            return None

    async def _synthesize_with_cosyvoice(
        self,
        model: str,
        text: str,
    ) -> tuple[bytes | None, str]:
        # The SDK copies ``dashscope.api_key`` into the synthesizer instance at
        # construction time. Swap it only for that synchronous window so several
        # providers can keep different credentials without leaving a global key.
        previous_api_key = dashscope.api_key
        dashscope.api_key = self.chosen_api_key
        try:
            synthesizer = SpeechSynthesizer(
                headers={
                    name.lower(): value for name, value in self.request_headers.items()
                },
                model=model,
                voice=self._resolve_voice(model),
                format=AudioFormat.WAV_24000HZ_MONO_16BIT,
            )
        finally:
            dashscope.api_key = previous_api_key
        loop = asyncio.get_running_loop()
        audio_bytes = await loop.run_in_executor(
            None,
            synthesizer.call,
            text,
            self.timeout_ms,
        )
        if not audio_bytes:
            raise ValueError("Dashscope CosyVoice returned no audio")
        return audio_bytes, ".wav"

    def _is_qwen_tts_model(self, model: str) -> bool:
        model_lower = model.lower()
        return "tts" in model_lower and model_lower.startswith("qwen")
