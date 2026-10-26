# DeepSeek Search API

[DeepSeek Search API](https://api-docs.deepseek.com/guides/search) 使用 DeepSeek 自有搜索引擎进行网页搜索，并提供将网页抽取为 Markdown 的 Fetch 接口，帮助 AI Agent 查找并阅读实时网页内容。

本页介绍 DeepSeek Search API 的配置与使用。多来源检索、提供商对比和通用检查请参阅[网页搜索](../websearch.md)。

## 获取 API Key

1. 打开 [DeepSeek 开放平台](https://platform.deepseek.com/) 并注册或登录。
2. 打开 [API Keys 页面](https://platform.deepseek.com/api_keys)，创建并复制 Key。
3. 检查账号余额和服务可用性。Search 和 Fetch 按请求计费，当前价格与计费规则见[官方文档](https://api-docs.deepseek.com/guides/search)。

## 配置 AstrBot

对话需要使用 AstrBot 内置 AI，且对话模型及其 API 支持工具调用。运行 AstrBot 的服务器或容器需要能访问 `https://api.deepseek.com`。

1. 在侧边栏打开 `配置`，选择对话实际使用的配置文件。
2. 打开 `AI → 能力 → 网页搜索`，启用 `启用网页搜索`。
3. 将 `DeepSeek` 加入 `网页搜索来源`（`websearch_route`）。顺序决定其在融合后的 `web_search` 结果中的优先级。
4. 将 Key 添加到 `DeepSeek API Key` 列表。一个 Key 即可同时启用网页搜索和正文抽取，也可以添加多个 Key 轮换。
5. 点击右下角 `保存配置`。

这些设置只对所选配置文件生效。搜索与对话模型独立配置：可以使用其他提供商的对话模型。即使对话模型已使用 DeepSeek，也需要在此单独填写搜索 Key，可以复用同一个 Key。

## 支持的能力

| 能力               | AstrBot 返回内容                                                                                                   |
| ------------------ | ------------------------------------------------------------------------------------------------------------------ |
| 网页搜索（Search） | 标题、来源链接和摘要。AstrBot 请求 DeepSeek 候选结果时不附带正文，并在融合后的 `web_search` 结果集中最多采用 50 条 |
| 正文抽取（Fetch）  | 指定网页的 URL、标题和 Markdown 内容，支持用户提供的链接或搜索得到的链接                                           |

融合后的 `web_search` 工具默认返回 7 条结果，并接受 `max_results` 限制；结果来自 `websearch_route` 中所有已配置来源，而不只是 DeepSeek。DeepSeek 搜索只提供摘要，需要正文时请对选中的来源链接使用 `web_fetch`。实际结果数量和正文可用性取决于搜索服务和目标网站。

当来源列表中存在已配置的 `Tavily`、`Firecrawl`、`Exa` 或 `DeepSeek` 时，AstrBot 只提供一个 `web_fetch` 工具，并按 `websearch_route` 顺序尝试这些来源。因此只有前面的抽取来源失败或未配置时，才会使用 DeepSeek Fetch。

## 在对话中使用 DeepSeek Search API

保存后，向机器人或 ChatUI 发送明确请求。模型会决定是否调用工具以及使用哪些参数。若希望回答基于搜索结果，可要求它“先搜索再回答”。

### 网页搜索

```text
先搜索 AstrBot 的最新版本再回答，给出版本号、主要变更摘要和来源链接。
```

### 缩小搜索范围

搜索支持站点、语言、日期和排除运算符。请在消息中说明这些要求：

```text
搜索 GitHub 上 2026 年以来发布的 AstrBot 版本信息，最多返回 5 条并附来源链接。
```

也可以直接给出搜索表达式：

```text
使用 DeepSeek Search API 搜索：AstrBot site:github.com lang:zh,en after:2026-01-01
```

可以组合 `site:`、`-site:`、`lang:`、`after:`、`before:`、双引号精确短语和排除词（`-keyword`）。日期接受 `YYYY` 或 `YYYY-MM-DD`。包含运算符在内的完整搜索表达式不得超过 128 个字符。

### 抽取正文

```text
阅读这个页面并总结它的安装步骤：https://github.com/Xero-Team/AstrBot
```

Fetch 一次只读取一个 HTTP 或 HTTPS URL。需要登录、付费墙、站点访问策略或页面没有可抽取内容时，抽取可能失败。

## 故障排查

### 已配置 DeepSeek 对话模型，但搜索提示缺少 Key

请在当前配置文件的 `AI → 能力 → 网页搜索` 中单独填写 `DeepSeek API Key` 并保存。对话模型 Key 不会自动用于搜索。

### 余额不足或触发限流

`402` 表示账号余额不足，`429` 表示触发限流。Search 和 Fetch 的账号限额相互独立。同一账号下的多个 Key 不会提高限额，Fetch 另有单域名限制。当前数值见[官方限流说明](https://api-docs.deepseek.com/guides/search#rate-limits)。

多个 Key 会在请求间轮换。AstrBot 不会立即用另一个 Key 重试失败请求；遇到限流后请先降低请求频率再试。

### 搜索正常，但正文抽取失败

请换用无需登录的公开页面，并在 `数据与日志 → 日志` 中查看错误。Fetch 的 `403` 可能表示安全策略拒绝，`404` 可能表示没有取到可用正文。通用检查请参阅[网页搜索](../websearch.md)。
