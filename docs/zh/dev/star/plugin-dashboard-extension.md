---
outline: deep
---

# Plugin Dashboard Extension 开发指南

Dashboard Extension Protocol v1 允许插件在 AstrBot Dashboard 中提供独立页面，并通过
宿主管理的 Action 调用插件 Python 代码。页面运行在只有 `allow-scripts` 的 sandboxed
iframe 中，不能读取 Dashboard DOM、Cookie、localStorage 或认证信息，也不能直接请求
Dashboard API 或外部网络。

插件页面只通过 `window.AstrBotPluginPage` 调用 manifest 明确允许的 Action。插件不能提交
目标 URL、HTTP 方法、请求头或服务器绝对路径。

## 最小目录结构

仓库中的可执行最小示例位于
`tests/fixtures/plugins/dashboard_extension_example/`：

```text
dashboard_extension_example/
  main.py
  metadata.yaml
  pages/
    settings/
      app.js
      assets.v1.json
```

Page 不提供自己的 HTML。AstrBot 生成固定安全 Shell，再加载 manifest 中声明的 module 和
styles。

## 声明 metadata capability

Dashboard Extension 必须在 `metadata.yaml` 中同时声明
`requires.dashboard_extension: 1` 和 `dashboard`。这两个字段必须成对出现；未知协议版本、
旧的 top-level `pages` 或未知字段都会使插件加载失败。

```yaml
name: dashboard_extension_example
display_name: Dashboard Extension Example
author: Xero-Team
version: 1.0.0
desc: Minimal Dashboard Extension Protocol v1 example plugin
astrbot_version: '>=4.26.6'
requires:
  dashboard_extension: 1
dashboard:
  extension_id: team.xero.astrbot-dashboard-extension-example
  pages:
    - id: settings
      title: Settings
      module: pages/settings/app.js
      assets_manifest: pages/settings/assets.v1.json
      icon: mdi-view-dashboard-outline
      actions:
        - settings.read
```

### 字段约束

- `dashboard.extension_id` 是安装、重命名和升级时保持不变的扩展身份。它必须是 3–128 个
  小写 ASCII 字符，由至少两个点分 label 组成；每个 label 必须匹配
  <code>^[a-z0-9]&lpar;?:[a-z0-9-]{0,61}[a-z0-9])?$</code>。不要从可变的插件目录名动态生成它。
- `page.id` 必须匹配 `^[a-z][a-z0-9-]{0,47}$`，同一扩展内不能重复。
- `page.title` 长度为 1–80 个字符。
- `page.module` 必须是 `.js` 或 `.mjs` 文件。
- `page.styles` 可选，最多 8 个不重复的 `.css` 文件。
- `page.icon` 可选，使用 Dashboard 支持的 MDI 图标名。
- `page.actions` 最多 64 个，不能重复。Action ID 最长 64 个字符，必须匹配
  `^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`。
- 一个 extension 至少声明一个 Page。每个 Page 引用的 Action 都必须在插件
  `initialize()` 期间成功注册。

## 创建 assets manifest

每个 Page 都必须提供独立的 `assets.v1.json`。它是该 Page 可访问静态文件的完整
allowlist，而不是构建产物的提示信息：module、styles、动态 import、图片、字体和其他运行时
资源都必须逐项列出。

```json
{
  "version": 1,
  "files": [
    {
      "path": "pages/settings/app.js",
      "sha256": "34151ab52abbc2cfdde2b611e63e9f22190e27d656301c60af398a10fbadf079",
      "size": 676
    }
  ]
}
```

`sha256` 必须是文件原始字节的 64 位小写十六进制摘要，`size` 必须是同一文件的精确字节
数。插件加载时和每次 bundle 读取时都会重新检查路径 containment、类型、size 和 digest；
任何不一致都会 fail closed。

资源路径必须是相对插件根目录的普通路径。绝对路径、`..`、反斜杠、编码路径、NUL、隐藏
段、尾随点或空格、Windows drive/UNC/ADS、symlink 逃逸，以及大小写或 Unicode
规范化碰撞都会被拒绝。

单文件上限为 16 MiB，每个 Page 总计 32 MiB、最多 256 个文件。允许的后缀为：

```text
.js .mjs .css .json .png .jpg .jpeg .gif .webp .ico
.woff .woff2 .ttf
```

SVG、WASM 和 source map 不会被服务。构建器必须输出确定性的文件列表，并在每次前端构建
后重新生成 size/digest；不要手工保留旧摘要。

## 注册 Python Action

只从公共 SDK `astrbot.api.dashboard` 导入 Dashboard 类型。Action 注册只能发生在
`initialize()` 内；构造函数注册会失败。AstrBot 对整个 initialize 使用 staging
transaction，任何 manifest、Action 或 handler 校验失败都不会留下部分可用的扩展。

```python
from pydantic import BaseModel, ConfigDict

from astrbot.api.dashboard import (
    DashboardActionContext,
    DashboardJsonAction,
)
from astrbot.api.star import Star


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingsResult(BaseModel):
    message: str


class DashboardExtensionExample(Star):
    async def initialize(self) -> None:
        registrar = self.context.dashboard_extensions.for_plugin(self)
        registrar.register_json(
            DashboardJsonAction(
                name="settings.read",
                input_model=SettingsRequest,
                output_model=SettingsResult,
                description="Read the example Dashboard settings",
            ),
            self.read_settings,
        )

    async def read_settings(
        self,
        _payload: SettingsRequest,
        _context: DashboardActionContext,
    ) -> SettingsResult:
        return SettingsResult(message="Dashboard Extension Protocol v1 is ready")
```

输入或上传 fields model 必须是 Pydantic v2 `BaseModel`，并设置
`ConfigDict(extra="forbid")`。输出也必须是 `BaseModel`，返回值会再次按声明的 output model
校验。不要返回 `Response`、重定向、响应头或任意状态码。

### Action 类型

| 类型       | 注册方法          | handler 签名                           | 页面 SDK                    |
| ---------- | ----------------- | -------------------------------------- | --------------------------- |
| JSON       | `register_json`   | `(payload, context) -> BaseModel`      | `invoke()`                  |
| 单文件上传 | `register_upload` | `(file, fields, context) -> BaseModel` | `upload()`                  |
| 文件读取   | `register_file`   | `(payload, context) -> DashboardFile`  | `readFile()` / `download()` |

`DashboardJsonAction` 声明 `input_model` 和 `output_model`。
`DashboardUploadAction` 声明 `fields_model`、`output_model`、
`max_file_bytes`、`allowed_content_types` 和 `allowed_extensions`。上传上限必须在 1 byte–64
MiB 之间；MIME 必须是小写精确值，不能使用 wildcard 或参数；扩展名必须是小写的
`.ext`。

`DashboardFileAction` 声明 `input_model`、`disposition`、`max_file_bytes` 和
`allowed_content_types`。`disposition="inline"` 用于 `readFile()`，上限 32 MiB；
`disposition="attachment"` 用于 `download()`，上限 128 MiB。handler 返回：

```python
from pathlib import Path

from astrbot.api.dashboard import DashboardFile

return DashboardFile(
    relative_path=Path("exports/result.json"),
    filename="result.json",
    content_type="application/json",
)
```

`relative_path` 必须指向插件根目录内已经存在的普通文件，不能是绝对路径或 traversal。
宿主会再次检查 containment、文件大小和 MIME，并通过短期、owner-bound 的 file ticket
流式提供文件。

所有 Action 都可以声明：

- `required_scope`：默认 `plugin`，只能使用 `bot`、`provider`、`prompt`、`im`、
  `config`、`chat`、`kb`、`memory`、`data`、`file`、`plugin`、`mcp`、`skill`。
- `timeout_seconds`：5–120 秒，默认 30 秒。
- `description`：最多 200 个字符。

`DashboardActionContext` 提供 `request_id`、`username`、`scopes`、`extension_id`、
`plugin_name` 和 `cancellation`。长任务应定期检查 `cancellation.cancelled`，或等待
`cancellation.wait()`，并在取消后尽快停止。可预期且可安全展示的业务错误使用：

```python
from astrbot.api.dashboard import DashboardActionError

raise DashboardActionError("invalid_palette", "The selected palette is invalid")
```

其他异常只会向页面返回通用错误；不要把 token、路径、URL、上传内容或敏感配置写入异常
消息。

`DashboardUploadedFile` 只在 handler 调用期间有效，提供 `filename`、`content_type`、`size`
和异步 `iter_chunks()`。需要保留内容时，应在 handler 返回前按块复制到插件拥有的位置。

## 编写 Page module

固定 Shell 会在 module 执行前安装 `window.AstrBotPluginPage`。先等待 `ready()`，再创建 UI
和调用 Action：

```js
const api = window.AstrBotPluginPage;
const context = await api.ready();

const button = document.createElement('button');
button.textContent = `Read settings for ${context.plugin_name}`;
button.addEventListener('click', async () => {
  try {
    const result = await api.invoke('settings.read', {});
    console.log(result.message);
  } catch (error) {
    console.error(error.code, error.message, error.request_id);
  }
});
document.body.append(button);
```

浏览器 SDK 提供：

- `ready()`：返回初始 context。
- `invoke(actionId, payload)`：调用 JSON Action。
- `upload(actionId, file, fields)`：调用单文件上传 Action。
- `readFile(actionId, payload)`：读取 `inline` 文件，返回包含 `bytes`、`filename`、
  `contentType`、`size` 和 `disposition` 的对象。
- `download(actionId, payload)`：触发 `attachment` 流式下载。
- `createObjectURL(file)` / `revokeObjectURL(url)`：为 `readFile()` 结果创建并回收受 SDK
  跟踪的 object URL。
- `onContext(listener)`：订阅 theme 和 locale 等 context 更新，返回取消订阅函数。
- `dispose()`：主动关闭当前 Page 实例并拒绝 pending 请求。

context 包含 `protocol_version`、`extension_id`、`plugin_name`、`page_id`、
`instance_id`、`plugin_generation`、`expires_at`、`locale`、`theme` 和
`capabilities`。只能把 `capabilities.actions` 中列出的 Action 当作当前页面可用能力。

Page 最多同时保留 64 个 pending 请求；Bridge JSON 消息最大 256 KiB。Host 会处理超时、
取消、generation 变化、logout、reload、disable、uninstall 和路由离开。Promise 拒绝值是
`Error`，并带有 `code`、`retryable` 和可选 `request_id`。

使用 `createObjectURL()` 创建的 URL 会在显式 revoke 或 Page dispose 时回收。插件自己调用
浏览器 `URL.createObjectURL()` 得到的 URL 不受 SDK 管理，必须自行回收。

## 安全与生命周期边界

- iframe 固定为 `sandbox="allow-scripts"`，不能请求 `allow-same-origin`、
  `allow-forms`、`allow-popups` 或 `allow-downloads`。
- CSP 只允许当前 content-addressed bundle 和固定 SDK；外部 script、fetch、beacon、
  WebSocket、frame、object 和表单提交会被阻止。
- 不要直接使用 `fetch()` 访问 Dashboard API。所有特权操作都必须设计成结构化 Action。
- 不要把用户数据、token、session/ticket handle 或绝对文件路径放进静态 bundle、URL、DOM
  日志或 Action 错误。
- 插件 reload、disable、uninstall 和 AstrBot shutdown 会使旧 generation 的 Action、Page
  session 和 file ticket 失效。页面必须允许宿主随时 dispose，不能依赖跨 generation 状态。
- Python 插件仍在 AstrBot 主进程中运行。iframe 是浏览器侧隔离，不是 Python 沙箱。

## 本地验证

修改 Page 资源后，重新生成 `assets.v1.json`，再从 Dashboard 重载插件。开发期间至少验证：

1. metadata capability、extension ID、Page/Action ID 和 assets digest 能通过加载。
2. 页面只能调用 allowlist 中的 Action。
3. JSON 输入和输出都通过 Pydantic schema。
4. 上传的 MIME、扩展名和实际内容符合声明。
5. inline object URL 被回收，attachment 能完成流式下载。
6. reload、disable、uninstall 和 logout 后旧页面不再调用成功。

协议是 breaking contract，不提供旧 Page metadata、任意 HTTP proxy 或旧插件运行时 API 的
兼容层。迁移现有插件时必须直接改用本指南描述的 v1 manifest、Action 和 Page SDK。
