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

_REQUEST_ERROR = "GSV TTS request failed"
_INITIALIZATION_ERROR = "GSV TTS initialization failed"
_AUDIO_ERROR = "GSV TTS audio generation failed"


@register_provider_adapter(
    provider_type_name="gsv_tts_selfhost",
    desc="GPT-SoVITS TTS(本地加载)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderGSVTTS(TTSProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)

        self.api_base = provider_config.get("api_base", "http://127.0.0.1:9880").rstrip(
            "/",
        )
        self.gpt_weights_path: str = provider_config.get("gpt_weights_path", "")
        self.sovits_weights_path: str = provider_config.get("sovits_weights_path", "")

        # TTS 请求的默认参数，移除前缀gsv_
        self.default_params: dict = {
            key.removeprefix("gsv_"): str(value).lower()
            for key, value in provider_config.get("gsv_default_parms", {}).items()
        }
        self.timeout = provider_config.get("timeout", 60)
        self._session: aiohttp.ClientSession | None = None

    async def initialize(self) -> None:
        """异步初始化：在 ProviderManager 中被调用"""
        session = aiohttp.ClientSession(
            headers=self.request_headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self._session = session
        try:
            await self._set_model_weights()
            logger.info("[GSV TTS] 初始化完成")
        except asyncio.CancelledError:
            self._session = None
            await self._close_session(session)
            raise
        except Exception as exc:
            self._session = None
            await self._close_session(session)
            logger.error("[GSV TTS] Initialization failed: %s", safe_error("", exc))
            raise RuntimeError(_INITIALIZATION_ERROR) from None

    async def _close_session(self, session: aiohttp.ClientSession) -> None:
        if getattr(session, "closed", False):
            return
        try:
            await session.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[GSV TTS] Session close failed: %s", safe_error("", exc))

    def get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            raise RuntimeError(
                "[GSV TTS] Provider HTTP session is not ready or closed.",
            )
        return self._session

    async def _make_request(
        self,
        endpoint: str,
        params=None,
        retries: int = 3,
    ) -> bytes | None:
        """发起请求"""
        if retries <= 0:
            raise ValueError("retries must be greater than zero")

        for attempt in range(retries):
            try:
                async with self.get_session().get(endpoint, params=params) as response:
                    if response.status != 200:
                        raise RuntimeError(
                            f"GSV TTS HTTP request failed with status {response.status}"
                        )
                    return await response.read()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt < retries - 1:
                    logger.warning(
                        "[GSV TTS] Request attempt %d failed: %s",
                        attempt + 1,
                        safe_error("", exc),
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error(
                        "[GSV TTS] Request failed after %d attempts: %s",
                        retries,
                        safe_error("", exc),
                    )
                    raise RuntimeError(_REQUEST_ERROR) from None

        raise RuntimeError(_REQUEST_ERROR)

    async def _set_model_weights(self) -> None:
        """设置模型路径"""
        if self.gpt_weights_path:
            await self._make_request(
                f"{self.api_base}/set_gpt_weights",
                {"weights_path": self.gpt_weights_path},
            )
            logger.info("[GSV TTS] GPT model weights configured")
        else:
            logger.info("[GSV TTS] GPT 模型路径未配置，将使用内置 GPT 模型")

        if self.sovits_weights_path:
            await self._make_request(
                f"{self.api_base}/set_sovits_weights",
                {"weights_path": self.sovits_weights_path},
            )
            logger.info("[GSV TTS] SoVITS model weights configured")
        else:
            logger.info("[GSV TTS] SoVITS 模型路径未配置，将使用内置 SoVITS 模型")

    async def get_audio(self, text: str) -> str:
        """实现 TTS 核心方法，根据文本内容自动切换情绪"""
        if not text.strip():
            raise ValueError("[GSV TTS] TTS 文本不能为空")

        endpoint = f"{self.api_base}/tts"

        params = self.build_synthesis_params(text)

        path = Path(get_astrbot_temp_path()) / f"gsv_tts_{uuid.uuid4().hex}.wav"
        completed = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            result = await self._make_request(endpoint, params)
            if not isinstance(result, bytes) or not result:
                raise ValueError("GSV TTS returned empty audio")
            with open(path, "wb") as output:
                output.write(result)
            completed = True
            return str(path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[GSV TTS] Audio generation failed: %s", safe_error("", exc))
            raise RuntimeError(_AUDIO_ERROR) from None
        finally:
            if not completed:
                path.unlink(missing_ok=True)

    def build_synthesis_params(self, text: str) -> dict:
        """构建语音合成所需的参数字典。

        当前仅包含默认参数 + 文本，未来可在此基础上动态添加如情绪、角色等语义控制字段。
        """
        params = self.default_params.copy()
        params["text"] = text
        # TODO: 在此处添加情绪分析，例如 params["emotion"] = detect_emotion(text)
        return params

    async def terminate(self) -> None:
        """终止释放资源：在 ProviderManager 中被调用"""
        session = self._session
        self._session = None
        if session is None:
            return
        await self._close_session(session)
