# Web Search

The web search feature gives large language models internet retrieval capability for recent information, which can improve response accuracy and reduce hallucinations to some extent.

AstrBot's built-in web search functionality relies on the large language model's `function calling` capability. If you're not familiar with function calling, please refer to: [Function Calling](/en/use/function-calling).

When using a large language model that supports function calling with the web search feature enabled, you can try saying:

- `Help me search for xxx`
- `Help me summarize this link: https://github.com/Xero-Team/AstrBot`
- `Look up xxx`
- `Recent xxxx`

And other prompts with search intent to trigger the model to invoke the search tool.

## Multi-source retrieval

AstrBot queries every source in the ordered `Web Search Sources` (`websearch_route`) list in parallel, deduplicates the results by canonical URL, and fuses them with RRF (Reciprocal Rank Fusion, k=60) behind a single `web_search` tool. The list order is the priority order: earlier sources carry more weight in the fusion.

- `websearch_route`: the ordered, multi-select source list, defaulting to `["searxng", "duckduckgo"]`.
- `websearch_oversample`: the per-source candidate multiplier, defaulting to 8. Each source fetches `target results` $\times$ `this multiplier` candidates (clamped to each source's limit) before fusion.
- A source that is unconfigured, fails, or times out is skipped without affecting the others; when no source is usable, `web_search` returns a clear error.

Keyless `SearXNG` and `DuckDuckGo` are supported alongside the key-based `Tavily`, `BoCha`, `Baidu AI Search`, `Brave`, `Firecrawl`, `Exa`, `AnySearch`, `DeepSeek`, and `SerpApi`.

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

Go to **Config → select a profile → AI**, find Web Search, choose and order the sources under `Web Search Sources`, then fill in the API Key for each source you enable.

## SearXNG (self-hosted, keyless)

SearXNG already aggregates Google, Bing, DuckDuckGo, and other engines, making it the preferred keyless multi-source option. First enable `json` in `search.formats` in the instance's `settings.yml`, otherwise the endpoint returns `403`:

```yaml
search:
  formats:
    - html
    - json
```

Then fill in the instance address in `SearXNG Instance URL` (`websearch_searxng_url`), for example `http://127.0.0.1:8080`. For safety, AstrBot only contacts the endpoint you explicitly configure, does not follow redirects, and does not fetch result URLs server-side.

If you deploy with Docker, `compose-with-searxng.yml` starts a preconfigured SearXNG sidecar with `json` already enabled. In that stack, use `http://searxng:8080` as the instance URL; see [Deploy AstrBot with Docker](/en/deploy/astrbot/docker).

## DuckDuckGo (keyless fallback)

DuckDuckGo works with no configuration and serves as the keyless fallback. It parses results from its HTML endpoint without any extra dependency.

## Tavily

Go to [Tavily](https://app.tavily.com/home) to get an API Key, then fill it in the corresponding configuration item.

If you use Tavily as one of your web search sources, you will get a better experience optimization on AstrBot ChatUI, including citation source display and more:

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

## BoCha

Get an API Key from the BoCha platform, then fill it in the corresponding configuration item.

## Baidu AI Search

Get an API Key from Baidu Qianfan APP Builder, then fill it in the corresponding configuration item.

## Brave

Get an API Key from Brave Search, then fill it in the corresponding configuration item.

## Firecrawl

Go to [Firecrawl](https://firecrawl.dev) to get an API Key, then fill it in the corresponding configuration item.

## Exa

Go to [Exa](https://dashboard.exa.ai) to get an API Key, then fill it in the corresponding configuration item. Exa is an AI-native search engine that supports keyword and semantic search with category filters, domain restrictions, and date ranges.

## AnySearch

Go to the [AnySearch Console](https://anysearch.com/console/api-keys) to get your API Key, then fill it in the corresponding configuration field.

In addition to general web search, AnySearch can accept a provider-supported domain tag and a `params` object for domain-specific retrieval. Results preserve compatible structured fields as text. `max_results` is limited to 1–10 and the supported result regions are `cn` and `intl`. If the API Key is left empty, it uses anonymous mode with a daily free quota.

## SerpApi

See [Web Search → SerpApi](./websearch/serpapi.md) for API keys, configuration, the `websearch_route` entry, and the Google web, image, finance, and academic search tools. The specialist tools are available whenever the key is configured and web search is enabled; they do not need to be listed in the web search source route.

## DeepSeek

See [Web Search → DeepSeek Search API](./websearch/deepseek.md) for API keys, configuration, the `websearch_route` entry, page extraction through `web_fetch`, search operators, and rate limits. DeepSeek search is configured independently of the chat model: even if the chat model already uses DeepSeek, enter the key separately for search.

## Page extraction

When web search is enabled and the source list contains a configured `Tavily`, `Firecrawl`, `Exa`, or `DeepSeek` source, AstrBot exposes a single `web_fetch` tool that accepts only `url`. It tries those configured sources sequentially in `websearch_route` order, moving to the next source when one fails or times out, and returns `URL`, an optional `Title`, and `Content`. If every source fails, it returns one generic error without exposing upstream error text.

Extraction parameters use each provider's fixed defaults: Tavily basic extraction, Firecrawl Markdown main content, Exa with at most 3000 characters, and the unchanged DeepSeek request. The model does not choose a provider and cannot pass advanced extraction parameters. Unconfigured sources and sources without extraction support, such as SearXNG and DuckDuckGo, are skipped. SerpApi additionally provides `image_search_serpapi`, `finance_search_serpapi`, and `scholar_search_serpapi` whenever its key is configured.
