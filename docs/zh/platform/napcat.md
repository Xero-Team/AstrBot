# 接入 NapCat

`napcat` 是 AstrBot 内置的 NapCat QQ 独立适配器，现已改为只使用 OneBot v11 正向 WebSocket。

它和通用 `OneBot v11` 适配器的区别是：

- WebUI 直接暴露 NapCat 专用配置项
- 运行时只维护一条 AstrBot -> NapCat 的正向 WebSocket 连接
- NapCat 平台动作和事件解析都走同一个连接

> [!TIP]
> 如果你只是要接入任意标准 OneBot v11 协议实现，请看 [OneBot v11](/platform/aiocqhttp)。

## 1. 准备 NapCat

请先完成 NapCat 部署，并确认：

- NapCat 已启用 OneBot v11 正向 WebSocket
- 你知道它的 WebSocket 地址，例如 `ws://127.0.0.1:3001`
- 如果 NapCat 配置了鉴权 token，你也知道对应 token

## 2. 在 AstrBot 中创建 NapCat 平台

1. 打开 AstrBot WebUI
2. 进入 `机器人`
3. 点击 `+ 创建机器人`
4. 选择 `NapCat`

至少填写这些字段：

- `id`：平台实例 ID
- `enable`：勾选启用
- `ws_url`：NapCat OneBot v11 正向 WebSocket 地址
- `token`：可选，仅在 NapCat 开启 WebSocket 鉴权时填写

高级项：

- `verify_ssl`：仅在使用自签名 WSS 证书时关闭
- `timeout_seconds`：动作响应超时
- `reconnect_interval_seconds`：断线后重连间隔
- `max_frame_size_mb`：允许接收的最大单帧大小

## 3. 合并转发的入口展开

以下开关位于全局 `platform_settings`，由 `napcat` 与 `OneBot v11`（`aiocqhttp`）共享，可在 `配置` 页设置：

- `platform_settings.onebot_forward.expand_on_ingress`：默认开启。收到只带 `forward` id、没有展开内容的合并转发时，适配器先调用 `get_forward_msg` 回填节点内容，再交给后续处理；拉取失败或超时会保留原样，不阻塞消息。
- `platform_settings.onebot_forward.max_fetch`：单条消息入口展开时递归调用 `get_forward_msg` 的最大次数，默认 8。
- `t2i.forward_card`：全局系统配置，默认开启。会话桥接把已展开的合并转发投递到**不支持**原生 `forward` 的目标时，会渲染成一张图片卡片；渲染失败时回退为带作者标签的文字转录。目标支持 `forward` 时仍重建合并转发卡片。

## 4. 在 NapCat 中确认服务

在 NapCat WebUI 中确认 OneBot v11 正向 WebSocket 服务已经开启，并且地址与 AstrBot 配置一致。

常见示例：

- 本机部署：`ws://127.0.0.1:3001`
- Docker Compose：`ws://napcat:3001`
- 同 Pod：`ws://localhost:3001`

## 5. 验证

AstrBot 启动后应看到类似日志：

```text
[NapCat] Connecting forward WebSocket to ws://127.0.0.1:3001
[NapCat] Forward WebSocket connected to ws://127.0.0.1:3001
[NapCat] Forward WebSocket adapter ready: ...
```

此时从 QQ 侧发送消息，AstrBot 应能正常收到并回复。

## 6. 常见问题

- AstrBot 能启动，但收不到消息
  - 检查 NapCat 的正向 WebSocket 服务是否真的开启
  - 检查 `ws_url` 是否可达
  - 检查 token 是否一致
- 启动检查失败
  - 检查 NapCat 是否已经登录并对外提供 WebSocket
  - 检查地址是否填成了 HTTP 地址
  - 如果使用 `wss://`，检查证书与 `verify_ssl` 配置
- Docker 内连不上
  - 优先使用容器内网络地址，例如 `ws://napcat:3001` 或 `ws://localhost:3001`
