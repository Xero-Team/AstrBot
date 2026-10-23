import asyncio
import importlib
from collections.abc import Mapping
from functools import partial
from typing import Any

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.media_utils import MediaResolver

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_whisper_selfhost",
    "OpenAI Whisper 模型部署",
    provider_type=ProviderType.SPEECH_TO_TEXT,
)
class ProviderOpenAIWhisperSelfHost(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config["model"])
        self.device = str(provider_config.get("whisper_device", "cpu")).strip().lower()
        self.model: Any | None = None
        self._executor_futures: set[asyncio.Future[Any]] = set()

    def _resolve_device(self) -> str:
        if self.device == "mps":
            try:
                torch = importlib.import_module("torch")
            except ImportError:
                logger.warning(
                    "Whisper 配置为使用 MPS，但 torch 未安装，将回退到 CPU。"
                )
                return "cpu"

            mps_backend = getattr(torch.backends, "mps", None)
            if mps_backend and mps_backend.is_available():
                return "mps"
            logger.warning("Whisper 已配置为使用 MPS，但当前环境不可用，将回退到 CPU。")
            return "cpu"
        if self.device != "cpu":
            logger.warning("Whisper configured with an unknown device; using CPU.")
        return "cpu"

    async def _run_in_executor(self, callback, *args):
        """Run blocking model work and track the submitted future for shutdown."""
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, callback, *args)
        self._executor_futures.add(future)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            future.cancel()
            # A running thread cannot be interrupted; wait for it so callers do
            # not delete a temporary audio file the worker still reads.
            await asyncio.shield(future)
            raise
        finally:
            self._executor_futures.discard(future)

    async def initialize(self) -> None:
        device = self._resolve_device()
        logger.info("下载或者加载 Whisper 模型中，这可能需要一些时间 ...")
        try:
            whisper_module = importlib.import_module("whisper")
        except ImportError as exc:
            logger.error("Failed to import openai-whisper: %s", safe_error("", exc))
            raise RuntimeError("openai-whisper is not installed") from None
        except Exception as exc:
            logger.error(
                "Whisper model initialization failed: %s",
                safe_error("", exc),
            )
            raise RuntimeError("Whisper model initialization failed.") from None

        try:
            model = await self._run_in_executor(
                partial(whisper_module.load_model, self.model_name, device=device),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Whisper model initialization failed: %s",
                safe_error("", exc),
            )
            raise RuntimeError("Whisper model initialization failed.") from None

        if model is None:
            logger.error("Whisper model initialization returned no model.")
            raise RuntimeError("Whisper model initialization failed.")

        self.model = model
        logger.info("Whisper 模型加载完成。device=%s", device)

    async def get_text(self, audio_url: str) -> str:
        model = self.model
        if model is None:
            raise RuntimeError("Whisper model is not initialized.")

        try:
            async with MediaResolver(
                audio_url,
                media_type="audio",
                default_suffix=".wav",
            ).as_path(target_format="wav") as audio:
                result = await self._run_in_executor(
                    model.transcribe,
                    str(audio.path),
                )

            if not isinstance(result, Mapping):
                logger.warning("Whisper returned an invalid transcription response.")
                raise ValueError("invalid transcription response")

            text = result.get("text")
            if not isinstance(text, str):
                logger.warning("Whisper returned an invalid transcription response.")
                raise ValueError("invalid transcription response")
            return text
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Whisper transcription failed: %s", safe_error("", exc))
            raise RuntimeError("Whisper transcription failed.") from None

    async def terminate(self) -> None:
        """Cancel pending model work and release the loaded model reference."""
        pending = tuple(self._executor_futures)
        for future in pending:
            future.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._executor_futures.clear()
        self.model = None
