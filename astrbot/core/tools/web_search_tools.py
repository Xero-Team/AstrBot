import asyncio
import json
import uuid
from dataclasses import dataclass as std_dataclass
from dataclasses import field
from urllib.parse import parse_qsl, quote, urljoin, urlparse

import aiohttp
from pydantic import Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.registry import builtin_tool
from astrbot.core.utils.outbound_http import (
    searxng_search_policy,
    validate_outbound_url,
)

WEB_SEARCH_TOOL_NAMES = [
    "web_search",
    "web_fetch",
    "web_search_serpapi",
    "news_search_serpapi",
    "image_search_serpapi",
    "finance_search_serpapi",
    "scholar_search_serpapi",
]
_WEB_SEARCH_ENABLED_CONFIG = {"provider_settings.web_search": True}
_DEFAULT_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10, sock_read=20)


def _client_session() -> aiohttp.ClientSession:
    from astrbot.core.utils.proxy_route import create_aiohttp_session

    return create_aiohttp_session()


def _request_kwargs() -> dict:
    from astrbot.core.utils.proxy_route import current_aiohttp_proxy

    kwargs: dict = {"timeout": _DEFAULT_HTTP_TIMEOUT}
    proxy = current_aiohttp_proxy()
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def _post(session, url: str, *, json: dict, headers: dict):
    return session.post(url, json=json, headers=headers, **_request_kwargs())


def _get(session, url: str, *, params: dict, headers: dict):
    return session.get(url, params=params, headers=headers, **_request_kwargs())


@std_dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    favicon: str | None = None


@std_dataclass
class _KeyRotator:
    """Concurrency-safe round-robin API key rotator.

    Each call returns the current key and advances the index. Search functions
    combine this with failover loops to retry with the next configured key.
    """

    setting_name: str
    provider_name: str
    index: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self, provider_settings: dict) -> str:
        """Return the current key and advance the round-robin index.

        Args:
            provider_settings: Provider settings containing API key lists.

        Returns:
            The API key selected for this call.

        Raises:
            ValueError: If the configured key list is empty or missing.
        """
        keys = provider_settings.get(self.setting_name, [])
        if not keys:
            raise ValueError(
                f"Error: {self.provider_name} API key is not configured in AstrBot."
            )

        async with self.lock:
            # Keep the index valid if runtime config reloads shrink the key list.
            self.index = self.index % len(keys)
            key = keys[self.index]
            self.index = (self.index + 1) % len(keys)
            return key


# Retry with the next API key when these HTTP statuses indicate key-specific
# auth, quota, or rate-limit failures.
# 401 - Unauthorized, usually invalid or expired key.
# 403 - Forbidden, usually disabled key.
# 429 - Rate limited.
# 432 - Tavily quota exceeded.
_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({401, 403, 429, 432})
_ANYSEARCH_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({401, 402, 403, 429})


@std_dataclass
class _WebSearchRuntimeState:
    """API-key rotation state owned by one function-tool manager."""

    rotators: dict[str, _KeyRotator] = field(default_factory=dict)

    def get_rotator(self, setting_name: str, provider_name: str) -> _KeyRotator:
        rotator = self.rotators.get(setting_name)
        if rotator is None:
            rotator = _KeyRotator(setting_name, provider_name)
            self.rotators[setting_name] = rotator
        return rotator


class _RuntimeProviderSettings(dict):
    """A configuration snapshot with runtime-owned web-search state."""

    __slots__ = ("web_search_state",)

    def __init__(self, values: dict, state: _WebSearchRuntimeState) -> None:
        super().__init__(values)
        self.web_search_state = state


def _runtime_provider_settings(
    execution_context,
    provider_settings: dict,
) -> dict:
    get_tool_manager = getattr(execution_context, "get_llm_tool_manager", None)
    if not callable(get_tool_manager):
        return provider_settings

    tool_manager = get_tool_manager()
    get_or_create_state = getattr(tool_manager, "get_or_create_runtime_state", None)
    if not callable(get_or_create_state):
        return provider_settings

    state = get_or_create_state("web_search_key_rotators", _WebSearchRuntimeState)
    if not isinstance(state, _WebSearchRuntimeState):
        raise TypeError("Invalid runtime state for web-search key rotation")
    return _RuntimeProviderSettings(provider_settings, state)


def _get_key_rotator(
    provider_settings: dict,
    setting_name: str,
    provider_name: str,
) -> _KeyRotator:
    state = getattr(provider_settings, "web_search_state", None)
    if not isinstance(state, _WebSearchRuntimeState):
        state = _WebSearchRuntimeState()
    return state.get_rotator(setting_name, provider_name)


def _get_runtime(context) -> tuple[dict, dict, str]:
    agent_ctx = context.context
    event = agent_ctx.event
    execution_context = agent_ctx.context
    cfg = execution_context.get_config(umo=event.unified_msg_origin)
    provider_settings = cfg.get("provider_settings", {})
    return (
        cfg,
        _runtime_provider_settings(execution_context, provider_settings),
        event.unified_msg_origin,
    )


async def _tavily_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Tavily Search API with API key failover.

    Args:
        provider_settings: Provider settings containing Tavily API keys.
        payload: Request payload for the Tavily search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If Tavily API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_tavily_key", [])
    if not keys:
        raise ValueError("Error: Tavily API key is not configured in AstrBot.")

    # Retry key-specific failures with the next key, but fail fast for
    # non-retryable errors such as server-side 5xx responses.
    last_error = None
    for _ in range(len(keys)):
        tavily_key = await _get_key_rotator(
            provider_settings,
            "websearch_tavily_key",
            "Tavily",
        ).get(provider_settings)
        header = {
            "Authorization": f"Bearer {tavily_key}",
            "Content-Type": "application/json",
        }
        async with _client_session() as session:
            async with _post(
                session,
                "https://api.tavily.com/search",
                json=payload,
                headers=header,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return [
                        SearchResult(
                            title=item.get("title"),
                            url=item.get("url"),
                            snippet=item.get("content"),
                            favicon=item.get("favicon"),
                        )
                        for item in data.get("results", [])
                    ]
                reason = await response.text()
                # Retryable errors are saved so the final failure is meaningful.
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Tavily web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Tavily web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Tavily web search failed with all configured keys.")


async def _tavily_extract(provider_settings: dict, payload: dict) -> list[dict]:
    """Call the Tavily Extract API with API key failover.

    Args:
        provider_settings: Provider settings containing Tavily API keys.
        payload: Request payload for the Tavily extract endpoint.

    Returns:
        Raw Tavily extraction results.

    Raises:
        ValueError: If Tavily API keys are not configured or no results are
            returned.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_tavily_key", [])
    if not keys:
        raise ValueError("Error: Tavily API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        tavily_key = await _get_key_rotator(
            provider_settings,
            "websearch_tavily_key",
            "Tavily",
        ).get(provider_settings)
        header = {
            "Authorization": f"Bearer {tavily_key}",
            "Content-Type": "application/json",
        }
        async with _client_session() as session:
            async with _post(
                session,
                "https://api.tavily.com/extract",
                json=payload,
                headers=header,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results: list[dict] = data.get("results", [])
                    if not results:
                        raise ValueError(
                            "Error: Tavily web searcher does not return any results."
                        )
                    return results
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Tavily web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Tavily web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Tavily web extract failed with all configured keys.")


async def _bocha_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the BoCha Search API with API key failover.

    Args:
        provider_settings: Provider settings containing BoCha API keys.
        payload: Request payload for the BoCha search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If BoCha API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_bocha_key", [])
    if not keys:
        raise ValueError("Error: BoCha API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        bocha_key = await _get_key_rotator(
            provider_settings,
            "websearch_bocha_key",
            "BoCha",
        ).get(provider_settings)
        header = {
            "Authorization": f"Bearer {bocha_key}",
            "Content-Type": "application/json",
            # Explicitly disable brotli encoding to avoid aiohttp >= 3.13.3
            # decompression incompatibility.
            # See: https://github.com/aio-libs/aiohttp/issues/11898
            "Accept-Encoding": "gzip, deflate",
        }
        async with _client_session() as session:
            async with _post(
                session,
                "https://api.bochaai.com/v1/web-search",
                json=payload,
                headers=header,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    rows = data["data"]["webPages"]["value"]
                    return [
                        SearchResult(
                            title=item.get("name"),
                            url=item.get("url"),
                            snippet=item.get("snippet"),
                            favicon=item.get("siteIcon"),
                        )
                        for item in rows
                    ]
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"BoCha web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"BoCha web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("BoCha web search failed with all configured keys.")


async def _brave_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Brave Search API with API key failover.

    Args:
        provider_settings: Provider settings containing Brave API keys.
        payload: Request payload for the Brave search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If Brave API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_brave_key", [])
    if not keys:
        raise ValueError("Error: Brave API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        brave_key = await _get_key_rotator(
            provider_settings,
            "websearch_brave_key",
            "Brave",
        ).get(provider_settings)
        header = {
            "Accept": "application/json",
            "X-Subscription-Token": brave_key,
        }
        async with _client_session() as session:
            async with _get(
                session,
                "https://api.search.brave.com/res/v1/web/search",
                params=payload,
                headers=header,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    rows = data.get("web", {}).get("results", [])
                    return [
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            snippet=item.get("description", ""),
                        )
                        for item in rows
                    ]
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Brave web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Brave web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Brave web search failed with all configured keys.")


async def _firecrawl_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Firecrawl Search API with API key failover.

    Args:
        provider_settings: Provider settings containing Firecrawl API keys.
        payload: Request payload for the Firecrawl search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If Firecrawl API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_firecrawl_key", [])
    if not keys:
        raise ValueError("Error: Firecrawl API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        firecrawl_key = await _get_key_rotator(
            provider_settings,
            "websearch_firecrawl_key",
            "Firecrawl",
        ).get(provider_settings)
        header = {
            "Authorization": f"Bearer {firecrawl_key}",
            "Content-Type": "application/json",
        }
        async with _client_session() as session:
            async with _post(
                session,
                "https://api.firecrawl.dev/v2/search",
                json=payload,
                headers=header,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    rows = data.get("data", [])
                    if isinstance(rows, dict):
                        rows = rows.get("web", [])
                    return [
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            snippet=(
                                item.get("description")
                                or item.get("snippet")
                                or item.get("markdown")
                                or ""
                            ),
                        )
                        for item in rows
                        if item.get("url")
                    ]
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Firecrawl web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Firecrawl web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Firecrawl web search failed with all configured keys.")


async def _firecrawl_scrape(provider_settings: dict, payload: dict) -> dict:
    """Call the Firecrawl Scrape API with API key failover.

    Args:
        provider_settings: Provider settings containing Firecrawl API keys.
        payload: Request payload for the Firecrawl scrape endpoint.

    Returns:
        Raw Firecrawl scrape result data.

    Raises:
        ValueError: If Firecrawl API keys are not configured or no result data
            is returned.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_firecrawl_key", [])
    if not keys:
        raise ValueError("Error: Firecrawl API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        firecrawl_key = await _get_key_rotator(
            provider_settings,
            "websearch_firecrawl_key",
            "Firecrawl",
        ).get(provider_settings)
        header = {
            "Authorization": f"Bearer {firecrawl_key}",
            "Content-Type": "application/json",
        }
        async with _client_session() as session:
            async with _post(
                session,
                "https://api.firecrawl.dev/v2/scrape",
                json=payload,
                headers=header,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get("data", {})
                    if not result:
                        raise ValueError(
                            "Error: Firecrawl web scraper does not return any results."
                        )
                    return result
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Firecrawl web scraper failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Firecrawl web scraper failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Firecrawl web scraper failed with all configured keys.")


async def _exa_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    exa_key = await _get_key_rotator(
        provider_settings,
        "websearch_exa_key",
        "Exa",
    ).get(provider_settings)
    headers = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with _client_session() as session:
        async with _post(
            session,
            "https://api.exa.ai/search",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Exa web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(
                        item.get("text")
                        or (item.get("highlights") or [""])[0]
                        or item.get("summary", "")
                    ),
                )
                for item in data.get("results", [])
                if item.get("url")
            ]


async def _exa_get_contents(
    provider_settings: dict,
    payload: dict,
) -> list[dict]:
    exa_key = await _get_key_rotator(
        provider_settings,
        "websearch_exa_key",
        "Exa",
    ).get(provider_settings)
    headers = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with _client_session() as session:
        async with _post(
            session,
            "https://api.exa.ai/contents",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Exa get contents failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            return data.get("results", [])


async def _baidu_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    api_key = provider_settings.get("websearch_baidu_app_builder_key", "")
    if not api_key:
        raise ValueError("Error: Baidu AI Search API key is not configured in AstrBot.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Appbuilder-Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with _client_session() as session:
        async with _post(
            session,
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Baidu AI Search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            references = data.get("references", [])
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    favicon=item.get("icon"),
                )
                for item in references
                if item.get("url")
            ]


async def _deepseek_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the DeepSeek Search API and normalize its results.

    Args:
        provider_settings: Provider settings containing DeepSeek API keys.
        payload: Search payload with ``query`` and optional ``count`` and
            ``need_content``.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If DeepSeek API keys are not configured.
        Exception: If the API returns a non-200 status.
    """
    keys = provider_settings.get("websearch_deepseek_key", [])
    if not keys:
        raise ValueError("Error: DeepSeek API key is not configured in AstrBot.")

    key = await _get_key_rotator(
        provider_settings,
        "websearch_deepseek_key",
        "DeepSeek",
    ).get(provider_settings)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    async with _client_session() as session:
        async with _post(
            session,
            "https://api.deepseek.com/v1/tools/search",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"DeepSeek web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()

    results: list[SearchResult] = []
    for item in data.get("results", []):
        if not item.get("url"):
            continue
        snippet = item.get("summary") or item.get("snippet") or ""
        if payload.get("need_content") and item.get("content"):
            snippet = "\n\n".join(filter(None, [snippet, item["content"]]))
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item["url"],
                snippet=snippet,
                favicon=item.get("site_icon"),
            )
        )
    return results


async def _deepseek_fetch(
    provider_settings: dict,
    payload: dict,
) -> dict:
    """Fetch one page through the DeepSeek Fetch API.

    Args:
        provider_settings: Provider settings containing DeepSeek API keys.
        payload: Fetch payload with the target ``url``.

    Returns:
        The raw DeepSeek fetch response data.

    Raises:
        ValueError: If DeepSeek API keys are not configured.
        Exception: If the API returns a non-200 status.
    """
    keys = provider_settings.get("websearch_deepseek_key", [])
    if not keys:
        raise ValueError("Error: DeepSeek API key is not configured in AstrBot.")

    key = await _get_key_rotator(
        provider_settings,
        "websearch_deepseek_key",
        "DeepSeek",
    ).get(provider_settings)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    async with _client_session() as session:
        async with _post(
            session,
            "https://api.deepseek.com/v1/tools/fetch",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"DeepSeek fetch failed: {reason}, status: {response.status}",
                )
            return await response.json()


async def _serpapi_request(
    provider_settings: dict,
    payload: dict,
    *,
    engine: str,
) -> dict:
    """Call a SerpApi search engine with API key failover.

    Args:
        provider_settings: Provider settings containing SerpApi API keys.
        payload: Search parameters, excluding credentials and the engine.
        engine: SerpApi engine name for the requested search service.

    Returns:
        The JSON search response.

    Raises:
        ValueError: If SerpApi API keys are not configured.
        RuntimeError: If the API or network request fails.
    """
    keys = provider_settings.get("websearch_serpapi_key", [])
    if not keys:
        raise ValueError("Error: SerpApi API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        api_key = await _get_key_rotator(
            provider_settings,
            "websearch_serpapi_key",
            "SerpApi",
        ).get(provider_settings)
        request_kwargs = _request_kwargs()
        request_kwargs["timeout"] = aiohttp.ClientTimeout(total=60)
        try:
            async with _client_session() as session:
                async with session.get(
                    "https://serpapi.com/search.json",
                    params={**payload, "engine": engine, "api_key": api_key},
                    **request_kwargs,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        status = data.get("search_metadata", {}).get("status")
                        # SerpApi also returns an error message for successful
                        # searches with no results; these should remain empty.
                        if status == "Error" or (
                            data.get("error") and status != "Success"
                        ):
                            reason = str(data.get("error") or "Unknown API error.")
                            raise RuntimeError(
                                "SerpApi search failed: "
                                f"{reason.replace(api_key, '[redacted]')}"
                            )
                        return data
                    reason = (await response.text()).replace(api_key, "[redacted]")
                    last_error = RuntimeError(
                        f"SerpApi search failed: {reason}, status: {response.status}"
                    )
                    if response.status in {401, 403, 429}:
                        continue
                    raise last_error
        except aiohttp.ClientError, TimeoutError:
            # Transport errors can include the request URL with its API key.
            raise RuntimeError("SerpApi search request failed or timed out.") from None

    if last_error is not None:
        raise last_error
    raise RuntimeError("SerpApi search failed with all configured keys.")


async def _serpapi_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Search Google and normalize organic results.

    Args:
        provider_settings: Provider settings containing SerpApi API keys.
        payload: Google search parameters, excluding credentials.

    Returns:
        Normalized organic search results.

    Raises:
        ValueError: If SerpApi API keys are not configured.
        RuntimeError: If the API or network request fails.
    """
    data = await _serpapi_request(provider_settings, payload, engine="google")
    return [
        SearchResult(
            title=item.get("title") or "",
            url=item["link"],
            snippet=item.get("snippet") or "",
            favicon=item.get("favicon"),
        )
        for item in data.get("organic_results", [])
        if item.get("link")
    ]


async def _searxng_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Query a self-hosted SearXNG instance over its JSON API.

    The configured instance URL is the only allowed destination; redirects are
    not followed, and the aggregated result URLs are returned without being
    fetched server-side.

    Args:
        provider_settings: Provider settings containing ``websearch_searxng_url``.
        payload: Search payload with ``query``.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If the SearXNG instance URL is not configured.
        Exception: If the instance responds with a non-200 status, which
            includes the 403 returned when ``search.formats`` does not enable
            ``json``.
    """

    endpoint = str(provider_settings.get("websearch_searxng_url", "")).strip()
    if not endpoint:
        raise ValueError("Error: SearXNG instance URL is not configured in AstrBot.")

    if not endpoint.endswith("/"):
        endpoint = f"{endpoint}/"
    search_url = urljoin(endpoint, "search")
    validated = validate_outbound_url(search_url, searxng_search_policy(endpoint))

    params = {
        "q": payload["query"],
        "format": "json",
        "safesearch": "0",
    }
    headers = {"Accept": "application/json"}
    async with _client_session() as session:
        async with session.get(
            validated.url,
            params=params,
            headers=headers,
            allow_redirects=False,
            **_request_kwargs(),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"SearXNG search failed: {reason}, status: {response.status}",
                )
            data = await response.json(content_type=None)
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    favicon=item.get("favicon"),
                )
                for item in data.get("results", [])
                if item.get("url")
            ]


_DUCKDUCKGO_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
_DUCKDUCKGO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _decode_duckduckgo_url(href: str) -> str:
    """Resolve a DuckDuckGo HTML result link to its target URL.

    DuckDuckGo wraps outbound links as ``//duckduckgo.com/l/?uddg=<target>``;
    the query parser already percent-decodes the ``uddg`` value.

    Args:
        href: Raw ``href`` from the result anchor.

    Returns:
        The decoded target URL, or the input when it is not a redirect wrapper.
    """

    if not href:
        return ""
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    hostname = (parsed.hostname or "").lower()
    is_duckduckgo = hostname == "duckduckgo.com" or hostname.endswith(".duckduckgo.com")
    if is_duckduckgo and parsed.path.startswith("/l/"):
        target = dict(parse_qsl(parsed.query)).get("uddg")
        if target:
            return target
    return href


async def _duckduckgo_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Search DuckDuckGo through its keyless HTML endpoint.

    Args:
        provider_settings: Provider settings (DuckDuckGo is keyless).
        payload: Search payload with ``query``.

    Returns:
        Normalized search results.

    Raises:
        Exception: If the endpoint responds with a non-200 status.
    """

    from bs4 import BeautifulSoup

    async with _client_session() as session:
        async with session.post(
            _DUCKDUCKGO_HTML_ENDPOINT,
            data={"q": payload["query"]},
            headers=_DUCKDUCKGO_HEADERS,
            **_request_kwargs(),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"DuckDuckGo search failed: {reason}, status: {response.status}",
                )
            html = await response.text()

    soup = BeautifulSoup(html, "lxml")
    results: list[SearchResult] = []
    for node in soup.select(".result"):
        link = node.select_one("a.result__a")
        if link is None:
            continue
        url = _decode_duckduckgo_url(str(link.get("href", "")))
        if not url:
            continue
        snippet_node = node.select_one(".result__snippet")
        results.append(
            SearchResult(
                title=link.get_text(" ", strip=True),
                url=url,
                snippet=(
                    snippet_node.get_text(" ", strip=True) if snippet_node else ""
                ),
            )
        )
    return results


@builtin_tool(config=_WEB_SEARCH_ENABLED_CONFIG, required_actions=("tool.web_search",))
@pydantic_dataclass
class SerpApiWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_serpapi"
    description: str = (
        "Search the web using SerpApi Google Search for current information. "
        "Returns page titles, URLs, and snippets."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "max_results": {
                    "type": "integer",
                    "description": (
                        "Maximum results to return from the first page, 1-10. "
                        "Default is 5; fewer may be available."
                    ),
                },
                "country": {
                    "type": "string",
                    "description": "Optional. Google country code, such as us, uk, or cn.",
                },
                "search_lang": {
                    "type": "string",
                    "description": (
                        "Optional. Google interface language code, such as en or zh-cn."
                    ),
                },
                "location": {
                    "type": "string",
                    "description": (
                        "Optional. Search origin, such as Austin, Texas, United States."
                    ),
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_serpapi_key", []):
            return "Error: SerpApi API key is not configured in AstrBot."

        try:
            max_results = max(1, min(int(kwargs.get("max_results", 5)), 10))
        except TypeError, ValueError:
            max_results = 5
        payload = {"q": kwargs["query"]}
        for name, parameter in (
            ("country", "gl"),
            ("search_lang", "hl"),
            ("location", "location"),
        ):
            if kwargs.get(name):
                payload[parameter] = kwargs[name]
        results = await _serpapi_search(provider_settings, payload)
        ref_uuid = str(uuid.uuid4())[:4]
        return json.dumps(
            {
                "results": [
                    {
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.snippet,
                        "index": f"{ref_uuid}.{index}",
                    }
                    for index, result in enumerate(results[:max_results], start=1)
                ]
            },
            ensure_ascii=False,
        )


@builtin_tool(config=_WEB_SEARCH_ENABLED_CONFIG, required_actions=("tool.web_search",))
@pydantic_dataclass
class SerpApiNewsSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "news_search_serpapi"
    description: str = (
        "Search current news using the SerpApi Google News API. Returns article "
        "titles, source URLs, publishers, authors, snippets, and publication times."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Required. News search query. Google News operators such as "
                        "site: and when: are supported."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": (
                        "Maximum articles to return, 1-10. Default is 5; fewer may "
                        "be available."
                    ),
                },
                "country": {
                    "type": "string",
                    "description": "Optional. Google News country code, such as us, uk, or cn.",
                },
                "search_lang": {
                    "type": "string",
                    "description": (
                        "Optional. Google News language code, such as en or zh-cn."
                    ),
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_serpapi_key", []):
            return "Error: SerpApi API key is not configured in AstrBot."

        query = str(kwargs["query"]).strip()
        if not query:
            return "Error: query must not be empty."
        try:
            max_results = max(1, min(int(kwargs.get("max_results", 5)), 10))
        except TypeError, ValueError:
            max_results = 5
        payload = {"q": query}
        for name, parameter in (("country", "gl"), ("search_lang", "hl")):
            if kwargs.get(name):
                payload[parameter] = kwargs[name]
        data = await _serpapi_request(provider_settings, payload, engine="google_news")

        ref_uuid = str(uuid.uuid4())[:4]
        results = []
        seen_urls = set()
        for group in data.get("news_results", []):
            articles = []
            if group.get("link"):
                articles.append(group)
            if isinstance(group.get("highlight"), dict):
                articles.append(group["highlight"])
            articles.extend(
                story for story in group.get("stories", []) if isinstance(story, dict)
            )
            for article in articles:
                source_url = article.get("link")
                if not source_url or source_url in seen_urls:
                    continue
                seen_urls.add(source_url)
                source = article.get("source") or {}
                results.append(
                    {
                        "title": article.get("title") or "",
                        "url": source_url,
                        "snippet": article.get("snippet") or "",
                        "source": source.get("name") or source.get("title") or "",
                        "authors": source.get("authors") or [],
                        "published_at": article.get("iso_date")
                        or article.get("date")
                        or "",
                        "thumbnail_url": article.get("thumbnail")
                        or article.get("thumbnail_small")
                        or "",
                        "index": f"{ref_uuid}.{len(results) + 1}",
                    }
                )
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        return json.dumps({"results": results}, ensure_ascii=False)


@builtin_tool(config=_WEB_SEARCH_ENABLED_CONFIG, required_actions=("tool.web_search",))
@pydantic_dataclass
class SerpApiImageSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "image_search_serpapi"
    description: str = (
        "Find images using SerpApi Google Images Light. Returns direct image URLs, "
        "thumbnails, dimensions, and source page URLs. Use image_url to display "
        "or send an image, and url to cite its source page."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Required. Image search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": (
                        "Maximum images to return, 1-10. Default is 5; fewer may "
                        "be available."
                    ),
                },
                "country": {
                    "type": "string",
                    "description": "Optional. Google country code, such as us, uk, or cn.",
                },
                "search_lang": {
                    "type": "string",
                    "description": (
                        "Optional. Google interface language code, such as en or zh-cn."
                    ),
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_serpapi_key", []):
            return "Error: SerpApi API key is not configured in AstrBot."

        try:
            max_results = max(1, min(int(kwargs.get("max_results", 5)), 10))
        except TypeError, ValueError:
            max_results = 5
        payload = {"q": kwargs["query"]}
        for name, parameter in (("country", "gl"), ("search_lang", "hl")):
            if kwargs.get(name):
                payload[parameter] = kwargs[name]
        data = await _serpapi_request(
            provider_settings, payload, engine="google_images_light"
        )
        ref_uuid = str(uuid.uuid4())[:4]
        results = []
        for item in data.get("images_results", []):
            image_url = item.get("original") or ""
            thumbnail_url = item.get("thumbnail") or item.get("serpapi_thumbnail") or ""
            # Images extracted from PDFs can use x-raw-image:// references.
            # Return their HTTP thumbnail when a direct image URL is unavailable.
            if not image_url.startswith(("https://", "http://")):
                image_url = thumbnail_url
            if not image_url.startswith(("https://", "http://")):
                continue
            source_url = item.get("link") or image_url
            results.append(
                {
                    "title": item.get("title") or "",
                    "url": source_url,
                    "snippet": item.get("source") or "",
                    "image_url": image_url,
                    "thumbnail_url": thumbnail_url,
                    "width": item.get("original_width")
                    if image_url == item.get("original")
                    else None,
                    "height": item.get("original_height")
                    if image_url == item.get("original")
                    else None,
                    "index": f"{ref_uuid}.{len(results) + 1}",
                }
            )
            if len(results) >= max_results:
                break
        return json.dumps({"results": results}, ensure_ascii=False)


@builtin_tool(config=_WEB_SEARCH_ENABLED_CONFIG, required_actions=("tool.web_search",))
@pydantic_dataclass
class SerpApiFinanceSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "finance_search_serpapi"
    description: str = (
        "Look up stocks, indices, funds, currencies, and futures using Google Finance. "
        "Use ticker symbols such as AAPL:NASDAQ or currency pairs such as EUR-USD. "
        "Returns quote prices, currency, timestamps, key statistics, financials, "
        "and news when available. Set window only when price history is needed."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Required. Google Finance symbol, such as AAPL:NASDAQ, "
                        ".INX:INDEXSP, BTC-USD, or EUR-USD."
                    ),
                },
                "search_lang": {
                    "type": "string",
                    "description": (
                        "Optional. Google interface language code, such as en or zh-cn."
                    ),
                },
                "window": {
                    "type": "string",
                    "enum": ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"],
                    "description": (
                        "Optional. Price history range. When set, Google Finance "
                        "returns a quote summary and graph instead of full "
                        "financials and news."
                    ),
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_serpapi_key", []):
            return "Error: SerpApi API key is not configured in AstrBot."

        query = str(kwargs["query"]).strip()
        if not query:
            return "Error: query must not be empty."
        window = kwargs.get("window")
        if window and window not in {"1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"}:
            return "Error: window must be one of 1D, 5D, 1M, 6M, YTD, 1Y, 5Y, MAX."
        payload = {"q": query}
        if window:
            payload["window"] = window
        if kwargs.get("search_lang"):
            payload["hl"] = kwargs["search_lang"]
        data = await _serpapi_request(
            provider_settings, payload, engine="google_finance"
        )
        summary = data.get("summary") or {}
        result = {
            "results": [],
            "summary": summary,
            "knowledge_graph": data.get("knowledge_graph") or {},
            "financials": data.get("financials") or [],
            "news_results": data.get("news_results") or [],
            "suggestions": data.get("suggestions") or [],
        }
        if summary:
            source_url = data.get("search_metadata", {}).get("google_finance_url")
            if not source_url:
                source_url = (
                    f"https://www.google.com/finance/quote/{quote(query, safe=':-.')}"
                )
            result["results"].append(
                {
                    "title": summary.get("title") or query,
                    "url": source_url,
                    "snippet": json.dumps(summary, ensure_ascii=False),
                    "index": f"{str(uuid.uuid4())[:4]}.1",
                }
            )
        if window:
            result["graph"] = data.get("graph") or []
            result["key_events"] = data.get("key_events") or []
        return json.dumps(result, ensure_ascii=False)


@builtin_tool(config=_WEB_SEARCH_ENABLED_CONFIG, required_actions=("tool.web_search",))
@pydantic_dataclass
class SerpApiScholarSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "scholar_search_serpapi"
    description: str = (
        "Search academic publications using Google Scholar. Returns titles, "
        "source URLs, snippets, publication details, citation counts, and available "
        "PDF or full-text links. Supports publication year filters."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Required. Academic search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum publications to return, 1-20. Default is 5.",
                },
                "search_lang": {
                    "type": "string",
                    "description": (
                        "Optional. Google Scholar interface language, such as "
                        "en or zh-cn."
                    ),
                },
                "year_from": {
                    "type": "integer",
                    "description": "Optional. Earliest publication year, inclusive.",
                },
                "year_to": {
                    "type": "integer",
                    "description": "Optional. Latest publication year, inclusive.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_serpapi_key", []):
            return "Error: SerpApi API key is not configured in AstrBot."

        query = str(kwargs["query"]).strip()
        if not query:
            return "Error: query must not be empty."
        try:
            max_results = max(1, min(int(kwargs.get("max_results", 5)), 20))
        except TypeError, ValueError:
            max_results = 5
        payload = {"q": query, "num": max_results}
        for name, parameter in (("year_from", "as_ylo"), ("year_to", "as_yhi")):
            if kwargs.get(name) is not None:
                try:
                    year = int(kwargs[name])
                except TypeError, ValueError:
                    return "Error: publication years must be integers."
                if not 1 <= year <= 9999:
                    return "Error: publication years must be between 1 and 9999."
                payload[parameter] = year
        if payload.get("as_ylo", 1) > payload.get("as_yhi", 9999):
            return "Error: year_from must not be greater than year_to."
        if kwargs.get("search_lang"):
            payload["hl"] = kwargs["search_lang"]
        data = await _serpapi_request(
            provider_settings, payload, engine="google_scholar"
        )
        ref_uuid = str(uuid.uuid4())[:4]
        results = []
        for item in data.get("organic_results", []):
            resources = item.get("resources") or []
            source_url = item.get("link") or next(
                (resource["link"] for resource in resources if resource.get("link")),
                None,
            )
            # Citation-only entries can have a title without a publisher URL.
            if not source_url:
                source_url = (
                    "https://scholar.google.com/scholar?q="
                    f"{quote(item.get('title') or query, safe='')}"
                )
            cited_by = (item.get("inline_links") or {}).get("cited_by") or {}
            publication_info = item.get("publication_info") or {}
            results.append(
                {
                    "title": item.get("title") or "",
                    "url": source_url,
                    "snippet": item.get("snippet") or "",
                    "publication_info": publication_info,
                    "cited_by_count": cited_by.get("total"),
                    "cited_by_url": cited_by.get("link"),
                    "resources": resources,
                    "index": f"{ref_uuid}.{len(results) + 1}",
                }
            )
            if len(results) >= max_results:
                break
        return json.dumps({"results": results}, ensure_ascii=False)


async def _anysearch_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the AnySearch /v1/search endpoint and return normalized results.

    AnySearch also serves anonymous traffic with a daily free quota, so an empty
    key list is valid and results in a single unauthenticated request.

    Args:
        provider_settings: Provider settings containing AnySearch API keys.
        payload: Request payload for the AnySearch search endpoint.

    Returns:
        Normalized search results.

    Raises:
        Exception: If the request fails after all configured keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_anysearch_key", [])
    attempts: list[str | None] = list(keys) if keys else [None]

    last_error = None
    for _ in range(len(attempts)):
        headers = {"Content-Type": "application/json"}
        if keys:
            anysearch_key = await _get_key_rotator(
                provider_settings,
                "websearch_anysearch_key",
                "AnySearch",
            ).get(provider_settings)
            headers["Authorization"] = f"Bearer {anysearch_key}"

        async with _client_session() as session:
            async with _post(
                session,
                "https://api.anysearch.com/v1/search",
                json=payload,
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    code = data.get("code")
                    if code not in (None, 0):
                        raise Exception(
                            f"AnySearch web search failed: {data.get('message') or code}"
                        )
                    body = data.get("data") or data
                    results = []
                    for item in body.get("results", []):
                        if not item.get("url"):
                            continue
                        snippet = item.get("snippet") or item.get("content") or ""
                        fields = []
                        for key, value in item.items():
                            if (
                                key in {"title", "url", "snippet", "content", "favicon"}
                                or value is None
                            ):
                                continue
                            if isinstance(value, dict | list):
                                value = json.dumps(value, ensure_ascii=False)
                            if isinstance(value, str | int | float | bool):
                                fields.append(f"{key}: {value}")
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item["url"],
                                snippet="\n".join([snippet, *fields]).strip(),
                            )
                        )
                    return results
                reason = await response.text()
                if response.status in _ANYSEARCH_RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"AnySearch web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"AnySearch web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("AnySearch web search failed with all configured keys.")


__all__ = [
    "SerpApiFinanceSearchTool",
    "SerpApiImageSearchTool",
    "SerpApiNewsSearchTool",
    "SerpApiScholarSearchTool",
    "SerpApiWebSearchTool",
    "WEB_SEARCH_TOOL_NAMES",
]
