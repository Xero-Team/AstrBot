import asyncio
import uuid
from pathlib import Path
from typing import Protocol, cast

from astrbot import logger
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error

_AUDIO_GENERATION_ERROR = "Genie TTS audio generation failed."
_INITIALIZATION_ERROR = "Genie TTS initialization failed."


class _GenieModule(Protocol):
    def load_character(
        self,
        *,
        character_name: str,
        language: str,
        onnx_model_dir: str,
    ) -> None: ...

    def set_reference_audio(
        self,
        *,
        character_name: str,
        audio_path: str,
        audio_text: str,
        language: str,
    ) -> None: ...

    def tts(
        self,
        *,
        character_name: str,
        text: str,
        save_path: str,
    ) -> None: ...


try:
    import genie_tts as genie_module
except ImportError:
    genie_module = None

genie = cast(_GenieModule | None, genie_module)


@register_provider_adapter(
    "genie_tts",
    "Genie TTS",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class GenieTTSProvider(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        if not genie:
            raise ImportError("Please install genie_tts first.")

        self.character_name = provider_config.get("genie_character_name", "mika")
        language = provider_config.get("genie_language", "Japanese")
        model_dir = provider_config.get("genie_onnx_model_dir", "")
        refer_audio_path = provider_config.get("genie_refer_audio_path", "")
        refer_text = provider_config.get("genie_refer_text", "")

        try:
            genie.load_character(
                character_name=self.character_name,
                language=language,
                onnx_model_dir=model_dir,
            )
            genie.set_reference_audio(
                character_name=self.character_name,
                audio_path=refer_audio_path,
                audio_text=refer_text,
                language=language,
            )
        except Exception as exc:
            logger.error("Genie TTS initialization failed: %s", safe_error("", exc))
            raise RuntimeError(_INITIALIZATION_ERROR) from None

    def support_stream(self) -> bool:
        return True

    @staticmethod
    def _remove_audio(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                "Failed to remove incomplete Genie TTS audio: %s",
                safe_error("", exc),
            )

    def _new_audio_path(self) -> Path:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir / f"genie_tts_{uuid.uuid4()}.wav"

    def _generate(self, text: str, path: Path) -> None:
        assert genie is not None
        genie.tts(
            character_name=self.character_name,
            text=text,
            save_path=str(path),
        )

    async def _generate_audio(self, text: str, path: Path) -> None:
        loop = asyncio.get_running_loop()
        worker = loop.run_in_executor(None, self._generate, text, path)

        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:

            def _cleanup_after_worker(_worker: asyncio.Future[None]) -> None:
                try:
                    _worker.exception()
                except asyncio.CancelledError, Exception:
                    pass
                self._remove_audio(path)

            worker.add_done_callback(_cleanup_after_worker)
            raise

    @staticmethod
    def _has_audio(path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0

    async def get_audio(self, text: str) -> str:
        path: Path | None = None

        try:
            path = self._new_audio_path()
            await self._generate_audio(text, path)
            if not self._has_audio(path):
                raise RuntimeError("Genie TTS did not save audio.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if path is not None:
                self._remove_audio(path)
            logger.error("Genie TTS generation failed: %s", safe_error("", exc))
            raise RuntimeError(_AUDIO_GENERATION_ERROR) from None

        assert path is not None
        return str(path)

    async def get_audio_stream(
        self,
        text_queue: asyncio.Queue[str | None],
        audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None],
    ) -> None:
        while True:
            text = await text_queue.get()
            if text is None:
                await audio_queue.put(None)
                break

            path: Path | None = None
            try:
                path = self._new_audio_path()
                await self._generate_audio(text, path)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if path is not None:
                    self._remove_audio(path)
                logger.error(
                    "Genie TTS stream generation failed: %s",
                    safe_error("", exc),
                )
                continue

            assert path is not None
            try:
                if self._has_audio(path):
                    audio_data = path.read_bytes()

                    # Put (text, bytes) into queue so frontend can display text
                    await audio_queue.put((text, audio_data))
                else:
                    logger.error("Genie TTS stream generation did not produce audio.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Genie TTS stream generation failed: %s",
                    safe_error("", exc),
                )
            finally:
                self._remove_audio(path)
