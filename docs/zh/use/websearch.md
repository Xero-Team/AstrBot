# 网页搜索

网页搜索功能旨在为大模型提供联网检索能力，以获取最近信息，一定程度上能够提高回复准确度，减少幻觉。

AstrBot 内置的网页搜索功能依赖大模型提供 `函数调用` 能力。如果你不了解函数调用，请参考：[函数调用](/use/function-calling)。

在使用支持函数调用的大模型且开启了网页搜索功能的情况下，您可以试着说：

- `帮我搜索一下 xxx`
- `帮我总结一下这个链接：https://github.com/Xero-Team/AstrBot`
- `查一下 xxx`
- `最近 xxxx`

等等带有搜索意味的提示让大模型触发调用搜索工具。

## 多来源检索

AstrBot 会按 `网页搜索来源`（`websearch_route`）配置的**有序列表**并行查询多个来源，对结果做 canonical URL 去重，再以 RRF（Reciprocal Rank Fusion，k=60）融合，最终通过单个 `web_search` 工具返回。列表顺序即优先级：靠前的来源在融合中权重更高。

- `websearch_route`：按优先级排列的来源列表，可多选，默认为 `["searxng", "duckduckgo"]`。
- `websearch_oversample`：每来源候选倍数，默认为 8。每个来源按 `目标结果数` $\times$ `该倍数` 取候选（并受各来源上限约束），再融合。
- 单个来源未配置、失败或超时会被跳过，不影响其他来源；全部来源都不可用时，`web_search` 会返回明确错误。

支持免 key 的 `SearXNG` 与 `DuckDuckGo`，以及需要 API Key 的 `Tavily`、`BoCha`、`百度 AI 搜索`、`Brave`、`Firecrawl`、`Exa`、`AnySearch`、`DeepSeek`、`SerpApi`。

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

进入 `配置`，下拉找到网页搜索，在 `网页搜索来源` 中选择需要的来源并排序，然后按需填写对应来源的 API Key。

## SearXNG（自托管，免 Key）

SearXNG 自身聚合 Google、Bing、DuckDuckGo 等多个引擎，是免 Key 多来源检索的首选。请先在实例的 `settings.yml` 中，将 `search.formats` 加入 `json`，否则接口会返回 `403`：

```yaml
search:
  formats:
    - html
    - json
```

然后在 `SearXNG 实例地址`（`websearch_searxng_url`）中填写实例地址，例如 `http://127.0.0.1:8080`。出于安全考虑，AstrBot 只会访问你显式配置的这个端点，不跟随重定向，也不会在服务端抓取结果 URL。

如果使用 Docker 部署，`compose-with-searxng.yml` 会启动一个已启用 `json` 的预配置 SearXNG 边车；该组合中请把实例地址填为 `http://searxng:8080`。详见[使用 Docker 部署 AstrBot](/deploy/astrbot/docker)。

## DuckDuckGo

DuckDuckGo 无需任何配置即可使用，作为免 Key 兜底来源。它通过 HTML 端点解析结果，不依赖额外依赖。

## Tavily

前往 [Tavily](https://app.tavily.com/home) 得到 API Key，然后填写在相应的配置项。

如果您使用 Tavily 作为网页搜索源之一，在 AstrBot ChatUI 上将会获得更好的体验优化，包括引用来源展示等：

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

## BoCha

前往 BoCha 平台获取 API Key，然后填写在相应的配置项。

## 百度 AI 搜索

前往百度千帆 APP Builder 获取 API Key，然后填写在相应的配置项。

## Brave

前往 Brave Search 获取 API Key，然后填写在相应的配置项。

## Firecrawl

前往 [Firecrawl](https://firecrawl.dev) 获取 API Key，然后填写在相应的配置项。

## Exa

前往 [Exa](https://dashboard.exa.ai) 获取 API Key，然后填写在相应的配置项。Exa 是一个 AI 原生搜索引擎，支持关键词和语义搜索，提供分类过滤、域名限制和日期范围等高级搜索功能。

## AnySearch

前往 [AnySearch 控制台](https://anysearch.com/console/api-keys) 获取 API Key，然后填写在相应的配置项。

AnySearch 除通用网页搜索外，还可通过服务商支持的领域标签和 `params` 对象进行垂直检索。兼容的结构化结果字段会以文本保留。`max_results` 限制为 1–10，支持的结果区域为 `cn` 和 `intl`。若 API Key 留空，将以匿名模式调用，每日有免费额度。

## SerpApi

前往 [SerpApi 控制台](https://serpapi.com/manage-api-key) 获取 API Key，然后填写在相应的配置项。SerpApi 提供 Google 网页搜索，以及 Google Images Light、Google Finance 和 Google Scholar 专用工具。只要配置了 Key 并启用网页搜索，这些专用工具就会可用，无需加入网页搜索来源列表。

## DeepSeek

前往 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 获取 API Key，然后填写在相应的配置项。DeepSeek 搜索与对话模型独立配置：即使对话模型已使用 DeepSeek，也需要单独填写搜索 Key。搜索和正文提取接口各按账号限制 5 QPS，配置多个同账号 Key 不会增加限额。

## 正文抽取

当网页搜索已启用，且来源列表中存在已配置的 `Tavily`、`Firecrawl`、`Exa` 或 `DeepSeek` 时，AstrBot 会提供单一的 `web_fetch` 工具，只接受 `url` 参数。它会按 `websearch_route` 的顺序依次尝试这些已配置来源，某个来源失败或超时后自动切换到下一个，成功后返回 `URL`、可选的 `Title` 和 `Content`。全部失败时只返回通用错误，不会暴露上游错误内容。

抽取参数固定使用各来源的默认值：Tavily 基础抽取、Firecrawl 输出 Markdown 正文、Exa 最多 3000 字符、DeepSeek 保持原请求。模型不需要选择来源，也不能传入高级抽取参数。未配置的来源，以及不支持正文抽取的来源（如 SearXNG、DuckDuckGo），不会参与。配置 SerpApi Key 后，还会提供 `image_search_serpapi`、`finance_search_serpapi` 和 `scholar_search_serpapi`。
