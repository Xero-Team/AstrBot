# 插件

AstrBot 把插件称为 Star。插件可以注册指令、工具、事件监听，以及可选的 Dashboard 页面。

入口：侧栏 **插件**。配置档里的可用插件列表在 **配置文件 → 插件配置**。开发请看 [插件开发指南](/dev/star/plugin-new)。

## 在 WebUI 里管理

**已安装** 标签可以启用、禁用、重载、卸载插件，并查看加载错误。

加载、卸载、重载或启禁后，AstrBot 会立即重建指令 catalog，并刷新已启用的 Telegram / Discord 原生命令入口，不必等下一条消息。

如果插件加载失败，面板会显示错误，并提供 **尝试一键重载修复**。先补依赖或改代码，再点重载，不必重启整个进程。

右下角 **+** 可以用仓库 URL 或本地文件安装。仓库 URL 含 `&`、`#` 时请加引号，指令安装同样如此。

启用、禁用需要 `extension.manage`。从 URL 安装需要 `extension.plugin_install`，并且会弹出 Dashboard 二次验证（step-up）。见 [授权管理](./authorization)。

## 插件市场

**插件市场** 的默认源是上游兼容源，不是本 fork 的官方市场：

1. 先请求上游 `cloud.astrbot.app` 市场 JSON；
2. 失败后再回退到 `AstrBotDevs/AstrBot_Plugins_Collection` 及其 CDN。

能在市场里搜到，不等于能在本分支运行。本 fork 要求 Python 3.14+，并且不兼容旧插件 API。

安装前检查插件元数据里的 `astrbot_version`。需要 Dashboard 页面的插件必须同时声明：

- `requires.dashboard_extension: 1`
- Extension Protocol v1 的 `assets.v1.json` 清单

不兼容时改用 URL / 文件安装，或放弃该插件。本 fork 与上游都不保证第三方插件的安全性。扩展协议见 [Dashboard 扩展](/dev/star/plugin-dashboard-extension)。

## 配置档里的可用插件

配置档字段 `plugin_set` 默认 `["*"]`，表示使用全部**未被插件页禁用**的插件。空列表表示这个配置档不使用任何插件。

优先级：

1. 插件页全局禁用：配置档勾选无效。
2. 配置档 `plugin_set`：限制该档能用的插件。
3. [自定义规则](./custom-rules) 的会话插件列表：再按 UMO 收窄。

不同配置档可以启用不同插件集。改完保存后，该档的指令 catalog 会重建。

## 指令

- `/plugin list`：列出当前已加载插件。
- `/plugin show <插件名>`：查看版本、作者和已注册指令。
- `/plugin disable <插件名>`：停用，需要 `extension.manage`。
- `/plugin enable <插件名>`：启用，需要 `extension.manage`。
- `/plugin install <仓库 URL>`：安装，需要 `extension.plugin_install` 和 Dashboard step-up。

只输入 `/plugin` 会显示子指令树。例如：

```text
/plugin install 'https://example.com/plugin.git?ref=main&source=manual#install'
```

旧短名 `/plugin ls` 不是别名，不会匹配。见 [内置指令](./command)。

## 常见误配

1. 市场里安装成功，启动日志却报 Python 版本或 API 不兼容。
2. 插件页已禁用，却在配置档 `plugin_set` 里反复勾选。
3. 插件提供了 Dashboard 页，但没有声明 `requires.dashboard_extension: 1`，页面不会出现。
4. 用 IM 消息安装插件，但当前账户没有 step-up 资格。
