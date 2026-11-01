import json
from types import SimpleNamespace

import pytest

from astrbot.core.tools import web_search_router
from astrbot.core.tools import web_search_tools as tools


@pytest.mark.asyncio
async def test_web_search_tool_returns_fused_payload(monkeypatch):
    from astrbot.core.tools import web_search_router

    calls = {}

    async def fake_search(route, provider_settings, *, query, max_results, oversample):
        calls.update(
            route=route,
            query=query,
            max_results=max_results,
            oversample=oversample,
        )
        return [
            tools.SearchResult(
                title="AstrBot",
                url="https://example.com",
                snippet="Search result",
            )
        ]

    monkeypatch.setattr(web_search_router, "search", fake_search)
    tool = web_search_router.WebSearchTool()
    context = _context_with_provider_settings(
        {"websearch_route": ["searxng", "duckduckgo"], "websearch_oversample": 4}
    )

    result = await tool.call(context, query="AstrBot", max_results=3)

    assert calls == {
        "route": ("searxng", "duckduckgo"),
        "query": "AstrBot",
        "max_results": 3,
        "oversample": 4,
    }
    assert json.loads(result)["results"] == [
        {
            "title": "AstrBot",
            "url": "https://example.com",
            "snippet": "Search result",
            "index": json.loads(result)["results"][0]["index"],
        }
    ]


@pytest.mark.asyncio
async def test_web_search_tool_reports_missing_route():
    tool = web_search_router.WebSearchTool()
    context = _context_with_provider_settings({})

    result = await tool.call(context, query="AstrBot")

    assert result.startswith("Error: web search route")


@pytest.mark.asyncio
async def test_web_search_tool_reports_unconfigured_route(monkeypatch):
    from astrbot.core.tools import web_search_router

    async def fake_search(route, provider_settings, *, query, max_results, oversample):
        raise web_search_router.NoSearchSourceError("none")

    monkeypatch.setattr(web_search_router, "search", fake_search)
    tool = web_search_router.WebSearchTool()
    context = _context_with_provider_settings({"websearch_route": ["tavily"]})

    result = await tool.call(context, query="AstrBot")

    assert result.startswith("Error: no configured web search source")


@pytest.mark.asyncio
async def test_firecrawl_search_maps_v2_data_list(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": [
                    {
                        "title": "AstrBot",
                        "url": "https://example.com",
                        "description": "Search result",
                    }
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._firecrawl_search(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"query": "AstrBot", "limit": 5, "sources": ["web"]},
    )

    assert session.posted == {
        "url": "https://api.firecrawl.dev/v2/search",
        "json": {"query": "AstrBot", "limit": 5, "sources": ["web"]},
        "headers": {
            "Authorization": "Bearer firecrawl-key",
            "Content-Type": "application/json",
        },
        "timeout": tools._DEFAULT_HTTP_TIMEOUT,
    }
    assert results == [
        tools.SearchResult(
            title="AstrBot", url="https://example.com", snippet="Search result"
        )
    ]


@pytest.mark.asyncio
async def test_firecrawl_search_maps_v2_grouped_web_data(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": {
                    "web": [
                        {
                            "title": "AstrBot",
                            "url": "https://example.com",
                            "description": "Search result",
                        }
                    ]
                },
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._firecrawl_search(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"query": "AstrBot", "limit": 5, "sources": ["web"]},
    )

    assert results == [
        tools.SearchResult(
            title="AstrBot", url="https://example.com", snippet="Search result"
        )
    ]


@pytest.mark.asyncio
async def test_firecrawl_search_uses_session_context(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": [
                    {
                        "title": "AstrBot",
                        "url": "https://example.com",
                        "description": "Search result",
                    }
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    await tools._firecrawl_search(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"query": "AstrBot"},
    )

    assert session.trust_env is False
    assert session.entered is True
    assert session.exited is True
    assert session.posted == {
        "url": "https://api.firecrawl.dev/v2/search",
        "json": {"query": "AstrBot"},
        "headers": {
            "Authorization": "Bearer firecrawl-key",
            "Content-Type": "application/json",
        },
        "timeout": tools._DEFAULT_HTTP_TIMEOUT,
    }


@pytest.mark.asyncio
async def test_firecrawl_search_raises_error_for_http_errors(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Firecrawl web search failed: Unauthorized, status: 401",
    ):
        await tools._firecrawl_search(
            {"websearch_firecrawl_key": ["firecrawl-key"]},
            {"query": "AstrBot"},
        )

    assert session.trust_env is False
    assert session.entered is True
    assert session.exited is True


@pytest.mark.asyncio
async def test_firecrawl_scrape_uses_request_setup(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": {"url": "https://example.com", "markdown": "# Example"},
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    result = await tools._firecrawl_scrape(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"url": "https://example.com", "formats": ["markdown"]},
    )

    assert result == {"url": "https://example.com", "markdown": "# Example"}
    assert session.trust_env is False
    assert session.entered is True
    assert session.exited is True
    assert session.posted == {
        "url": "https://api.firecrawl.dev/v2/scrape",
        "json": {"url": "https://example.com", "formats": ["markdown"]},
        "headers": {
            "Authorization": "Bearer firecrawl-key",
            "Content-Type": "application/json",
        },
        "timeout": tools._DEFAULT_HTTP_TIMEOUT,
    }


@pytest.mark.asyncio
async def test_firecrawl_scrape_raises_error_for_http_errors(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Firecrawl web scraper failed: Unauthorized, status: 401",
    ):
        await tools._firecrawl_scrape(
            {"websearch_firecrawl_key": ["firecrawl-key"]},
            {"url": "https://example.com", "formats": ["markdown"]},
        )

    assert session.trust_env is False
    assert session.entered is True
    assert session.exited is True


class _FakeFirecrawlResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self.json_data = json_data or {}
        self.text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self.json_data

    async def text(self):
        return self.text_data


class _FakeFirecrawlSession:
    def __init__(self, response):
        self.response = response
        self.trust_env = None
        self.entered = False
        self.exited = False
        self.posted = None
        self.gotten = None

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return None

    def post(self, url, json, headers, timeout):
        self.posted = {
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        }
        return self.response

    def get(self, url, params, headers, timeout):
        self.gotten = {
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout,
        }
        return self.response


class _CycleSession:
    """Return the next response for each post() call in key rotation tests."""

    def __init__(self, responses: list):
        self.responses = responses
        self.cursor = 0
        self.trust_env = None
        self.entered = False
        self.exited = False
        self.calls: list[dict] = []

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return None

    def post(self, url, json, headers, timeout):
        resp = self.responses[self.cursor]
        self.cursor = (self.cursor + 1) % len(self.responses)
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return resp


class _TavilyResponse:
    """Fake HTTP response for Tavily API tests."""

    def __init__(self, status=200, jsonData=None, textData=""):
        self.status = status
        self.jsonData = jsonData or {}
        self.textData = textData

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self.jsonData

    async def text(self):
        return self.textData


def _runtime_search_settings(values: dict) -> dict:
    """Create one isolated key-rotation state for a direct search call."""
    return tools._RuntimeProviderSettings(values, tools._WebSearchRuntimeState())


# ---------------------------------------------------------------------------
# Issue #8886: Tavily key rotation did not fail over to the next key.
# ---------------------------------------------------------------------------


class _CycleSession:
    """Return the next response for each post() call in key rotation tests."""

    def __init__(self, responses: list):
        self.responses = responses
        self.cursor = 0
        self.trust_env = None
        self.entered = False
        self.exited = False
        self.calls: list[dict] = []

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return None

    def post(self, url, json, headers, timeout):
        resp = self.responses[self.cursor]
        self.cursor = (self.cursor + 1) % len(self.responses)
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return resp


class _TavilyResponse:
    """Fake HTTP response for Tavily API tests."""

    def __init__(self, status=200, jsonData=None, textData=""):
        self.status = status
        self.jsonData = jsonData or {}
        self.textData = textData

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self.jsonData

    async def text(self):
        return self.textData


# ---------------------------------------------------------------------------
# Issue #8886: Tavily key rotation did not fail over to the next key.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_search_raises_value_error_when_no_key_configured():
    """Raise ValueError when no Tavily API key is configured."""
    with pytest.raises(
        ValueError,
        match="Error: Tavily API key is not configured in AstrBot.",
    ):
        await tools._tavily_search({}, {"query": "test"})


@pytest.mark.asyncio
async def test_tavily_search_key_failover_on_quota_exceeded_432(
    monkeypatch,
):
    """Fail over to the second key when the first key returns 432."""
    session = _CycleSession(
        [
            _TavilyResponse(
                status=432,
                textData='{"detail":{"error":"quota exceeded"}}',
            ),
            _TavilyResponse(
                status=200,
                jsonData={
                    "results": [
                        {
                            "title": "AstrBot",
                            "url": "https://example.com",
                            "content": "OK",
                        }
                    ]
                },
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = _runtime_search_settings(
        {"websearch_tavily_key": ["bad-key", "good-key"]}
    )

    results = await tools._tavily_search(providerSettings, {"query": "test"})

    assert len(results) == 1
    assert results[0].title == "AstrBot"
    assert results[0].url == "https://example.com"
    assert len(session.calls) == 2  # Both keys were attempted.


@pytest.mark.asyncio
async def test_tavily_search_key_failover_on_rate_limited_429(
    monkeypatch,
):
    """Fail over to the second key when the first key returns 429."""
    session = _CycleSession(
        [
            _TavilyResponse(
                status=429,
                textData='{"detail":{"error":"rate limited"}}',
            ),
            _TavilyResponse(
                status=200,
                jsonData={
                    "results": [
                        {
                            "title": "RateLimitOK",
                            "url": "https://example2.com",
                            "content": "OK",
                        }
                    ]
                },
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = _runtime_search_settings(
        {"websearch_tavily_key": ["rate-limited-key", "good-key"]}
    )

    results = await tools._tavily_search(providerSettings, {"query": "test"})

    assert len(results) == 1
    assert results[0].title == "RateLimitOK"
    assert len(session.calls) == 2  # Both keys were attempted.


@pytest.mark.asyncio
async def test_tavily_search_fails_when_all_keys_exhausted_8886(
    monkeypatch,
):
    """Raise the last error when all keys are exhausted."""
    # Both responses are retryable failures.
    session = _CycleSession(
        [
            _TavilyResponse(
                status=432,
                textData='{"detail":{"error":"quota exceeded"}}',
            ),
            _TavilyResponse(
                status=429,
                textData='{"detail":{"error":"rate limited"}}',
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = _runtime_search_settings(
        {"websearch_tavily_key": ["bad-key-1", "bad-key-2"]}
    )

    with pytest.raises(
        Exception,
        match="Tavily web search failed",
    ):
        await tools._tavily_search(providerSettings, {"query": "test"})

    assert len(session.calls) == 2  # Both keys were attempted.


@pytest.mark.asyncio
async def test_tavily_search_does_not_failover_on_server_error_500(
    monkeypatch,
):
    """Raise immediately for non-key-related errors such as 500 responses."""
    session = _CycleSession(
        [
            _TavilyResponse(
                status=500,
                textData='{"error":"internal server error"}',
            ),
            _TavilyResponse(
                status=200,
                jsonData={
                    "results": [
                        {"title": "OK", "url": "https://example.com", "content": "OK"}
                    ]
                },
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = _runtime_search_settings(
        {"websearch_tavily_key": ["key-1", "key-2"]}
    )

    with pytest.raises(
        Exception,
        match="Tavily web search failed.*status: 500",
    ):
        await tools._tavily_search(providerSettings, {"query": "test"})

    # Only one key is attempted because 500 is not retryable.
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_tavily_key_rotation_is_isolated_by_runtime_state():
    """Independent tool runtimes must not share API-key rotation state."""
    first_runtime = _runtime_search_settings(
        {"websearch_tavily_key": ["first-a", "first-b"]}
    )
    second_runtime = _runtime_search_settings(
        {"websearch_tavily_key": ["second-a", "second-b"]}
    )

    first_rotator = tools._get_key_rotator(
        first_runtime,
        "websearch_tavily_key",
        "Tavily",
    )
    second_rotator = tools._get_key_rotator(
        second_runtime,
        "websearch_tavily_key",
        "Tavily",
    )

    assert await first_rotator.get(first_runtime) == "first-a"
    assert await first_rotator.get(first_runtime) == "first-b"
    assert await second_rotator.get(second_runtime) == "second-a"


def _context_with_provider_settings(provider_settings):
    config = {"provider_settings": provider_settings}
    agent_context = SimpleNamespace(
        context=SimpleNamespace(get_config=lambda umo: config),
        event=SimpleNamespace(unified_msg_origin="test:private:session"),
    )
    return SimpleNamespace(context=agent_context)


@pytest.mark.asyncio
async def test_exa_search_raw_api_call(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "results": [
                    {
                        "title": "AstrBot",
                        "url": "https://example.com",
                        "text": "AI Agent Assistant",
                    }
                ]
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._exa_search(
        {"websearch_exa_key": ["exa-key"]},
        {"query": "AstrBot", "numResults": 10, "type": "auto"},
    )

    assert session.posted["url"] == "https://api.exa.ai/search"
    assert session.posted["headers"]["x-api-key"] == "exa-key"
    assert results == [
        tools.SearchResult(
            title="AstrBot", url="https://example.com", snippet="AI Agent Assistant"
        )
    ]


@pytest.mark.asyncio
async def test_exa_search_raises_on_http_error(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Exa web search failed: Unauthorized, status: 401",
    ):
        await tools._exa_search(
            {"websearch_exa_key": ["exa-key"]},
            {"query": "AstrBot"},
        )


@pytest.mark.asyncio
async def test_exa_get_contents_raises_on_http_error(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=403, text_data="Forbidden")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Exa get contents failed: Forbidden, status: 403",
    ):
        await tools._exa_get_contents(
            {"websearch_exa_key": ["exa-key"]},
            {"ids": ["https://example.com"]},
        )


@pytest.mark.asyncio
async def test_anysearch_search_maps_results(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "code": 0,
                "message": "success",
                "data": {
                    "results": [
                        {
                            "title": "AstrBot",
                            "url": "https://github.com/Xero-Team/AstrBot",
                            "snippet": "A powerful AI chatbot framework",
                            "content": "AstrBot is a flexible AI chatbot framework...",
                        },
                        {
                            "title": "AstrBot Documentation",
                            "url": "https://example.com/docs",
                            "content": "Getting started with AstrBot...",
                            "score": 0.9,
                            "metadata": {"source": "docs"},
                        },
                    ]
                },
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._anysearch_search(
        {"websearch_anysearch_key": ["test-key"]},
        {"query": "AstrBot"},
    )

    assert session.posted["url"] == "https://api.anysearch.com/v1/search"
    assert session.posted["headers"]["Authorization"] == "Bearer test-key"
    assert results == [
        tools.SearchResult(
            title="AstrBot",
            url="https://github.com/Xero-Team/AstrBot",
            snippet="A powerful AI chatbot framework",
        ),
        tools.SearchResult(
            title="AstrBot Documentation",
            url="https://example.com/docs",
            snippet='Getting started with AstrBot...\nscore: 0.9\nmetadata: {"source": "docs"}',
        ),
    ]


@pytest.mark.asyncio
async def test_anysearch_search_supports_anonymous_mode(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=200, json_data={"data": {"results": []}})
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    await tools._anysearch_search({"websearch_anysearch_key": []}, {"query": "test"})

    assert session.posted is not None
    assert "Authorization" not in session.posted["headers"]


@pytest.mark.asyncio
async def test_anysearch_search_key_failover_on_quota_exhausted_402(monkeypatch):
    session = _CycleSession(
        [
            _FakeFirecrawlResponse(status=402, text_data="quota exhausted"),
            _FakeFirecrawlResponse(status=200, json_data={"data": {"results": []}}),
        ]
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    await tools._anysearch_search(
        {"websearch_anysearch_key": ["key1", "key2"]},
        {"query": "test"},
    )

    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_anysearch_search_does_not_failover_on_server_error_500(monkeypatch):
    session = _CycleSession(
        [
            _FakeFirecrawlResponse(status=500, text_data="internal server error"),
            _FakeFirecrawlResponse(status=200, json_data={"data": {"results": []}}),
        ]
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="internal server error"):
        await tools._anysearch_search(
            {"websearch_anysearch_key": ["key1", "key2"]},
            {"query": "test"},
        )

    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_anysearch_search_raises_for_http_200_business_error(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200, json_data={"code": 4001, "message": "bad params"}
        )
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    with pytest.raises(Exception, match="bad params"):
        await tools._anysearch_search({}, {"query": "test"})


class _DeepSeekResponse:
    def __init__(self, *, status=200, json_data=None, text=""):
        self.status = status
        self._json_data = json_data or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text


class _DeepSeekSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_deepseek_search_maps_results_and_content(monkeypatch):
    response = _DeepSeekResponse(
        json_data={
            "results": [
                {
                    "title": "AstrBot",
                    "url": "https://example.com",
                    "summary": "Summary",
                    "content": "Full content",
                    "site_icon": "https://example.com/icon.png",
                },
                {"title": "Missing URL", "summary": "skip"},
            ]
        }
    )
    monkeypatch.setattr(tools, "_client_session", lambda: _DeepSeekSession())
    monkeypatch.setattr(
        tools,
        "_post",
        lambda _session, _url, *, json, headers: response,
    )

    results = await tools._deepseek_search(
        {"websearch_deepseek_key": ["deepseek-key"]},
        {"query": "AstrBot", "count": 3, "need_content": True},
    )

    assert results == [
        tools.SearchResult(
            title="AstrBot",
            url="https://example.com",
            snippet="Summary\n\nFull content",
            favicon="https://example.com/icon.png",
        )
    ]


@pytest.mark.asyncio
async def test_deepseek_fetch_returns_response(monkeypatch):
    response = _DeepSeekResponse(json_data={"title": "Example", "content": "# Example"})
    monkeypatch.setattr(tools, "_client_session", lambda: _DeepSeekSession())
    monkeypatch.setattr(
        tools,
        "_post",
        lambda _session, _url, *, json, headers: response,
    )

    result = await tools._deepseek_fetch(
        {"websearch_deepseek_key": ["deepseek-key"]},
        {"url": "https://example.com"},
    )

    assert result == {"title": "Example", "content": "# Example"}


@pytest.mark.asyncio
async def test_deepseek_tools_require_api_key():
    with pytest.raises(ValueError, match="not configured"):
        await tools._deepseek_search({}, {"query": "AstrBot"})
    with pytest.raises(ValueError, match="not configured"):
        await tools._deepseek_fetch({}, {"url": "https://example.com"})


class _SerpApiResponse:
    def __init__(self, *, status=200, json_data=None, text=""):
        self.status = status
        self._json_data = json_data or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text


class _SerpApiSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def get(self, url, *, params, **kwargs):
        self.calls.append({"url": url, "params": params, **kwargs})
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_serpapi_search_maps_organic_results(monkeypatch):
    session = _SerpApiSession(
        [
            _SerpApiResponse(
                json_data={
                    "search_metadata": {"status": "Success"},
                    "organic_results": [
                        {
                            "title": "AstrBot",
                            "link": "https://example.com",
                            "snippet": "Search result",
                            "favicon": "https://example.com/favicon.ico",
                        }
                    ],
                }
            )
        ]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    results = await tools._serpapi_search(
        {"websearch_serpapi_key": ["serp-key"]},
        {"q": "AstrBot"},
    )

    assert results == [
        tools.SearchResult(
            title="AstrBot",
            url="https://example.com",
            snippet="Search result",
            favicon="https://example.com/favicon.ico",
        )
    ]
    assert session.calls[0]["url"] == "https://serpapi.com/search.json"
    assert session.calls[0]["params"]["api_key"] == "serp-key"


@pytest.mark.asyncio
async def test_serpapi_search_rotates_on_auth_failure(monkeypatch):
    session = _SerpApiSession(
        [
            _SerpApiResponse(status=401, text="bad key"),
            _SerpApiResponse(
                json_data={
                    "search_metadata": {"status": "Success"},
                    "organic_results": [{"title": "ok", "link": "https://example.com"}],
                }
            ),
        ]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    results = await tools._serpapi_search(
        _runtime_search_settings(
            {"websearch_serpapi_key": ["first-key", "second-key"]}
        ),
        {"q": "AstrBot"},
    )

    assert [result.url for result in results] == ["https://example.com"]
    assert [call["params"]["api_key"] for call in session.calls] == [
        "first-key",
        "second-key",
    ]


@pytest.mark.asyncio
async def test_serpapi_error_redacts_api_key(monkeypatch):
    session = _SerpApiSession(
        [_SerpApiResponse(status=500, text="failed with secret-key")]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    with pytest.raises(RuntimeError) as caught:
        await tools._serpapi_search(
            {"websearch_serpapi_key": ["secret-key"]},
            {"q": "AstrBot"},
        )

    assert "secret-key" not in str(caught.value)
    assert "[redacted]" in str(caught.value)


@pytest.mark.asyncio
async def test_serpapi_tools_require_key():
    context = _context_with_provider_settings({})
    for tool in (
        tools.SerpApiWebSearchTool(),
        tools.SerpApiNewsSearchTool(),
        tools.SerpApiImageSearchTool(),
        tools.SerpApiFinanceSearchTool(),
        tools.SerpApiScholarSearchTool(),
    ):
        assert "not configured" in await tool.call(context, query="AstrBot")


@pytest.mark.asyncio
async def test_serpapi_news_search_maps_articles_and_metadata(monkeypatch):
    session = _SerpApiSession(
        [
            _SerpApiResponse(
                json_data={
                    "news_results": [
                        {
                            "title": "AstrBot adds a news search tool",
                            "link": "https://example.com/astrbot-news",
                            "snippet": "The project added Google News support.",
                            "source": {
                                "name": "Example News",
                                "icon": "https://example.com/favicon.ico",
                                "authors": ["A. Reporter"],
                            },
                            "iso_date": "2026-10-24T08:00:00Z",
                            "thumbnail": "https://example.com/news.jpg",
                        },
                        {"title": "Group without a direct article", "stories": []},
                    ]
                }
            )
        ]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    context = _context_with_provider_settings({"websearch_serpapi_key": ["test-key"]})
    result = json.loads(
        await tools.SerpApiNewsSearchTool().call(
            context,
            query="AstrBot",
            country="us",
            search_lang="en",
        )
    )["results"]

    assert session.calls[0]["params"] == {
        "engine": "google_news",
        "api_key": "test-key",
        "q": "AstrBot",
        "gl": "us",
        "hl": "en",
    }
    assert len(result) == 1
    assert result[0]["title"] == "AstrBot adds a news search tool"
    assert result[0]["url"] == "https://example.com/astrbot-news"
    assert result[0]["snippet"] == "The project added Google News support."
    assert result[0]["source"] == "Example News"
    assert result[0]["authors"] == ["A. Reporter"]
    assert result[0]["published_at"] == "2026-10-24T08:00:00Z"
    assert result[0]["thumbnail_url"] == "https://example.com/news.jpg"
    assert result[0]["index"].endswith(".1")


@pytest.mark.asyncio
async def test_serpapi_news_search_flattens_groups_and_deduplicates(monkeypatch):
    session = _SerpApiSession(
        [
            _SerpApiResponse(
                json_data={
                    "news_results": [
                        {
                            "highlight": {
                                "title": "Highlighted article",
                                "link": "https://example.com/highlight",
                            },
                            "stories": [
                                {
                                    "title": "Duplicate article",
                                    "link": "https://example.com/highlight",
                                },
                                {
                                    "title": "Related article",
                                    "link": "https://example.com/related",
                                    "date": "Oct 24, 2026",
                                },
                            ],
                        }
                    ]
                }
            )
        ]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    context = _context_with_provider_settings({"websearch_serpapi_key": ["test-key"]})
    result = json.loads(
        await tools.SerpApiNewsSearchTool().call(
            context, query="AstrBot", max_results=2
        )
    )["results"]

    assert [item["url"] for item in result] == [
        "https://example.com/highlight",
        "https://example.com/related",
    ]
    assert result[1]["published_at"] == "Oct 24, 2026"


@pytest.mark.asyncio
async def test_serpapi_news_search_validates_query_before_request(monkeypatch):
    def fail_session():
        raise AssertionError("the news tool must not issue a request")

    monkeypatch.setattr(tools, "_client_session", fail_session)

    context = _context_with_provider_settings({"websearch_serpapi_key": ["test-key"]})
    result = await tools.SerpApiNewsSearchTool().call(context, query="  ")

    assert result == "Error: query must not be empty."


@pytest.mark.asyncio
async def test_serpapi_image_search_falls_back_to_thumbnail(monkeypatch):
    response = _SerpApiResponse(
        json_data={
            "images_results": [
                {
                    "title": "PDF image",
                    "original": "x-raw-image:///tmp/image",
                    "thumbnail": "https://example.com/thumb.png",
                    "link": "https://example.com/source",
                }
            ]
        }
    )
    session = _SerpApiSession([response])
    monkeypatch.setattr(tools, "_client_session", lambda: session)
    tool = tools.SerpApiImageSearchTool()
    context = _context_with_provider_settings({"websearch_serpapi_key": ["serp-key"]})

    result = json.loads(await tool.call(context, query="diagram", max_results=1))

    assert result["results"][0]["image_url"] == "https://example.com/thumb.png"
    assert result["results"][0]["url"] == "https://example.com/source"


_KEY_FAILOVER_CASES = [
    (tools._tavily_search, "tavily", 433),
    (tools._tavily_extract, "tavily", 433),
    (tools._firecrawl_search, "firecrawl", 402),
    (tools._firecrawl_scrape, "firecrawl", 402),
    (tools._exa_search, "exa", 401),
    (tools._exa_search, "exa", 402),
    (tools._exa_search, "exa", 429),
    (tools._exa_get_contents, "exa", 401),
    (tools._exa_get_contents, "exa", 402),
    (tools._exa_get_contents, "exa", 429),
]
_PROVIDER_NAMES = {"tavily": "Tavily", "firecrawl": "Firecrawl", "exa": "Exa"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("search_function", "provider", "status"), _KEY_FAILOVER_CASES)
@pytest.mark.parametrize("exhausted", [False, True])
@pytest.mark.parametrize("interleaved", [False, True])
@pytest.mark.parametrize("duplicate_first", [False, True])
async def test_search_key_errors_try_next_key(
    monkeypatch,
    search_function,
    provider,
    status,
    exhausted,
    interleaved,
    duplicate_first,
):
    setting_name = f"websearch_{provider}_key"
    row = {
        "title": "Example",
        "url": "https://example.com",
        "content": "OK",
        "description": "OK",
        "text": "OK",
    }
    success_data = {"results": [row], "data": [row]}
    if search_function is tools._firecrawl_scrape:
        success_data["data"] = {"markdown": "# Example"}
    session = _CycleSession(
        [
            _FakeFirecrawlResponse(status=status, text_data="first key failed"),
            _FakeFirecrawlResponse(
                status=status if exhausted else 200,
                text_data="last key failed",
                json_data=success_data,
            ),
        ]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)
    keys = ["first-key", "second-key"]
    if duplicate_first:
        keys.insert(0, "first-key")
    settings = _runtime_search_settings({setting_name: keys})
    if interleaved:

        async def advance_other_request():
            # Another request advances the shared cursor before this retry.
            await tools._get_key_rotator(
                settings, setting_name, _PROVIDER_NAMES[provider]
            ).get(settings)
            return "first key failed"

        monkeypatch.setattr(session.responses[0], "text", advance_other_request)
    payload = {"query": "AstrBot", "urls": ["https://example.com"]}

    if exhausted:
        with pytest.raises(Exception, match=f"last key failed, status: {status}"):
            await search_function(settings, payload)
    else:
        result = await search_function(settings, payload)
        if search_function is tools._firecrawl_scrape:
            assert result == {"markdown": "# Example"}
        elif search_function in (tools._tavily_extract, tools._exa_get_contents):
            assert result == [row]
        else:
            assert result == [
                tools.SearchResult(
                    title="Example", url="https://example.com", snippet="OK"
                )
            ]

    header = "x-api-key" if provider == "exa" else "Authorization"
    prefix = "" if provider == "exa" else "Bearer "
    assert [call["headers"][header] for call in session.calls] == [
        f"{prefix}first-key",
        f"{prefix}second-key",
    ]
    assert all(call["json"] == payload for call in session.calls)
    assert session.exited is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "search_function", [tools._exa_search, tools._exa_get_contents]
)
@pytest.mark.parametrize("status", [400, 500])
async def test_exa_non_key_errors_do_not_retry(monkeypatch, search_function, status):
    session = _CycleSession(
        [_FakeFirecrawlResponse(status=status, text_data="search_function failed")]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)

    with pytest.raises(Exception, match=f"search_function failed, status: {status}"):
        await search_function(
            _runtime_search_settings(
                {"websearch_exa_key": ["first-key", "second-key"]}
            ),
            {},
        )

    assert len(session.calls) == 1


class _BraveCycleSession(_CycleSession):
    def get(self, url, params, headers, timeout):
        response = self.responses[self.cursor]
        self.cursor = (self.cursor + 1) % len(self.responses)
        self.calls.append({"url": url, "params": params, "headers": headers})
        return response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "retry"),
    [
        ('{"error":{"code":"SUBSCRIPTION_TOKEN_INVALID"}}', True),
        ('{"error":{"code":"VALIDATION"}}', False),
        ('{"error":null}', False),
        ("[]", False),
        ("not JSON", False),
    ],
)
@pytest.mark.parametrize("interleaved", [False, True])
@pytest.mark.parametrize("duplicate_first", [False, True])
async def test_brave_only_retries_invalid_subscription_token(
    monkeypatch, reason, retry, interleaved, duplicate_first
):
    session = _BraveCycleSession(
        [
            _FakeFirecrawlResponse(status=422, text_data=reason),
            _FakeFirecrawlResponse(
                json_data={"web": {"results": [{"title": "Example"}]}}
            ),
        ]
    )
    monkeypatch.setattr(tools, "_client_session", lambda: session)
    keys = ["first-key", "second-key"]
    if duplicate_first:
        keys.insert(0, "first-key")
    settings = _runtime_search_settings({"websearch_brave_key": keys})
    if interleaved:

        async def advance_other_request():
            await tools._get_key_rotator(settings, "websearch_brave_key", "Brave").get(
                settings
            )
            return reason

        monkeypatch.setattr(session.responses[0], "text", advance_other_request)

    if retry:
        results = await tools._brave_search(settings, {"q": "AstrBot"})
        assert results == [tools.SearchResult(title="Example", url="", snippet="")]
    else:
        with pytest.raises(Exception, match="status: 422"):
            await tools._brave_search(settings, {"q": "AstrBot"})

    assert [call["headers"]["X-Subscription-Token"] for call in session.calls] == (
        ["first-key", "second-key"] if retry else ["first-key"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 402, 429])
@pytest.mark.parametrize("exhausted", [False, True])
@pytest.mark.parametrize("operation", ["search", "fetch"])
@pytest.mark.parametrize("interleaved", [False, True])
@pytest.mark.parametrize("duplicate_first", [False, True])
async def test_deepseek_key_errors_try_next_key(
    monkeypatch,
    status,
    exhausted,
    operation,
    interleaved,
    duplicate_first,
):
    responses = [
        _DeepSeekResponse(status=status, text="first key failed"),
        _DeepSeekResponse(
            status=status if exhausted else 200,
            text="last key failed",
            json_data={
                "results": [{"title": "Example", "url": "https://example.com"}],
                "title": "Example",
                "content": "# Example",
            },
        ),
    ]
    calls: list[dict] = []

    def fake_post(_session, _url, *, json, headers):
        response = responses[min(len(calls), len(responses) - 1)]
        calls.append({"json": json, "headers": headers})
        return response

    monkeypatch.setattr(tools, "_client_session", lambda: _DeepSeekSession())
    monkeypatch.setattr(tools, "_post", fake_post)
    keys = ["first-key", "second-key"]
    if duplicate_first:
        keys.insert(0, "first-key")
    settings = _runtime_search_settings({"websearch_deepseek_key": keys})
    if interleaved:

        async def advance_other_request():
            await tools._get_key_rotator(
                settings, "websearch_deepseek_key", "DeepSeek"
            ).get(settings)
            return "first key failed"

        monkeypatch.setattr(responses[0], "text", advance_other_request)
    payload = (
        {"query": "AstrBot"}
        if operation == "search"
        else {"url": "https://example.com"}
    )
    search_function = (
        tools._deepseek_search if operation == "search" else tools._deepseek_fetch
    )
    operation_name = "web search" if operation == "search" else "fetch"

    if exhausted:
        with pytest.raises(
            Exception,
            match=f"DeepSeek {operation_name} failed: last key failed, status: {status}",
        ):
            await search_function(settings, payload)
    else:
        result = await search_function(settings, payload)
        if operation == "search":
            assert result == [
                tools.SearchResult(
                    title="Example", url="https://example.com", snippet=""
                )
            ]
        else:
            assert result["title"] == "Example"
            assert result["content"] == "# Example"

    assert [call["headers"]["Authorization"] for call in calls] == [
        "Bearer first-key",
        "Bearer second-key",
    ]
    assert calls[0]["json"] == calls[1]["json"] == payload


@pytest.mark.asyncio
async def test_key_rotator_keeps_request_attempts_independent():
    rotator = tools._KeyRotator("keys", "Test")
    settings = {"keys": ["first", "first", "second"]}
    first_request: set[str] = set()
    second_request: set[str] = set()

    assert await rotator.get(settings, first_request) == "first"
    assert await rotator.get(settings, second_request) == "first"
    assert await rotator.get(settings, second_request) == "second"
    assert await rotator.get(settings, first_request) == "second"
    assert first_request == second_request == {"first", "second"}
    with pytest.raises(ValueError, match="No untried Test API keys remain"):
        await rotator.get(settings, first_request)
    # Omitting the request-local set preserves the ordinary round-robin API.
    assert await rotator.get(settings) == "first"
    assert await rotator.get(settings) == "first"
    assert await rotator.get(settings) == "second"
