# 接入 OneBot v11 协议实现

> [!TIP]
> 如果您打算将 AstrBot 接入 QQ，推荐使用 [QQ 官方机器人（WebSockets）](/platform/qqofficial/websockets)，由 QQ 官方推出，更稳定，支持一键扫码登录。

AstrBot 的 `OneBot v11`（`aiocqhttp`）平台使用**反向 WebSocket**：AstrBot 启动 WebSocket 服务，OneBot 实现作为客户端连接 AstrBot。

> [!TIP]
> 如果使用 NapCat，优先选择 AstrBot 内置的独立 [NapCat](/platform/napcat) 平台。它使用 AstrBot -> NapCat 的正向 WebSocket，配置和连接状态更直接。本页适用于必须使用通用 OneBot v11 反向 WebSocket 的实现。

常见 OneBot v11 实现包括：

- [NapCat](https://github.com/NapNeko/NapCatQQ)（QQ）
- [OneDisc](https://github.com/ITCraftDevelopmentTeam/OneDisc)（Discord）
- [Tele-KiraLink](https://github.com/Echomirix/Tele-KiraLink)（Telegram）

## 1. 在 AstrBot 中创建平台

1. 打开 AstrBot WebUI，进入 `机器人`。
2. 点击 `+ 创建机器人`，选择 `OneBot v11`。
3. 填写配置并保存。

主要字段：

- `id`：平台实例的唯一 ID。
- `enable`：启用平台。
- `ws_reverse_host`：AstrBot WebSocket 服务的**本地监听地址**，默认 `127.0.0.1`。
- `ws_reverse_port`：监听端口，默认 `6199`。
- `ws_reverse_token`：反向 WebSocket 鉴权 token。强烈建议配置，并在 OneBot 实现端使用相同值。

### 正确理解 `ws_reverse_host`

`ws_reverse_host` 不是让 OneBot 客户端填写的目标地址：

- AstrBot 与 OneBot 实现在同一台主机上时，保持 `127.0.0.1` 最安全。
- OneBot 实现在另一个容器、Pod 或主机上时，AstrBot 才需要监听可达接口。通常设为 `0.0.0.0`，也可以使用指定网卡地址。
- `0.0.0.0` 是监听通配地址，不能作为 OneBot 客户端的连接目标。

> [!CAUTION]
> 监听 `0.0.0.0` 后，请用防火墙或容器/集群网络限制来源，并设置 `ws_reverse_token`。不要把未鉴权的 OneBot WebSocket 直接暴露到公网。

## 2. 配置 OneBot 实现

在 OneBot 实现中创建反向 WebSocket 客户端，目标路径是：

```text
ws://<AstrBot可达地址>:6199/ws
```

常见地址：

- 同一主机：`ws://127.0.0.1:6199/ws`
- 同一 Docker 网络，AstrBot 服务名为 `astrbot`：`ws://astrbot:6199/ws`
- 不同主机：`ws://<AstrBot主机IP或域名>:6199/ws`

如果跨越不可信网络，请通过受保护的内网或 TLS 反向代理使用 `wss://`，不要只依赖端口公开。OneBot 实现端的 token 必须与 `ws_reverse_token` 一致。

## 3. 验证

进入 AstrBot WebUI 的 `控制台`。看到以下日志表示连接成功：

```text
aiocqhttp(OneBot v11) 适配器已连接。
```

如果没有连接日志，请依次检查：

- OneBot 实现是否启用了**反向** WebSocket 客户端。
- 客户端目标地址是否能从其所在网络访问 AstrBot，而不是误填 `0.0.0.0`。
- AstrBot 是否监听了正确接口，容器端口或防火墙是否放行。
- 两端 token 是否一致。

## NapCat 与仓库 Compose

仓库根目录的 `compose-with-napcat.yml` 当前设置了 NapCat `MODE=astrbot`。NapCat 会在每次启动时写入一个反向 WebSocket 客户端，目标是：

```text
ws://astrbot:6199/ws
```

如果保留此模式，请在 AstrBot 中创建 `OneBot v11` 平台，将 `ws_reverse_host` 设为 `0.0.0.0`、端口设为 `6199`。由于两个容器在同一个内部网络中，不需要向宿主机发布 `6199`。NapCat 的 `MODE` 模板会在每次启动时重写配置且默认 token 为空；如需持久化 token，请按 [Docker 部署](/deploy/astrbot/docker) 中的说明先移除模板模式。

如果希望使用推荐的独立 `NapCat` 平台，请在 Compose 中把 `MODE=astrbot` 改为 `MODE=ws`。然后创建 `NapCat` 平台，将 `ws_url` 填为 `ws://napcat:3001`。同一个 NapCat 实例只选择其中一种连接方式。
