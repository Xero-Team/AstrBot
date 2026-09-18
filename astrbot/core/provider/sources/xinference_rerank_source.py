import asyncio
from collections.abc import Mapping
from typing import Any, cast

from xinference_client.client.restful.async_restful_client import (
    AsyncClient as Client,
)
from xinference_client.client.restful.async_restful_client import (
    AsyncRESTfulRerankModelHandle,
)

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from ..entities import ProviderType, RerankResult
from ..provider import RerankProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "xinference_rerank",
    "Xinference Rerank 适配器",
    provider_type=ProviderType.RERANK,
)
class XinferenceRerankProvider(RerankProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.base_url = provider_config.get("rerank_api_base", "http://127.0.0.1:8000")
        self.base_url = self.base_url.rstrip("/")
        self.timeout = provider_config.get("timeout", 20)
        self.model_name = provider_config.get("rerank_model", "BAAI/bge-reranker-base")
        self.api_key = provider_config.get("rerank_api_key")
        self.launch_model_if_not_running = provider_config.get(
            "launch_model_if_not_running",
            False,
        )
        self.client = None
        self.model: AsyncRESTfulRerankModelHandle | None = None
        self.model_uid = None

    async def initialize(self) -> None:
        try:
            await self.terminate()
            if self.api_key:
                logger.info("Xinference rerank authentication is configured")
                self.client = Client(self.base_url, api_key=self.api_key)
            else:
                logger.info("Xinference rerank does not use API authentication")
                self.client = Client(self.base_url)
            self.client._headers.update(self.request_headers)

            running_models = await self.client.list_models()
            if not isinstance(running_models, Mapping):
                raise TypeError("Xinference model list must be an object")
            for uid, model_spec in running_models.items():
                if not isinstance(model_spec, Mapping):
                    logger.warning("Xinference returned an invalid model entry")
                    continue
                if model_spec.get("model_name") == self.model_name:
                    logger.info("Xinference rerank model is already running")
                    self.model_uid = uid
                    break

            if self.model_uid is None:
                if self.launch_model_if_not_running:
                    logger.info("Launching Xinference rerank model")
                    self.model_uid = await self.client.launch_model(
                        model_name=self.model_name,
                        model_type="rerank",
                    )
                    logger.info("Model launched.")
                else:
                    logger.warning(
                        "Xinference rerank model is not running and auto-launch is disabled"
                    )
                    return

            if self.model_uid:
                self.model = cast(
                    AsyncRESTfulRerankModelHandle,
                    await self.client.get_model(self.model_uid),
                )

        except asyncio.CancelledError:
            await self.terminate()
            raise
        except Exception as exc:
            logger.error(
                "Xinference rerank initialization failed: %s", safe_error("", exc)
            )
            await self.terminate()

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not self.model:
            logger.error("Xinference rerank model is not initialized.")
            return []
        try:
            response = await self.model.rerank(
                cast("list[str | dict[str, Any]]", documents),
                query,
                top_n,
            )
            if not isinstance(response, Mapping):
                logger.warning("Xinference rerank returned an invalid response")
                return []
            results = response.get("results", [])
            if not isinstance(results, list):
                logger.warning("Xinference rerank returned invalid result data")
                return []

            if not results:
                logger.warning("Xinference rerank returned no results")

            rerank_results: list[RerankResult] = []
            for idx, result in enumerate(results):
                try:
                    if not isinstance(result, Mapping):
                        raise TypeError("rerank result must be an object")
                    rerank_results.append(
                        RerankResult(
                            index=int(result.get("index", idx)),
                            relevance_score=float(result["relevance_score"]),
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "Xinference rerank result parsing failed: %s",
                        safe_error("", exc),
                    )

            return rerank_results
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Xinference rerank failed: %s", safe_error("", exc))
            return []

    async def terminate(self) -> None:
        """关闭客户端会话"""
        client = self.client
        self.client = None
        self.model = None
        self.model_uid = None
        if client is None:
            return

        logger.info("Closing Xinference rerank client")
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Xinference rerank client close failed: %s", safe_error("", exc)
            )
