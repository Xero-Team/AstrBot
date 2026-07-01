# 服务提供商配置

在 WebUI 的 `服务提供商 -> + 新增服务提供商` 中配置模型服务。

> [!TIP]
> 如果你要接入的服务没有单独的适配器，但它支持 OpenAI 兼容接口，通常可以直接选择 `OpenAI`，然后通过 `API Base URL` 接入。

![image](https://files.astrbot.app/docs/source/images/llm/image.png)

![image](https://files.astrbot.app/docs/source/images/llm/image-1.png)

## 需要注意的区别

- `服务提供商` 负责登记模型接口和密钥。
- `对话` 页面负责为当前配置选择默认对话模型。
- `Agent 执行器` 是另一套能力，用于 Dify、Coze、阿里云百炼应用等第三方编排服务。

> 相应的提供商配置保存在 `data/cmd_config.json` 的 `provider` 字段中。
