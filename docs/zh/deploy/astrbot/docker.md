# 使用 Docker 部署 AstrBot

> [!WARNING]
> 通过 Docker 可以方便地将 AstrBot 部署到 Windows, Mac, Linux 上。
>
> 以下教程默认您的环境已安装 Docker。如果没有安装，请参考 [Docker 官方文档](https://docs.docker.com/get-docker/) 进行安装。

## 通过 Docker Compose 部署

::: details 只部署 AstrBot（通用方式）

先克隆当前仓库：

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
```

然后直接使用仓库内置的 `compose.yml`：

```bash
docker compose up -d
```

> [!TIP]
> 如果您的网络环境在中国大陆境内，上述命令将无法正常拉取。您可能需要修改 compose.yml 文件，将其中的 `image: soulter/astrbot:latest` 替换为 `image: m.daocloud.io/docker.io/soulter/astrbot:latest`。
> :::

::: details 和 NapCat 一起部署

当前仓库内置了 `compose-with-napcat.yml`，可一并拉起 AstrBot 和 NapCat。

用法如下：

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
docker compose -f compose-with-napcat.yml up -d --build
```

这个 compose 文件会把 AstrBot 和 NapCat 放到同一个内部 Docker 网络中，因此 NapCat 可以直接使用 `ws://astrbot:6199/ws` 连接 AstrBot，而不需要把反向 WebSocket 端口暴露到宿主机。

启动后：

1. 在 AstrBot WebUI 中新建 `OneBot v11` 机器人，反向 WebSocket 主机填 `0.0.0.0`，端口填 `6199`。
2. 在 NapCat WebUI 中新建反向 WebSocket 客户端，URL 填 `ws://astrbot:6199/ws`。

如果您需要沙盒运行环境，请参考 [Shipyard Neo 与 Agent 沙盒文档](/use/astrbot-agent-sandbox.md)。这个 fork 不再继续维护旧版 Shipyard 兼容路径的文档说明。
:::

## 通过 Docker 部署

```bash
mkdir astrbot
cd astrbot
sudo docker run -itd -p 6185:6185 -p 6199:6199 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot soulter/astrbot:latest
```

> [!TIP]
> 如果您的网络环境在中国大陆境内，上述命令将无法正常拉取。请使用以下命令拉取镜像：
>
> ```bash
> sudo docker run -itd -p 6185:6185 -p 6199:6199 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
> ```
>
> (感谢 DaoCloud ❤️)
>
> Windows 下不需要加 sudo，下同
>
> Windows 同步 Host Time（需要WSL2）

```text
-v \\wsl.localhost\(your-wsl-os)\etc\timezone:/etc/timezone:ro
-v \\wsl.localhost\(your-wsl-os)\etc\localtime:/etc/localtime:ro
```

通过以下命令查看 AstrBot 的日志：

```bash
sudo docker logs -f astrbot
```

## 🎉 大功告成

如果一切顺利，你会看到 AstrBot 打印出的日志。

如果没有报错，AstrBot 会在容器日志中打印 WebUI 地址以及初始登录凭据。打开对应地址即可访问管理面板。

> [!TIP]
> 由于 Docker 隔离了网络环境，所以不能使用 `localhost` 访问管理面板。
>
> 首次登录请使用启动日志中打印的随机初始密码（用户名通常为 `astrbot`）。登录后请立即修改密码。
>
> 如果部署在云服务器上，需要在相应厂商控制台里放行对应端口。

接下来，你需要部署任何一个消息平台，才能够实现在消息平台上使用 AstrBot。
