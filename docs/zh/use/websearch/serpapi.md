# SerpApi

[SerpApi](https://serpapi.com/) 提供来自 Google、Bing、百度等搜索引擎的结构化实时搜索数据，让 AI Agent 无需自行维护网页抓取设施即可获取实时信息。

本页介绍 SerpApi 的配置与使用。多来源检索、提供商对比和通用检查请参阅[网页搜索](../websearch.md)。

## 获取 API Key

1. 打开 [SerpApi](https://serpapi.com/) 并注册或登录。
2. 打开 [API Key 页面](https://serpapi.com/manage-api-key) 并复制 Key。
3. 确认账号仍有搜索额度。当前额度、计费和服务可用性以 SerpApi 网站及账号信息为准。

## 配置 AstrBot

对话需要使用 AstrBot 内置 AI，且对话模型及其 API 支持工具调用。运行 AstrBot 的服务器或容器需要能访问 `https://serpapi.com`。

1. 在侧边栏打开 `配置`，选择对话实际使用的配置文件。
2. 打开 `AI → 能力 → 网页搜索`，启用 `启用网页搜索`。
3. 可选：将 `SerpApi` 加入 `网页搜索来源`（`websearch_route`），以便参与融合后的 `web_search` 结果；配置 Key 后其专用工具即可使用。
4. 将 Key 添加到 `SerpApi API Key` 列表。一个 Key 即可启用下列全部能力，也可以添加多个 Key 轮换。
5. 点击右下角 `保存配置`。

这些设置只对所选配置文件生效。多个 Key 会轮换使用，认证或额度错误时会尝试下一个 Key。

## 支持的能力

| 能力     | SerpApi 接口                                                           | AstrBot 返回内容                                                                    |
| -------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 网页搜索 | [Google Search API](https://serpapi.com/search-api)                    | 首页结果的标题、来源链接和摘要；默认最多 5 条，可请求最多 10 条                     |
| 图片搜索 | [Google Images Light API](https://serpapi.com/google-images-light-api) | 图片直链、缩略图、来源页面和可用尺寸；默认最多 5 张，可请求最多 10 张               |
| 财经查询 | [Google Finance API](https://serpapi.com/google-finance-api)           | 可用的报价、货币、时间戳、财务数据和新闻；请求时间区间时返回报价摘要和可用价格序列  |
| 学术搜索 | [Google Scholar API](https://serpapi.com/google-scholar-api)           | 论文标题、摘要、出版信息、引用次数和可用的全文链接；默认最多 5 篇，可请求最多 20 篇 |

实际结果数量和可用字段取决于搜索响应，可能少于请求值。网页和图片搜索支持国家与界面语言设置；网页搜索还支持搜索位置，学术搜索支持出版年份筛选。请在消息中说明这些要求，以便模型传给工具。

配置 Key 并启用网页搜索后，图片、财经和学术专用工具会自动挂载，无需加入 `websearch_route`。

## 在对话中使用 SerpApi

保存后，向机器人或 ChatUI 发送明确的搜索请求。模型会自行选择工具和参数。若希望回答基于搜索结果，可要求它“先搜索再回答”。

### 网页搜索

```text
搜索 AstrBot 的最新版本，给出版本号、主要变更摘要和来源链接。
```

网页搜索返回标题、链接和摘要，不会自动读取完整网页。AstrBot 的 SerpApi 集成不提供正文抽取工具。若经常需要总结某个链接，请在[网页搜索](../websearch.md#正文抽取)中配置支持正文抽取的来源。

### 图片搜索

```text
找三张咖啡的图片，并附上来源页面。
```

图片结果包含图片直链和来源页面。是否展示或发送图片取决于模型后续操作和消息平台。

### 财经查询

```text
查询 Google Finance 上 AAPL:NASDAQ 的报价，并给出报价时间戳。
```

财经查询支持 `AAPL:NASDAQ`、`.INX:INDEXSP`、`BTC-USD`、`EUR-USD` 等代码。需要历史价格时请指定时间区间：

```text
查询 AAPL:NASDAQ 最近一个月在 Google Finance 的价格历史，并附上来源。
```

支持的历史区间为 `1D`、`5D`、`1M`、`6M`、`YTD`、`1Y`、`5Y` 和 `MAX`。指定历史区间时，接口返回报价摘要和可用价格序列，而不是完整财务数据和新闻。

### 学术搜索

```text
在 Google Scholar 搜索 2023 年以来关于检索增强生成的论文，包含引用次数和可用的 PDF 链接。
```

可以指定出版年份范围，最多请求 20 篇论文。摘要不是论文全文；PDF 等全文链接仅在搜索结果提供时返回。

## 故障排查

### Key 无效、额度错误或超时

确认已填写 SerpApi Key，并检查账号剩余额度。在 `数据与日志 → 日志` 中查看错误。若为超时，请检查 AstrBot 所在环境能否访问 SerpApi API。通用的多来源检查请参阅[网页搜索](../websearch.md)。

### 模型不使用图片、财经或学术搜索

确认当前配置文件已启用网页搜索、SerpApi Key 已保存，并明确要求图片搜索、Google Finance 或 Google Scholar。四个工具共用同一配置，无需额外开关；是否调用仍由模型决定。
