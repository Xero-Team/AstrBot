"""TypeSafe System One HTTP adapter: https://docs.typesafe.ai/api."""

import asyncio
import math
from urllib.parse import urlsplit

import aiohttp

from astrbot.core.config.default import JEV_SYSTEMONE_TEMPLATE
from astrbot.core.typed_decision import (
    ClassifierInput,
    ClassifierQuestion,
    ClassifierResult,
)
from astrbot.core.utils.proxy_route import (
    aiohttp_request_proxy,
    create_aiohttp_session,
)

from ..entities import ProviderType
from ..provider import ClassifierProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "jev_systemone",
    "JEV System One 分类器适配器",
    provider_type=ProviderType.CLASSIFIER,
    default_config_tmpl=JEV_SYSTEMONE_TEMPLATE,
    provider_display_name="JEV System One",
)
class JevSystemOneProvider(ClassifierProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        base = str(provider_config.get("api_base", "https://api.typesafe.ai")).rstrip(
            "/"
        )
        url = urlsplit(base)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "JEV requires an HTTPS API base without credentials or query"
            )
        self.url = f"{base}/v1/systemone"
        self.timeout = float(provider_config.get("timeout", 20))
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("JEV timeout must be positive and finite")
        self.set_model(provider_config.get("model") or "jev-latest")
        keys = provider_config.get("key", [])
        if (
            not isinstance(keys, list)
            or not keys
            or not isinstance(keys[0], str)
            or not keys[0].strip()
        ):
            raise ValueError("JEV requires an API key")
        self.client = create_aiohttp_session(
            headers={
                **self.request_headers,
                "Authorization": f"Bearer {keys[0]}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )

    async def evaluate(
        self, state: ClassifierInput, questions: dict[str, ClassifierQuestion]
    ) -> ClassifierResult:
        if not questions:
            raise ValueError("JEV requires at least one typed question")
        payload = {
            "state": state,
            "model": self.get_model(),
            "questions": {
                name: question.model_dump(exclude_none=True)
                for name, question in questions.items()
            },
        }
        try:
            # Bound the whole operation, including backoff, not only each attempt.
            async with asyncio.timeout(self.timeout):
                for attempt in range(3):
                    async with self.client.post(
                        self.url,
                        json=payload,
                        proxy=aiohttp_request_proxy(self.get_network_route()),
                        allow_redirects=False,
                    ) as response:
                        if response.status in (429, 529) and attempt < 2:
                            retry = True
                        elif response.status != 200:
                            # Never include remote bodies, request headers or URLs.
                            raise RuntimeError(
                                f"JEV HTTP request failed ({response.status})"
                            )
                        else:
                            result = ClassifierResult.model_validate(
                                await response.json()
                            )
                            result.validate_questions(questions)
                            return result
                    if retry:
                        await asyncio.sleep(0.5 * 2**attempt)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise TimeoutError("JEV evaluation timed out") from None
        except Exception:
            raise RuntimeError("JEV evaluation failed") from None
        raise RuntimeError("JEV evaluation failed")

    async def terminate(self) -> None:
        """Close the HTTP session owned by this adapter."""
        await self.client.close()
