# 使用 Docker 部署 AstrBot

> [!WARNING]
> 当前 fork 不发布官方 Docker 镜像。Docker 部署请直接使用本仓库源码进行本地构建。

## 推荐方式

当前维护中的 Docker 路径以 `compose-with-napcat.yml` 为准。它会从本仓库的 `Dockerfile` 本地构建 AstrBot 容器，而不是拉取上游镜像。

先克隆仓库：

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
```

## 只启动 AstrBot

如果你只想启动 AstrBot 本体，可以只拉起 `astrbot` 服务：

```bash
docker compose -f compose-with-napcat.yml up -d --build astrbot
```

启动后可通过以下命令查看日志：

```bash
docker compose -f compose-with-napcat.yml logs -f astrbot
```

## 同时启动 AstrBot 和 NapCat

如果你还需要 OneBot v11 + NapCat，一并拉起整套 Compose：

```bash
docker compose -f compose-with-napcat.yml up -d --build
```

这个 Compose 文件会：

- 本地构建 AstrBot 镜像
- 拉起官方 NapCat 容器
- 让 AstrBot 与 NapCat 在同一个内部 Docker 网络中通信

默认端口：

- `6185`：AstrBot WebUI
- `6099`：NapCat WebUI

默认持久化目录：

- `./data`
- `./napcat/config`
- `./ntqq`

## NapCat 连接说明

容器启动后：

1. 在 AstrBot WebUI 中新建 `OneBot v11` 机器人，反向 WebSocket 主机填 `0.0.0.0`，端口填 `6199`。
2. 在 NapCat WebUI 中新建反向 WebSocket 客户端，URL 填 `ws://astrbot:6199/ws`。

由于两个容器在同一个内部网络中，NapCat 不需要通过宿主机地址回连 AstrBot。

## 不推荐的旧路径

以下方式不再作为当前 fork 的 Docker 部署说明：

- 直接使用 `soulter/astrbot:latest`
- 使用镜像站替换上游镜像
- 基于 `docker run` 手写容器命令部署当前 fork

这些路径对应的不是当前仓库维护方式，容易与本 fork 的代码、依赖和前端产物脱节。

## 启动后

如果没有报错，AstrBot 会在容器日志中打印 WebUI 地址以及初始登录凭据。打开对应地址即可访问管理面板。

> [!TIP]
> 首次登录请使用启动日志中打印的随机初始密码（用户名通常为 `astrbot`）。登录后请立即修改密码。

如果需要更新，拉取仓库最新代码后重新执行：

```bash
git pull
docker compose -f compose-with-napcat.yml up -d --build astrbot
```
