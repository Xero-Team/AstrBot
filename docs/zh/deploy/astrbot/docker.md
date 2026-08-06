# 使用 Docker 部署 AstrBot

> [!WARNING]
> 当前 fork 不发布预构建 Docker 镜像。请从本仓库克隆源码，并使用仓库根目录的 `Dockerfile`、`Dockerfile.docs` 和 Compose 文件在本地构建。

## 选择 Compose 文件

仓库提供两条本地构建路径：

- `compose.yml`：运行 AstrBot 和本仓库构建的静态文档站点，适合接入 QQ 官方机器人、Telegram、Discord 等平台，或独立管理其他机器人协议端。
- `compose-with-napcat.yml`：运行 AstrBot、静态文档站点和 NapCat，适合 QQ 个人号；AstrBot 与文档仍由本地源码构建，NapCat 使用其官方容器镜像。

先克隆仓库：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
```

## 允许容器外访问 WebUI

AstrBot 的 WebUI 默认只监听 `127.0.0.1`。在容器里，这意味着即使 Compose 发布了 `6185` 端口，宿主机也无法通过该端口访问。

启动前，请在所选 Compose 文件的 `astrbot.environment` 中加入：

```yaml
environment:
  - TZ=Asia/Shanghai
  - ASTRBOT_DASHBOARD_HOST=0.0.0.0
```

`ASTRBOT_DASHBOARD_HOST` 的优先级高于 `data/cmd_config.json` 中的 `dashboard.host`。如果以后不再需要容器外访问，请删除该环境变量，并将配置恢复为环回地址。

> [!CAUTION]
> `0.0.0.0` 会让 WebUI 监听容器的所有网络接口。不要把管理面板无保护地暴露到公网；至少应限制防火墙来源，并使用反向代理、HTTPS、强密码和 TOTP。

## 启动 AstrBot 和文档

根 `compose.yml` 会把当前仓库构建为本地镜像 `astrbot:local` 和 `astrbot-docs:local`：

```bash
docker compose up -d --build
docker compose logs -f astrbot docs
```

默认挂载和端口为：

- `./data` -> `/AstrBot/data`：配置、数据库、插件等运行时数据。
- `6185:6185`：AstrBot WebUI。
- `6199:6199`：可选的 OneBot v11 反向 WebSocket 入口。
- `6186:8080`：本仓库构建的文档站点，可通过 `http://localhost:6186` 访问。

文档是独立的只读静态服务，不读取 `data/`，也不复用 WebUI 的登录状态。仅在需要对外提供文档时才发布 `6186`，并按部署环境使用防火墙或 HTTPS 反向代理保护该端口。

发布 `6199` 并不会自动让 OneBot 入口监听外部接口。仅当 OneBot 客户端位于 AstrBot 容器之外时，才把该平台的 `ws_reverse_host` 改为 `0.0.0.0`；同时配置 `ws_reverse_token`，并限制端口的网络访问范围。

## 镜像内的开发 CLI 与主机权限

源码构建的 AstrBot 镜像预装 Claude Code 的 `claude` CLI 和 OpenAI Codex CLI，定位是容器内开发工具，不是 AstrBot 内置 Agent Runner。BTW 对话循环不会获得 Shell、文件或沙箱工具；插件 LLM 工具和 MCP 工具也默认只在工作循环可用。外部插件仍可直接启动这些 CLI，因此只安装可信插件，并检查其 BTW 循环分配和工作目录。

不要把 Claude Code、Codex 或其他服务的长期凭据提交到仓库或烘焙进镜像层。若使用 `.docker-local/` 向 `/root` 提供本地配置，要确认该目录未被提交、构建产物不会被分发，并按最小权限管理凭据和可写工作区。

`compose-with-napcat.yml` 默认把 `/var/run/docker.sock` 挂载到 AstrBot 容器，以支持需要 Docker 的本地能力。能够访问该 socket 的进程通常可以获得接近宿主机 root 的控制权；如果不使用这类能力，请删除该挂载。保留时应把 Dashboard、管理员账号和插件安装权限视为高权限管理面。

## 同时启动 AstrBot 和 NapCat

先按上文在 `compose-with-napcat.yml` 中加入 `ASTRBOT_DASHBOARD_HOST=0.0.0.0`。

当前文件还为 NapCat 设置了 `MODE=astrbot`。该模式会在 NapCat 每次启动时写入一个连接 `ws://astrbot:6199/ws` 的**反向** WebSocket 客户端。如果要使用 AstrBot 当前推荐的独立 `NapCat` 平台，请先将它改成：

```yaml
- MODE=ws
```

`MODE=ws` 会让 NapCat 启动监听 `0.0.0.0:3001` 的 OneBot v11 正向 WebSocket 服务。然后启动：

```bash
docker compose -f compose-with-napcat.yml up -d --build
docker compose -f compose-with-napcat.yml logs -f astrbot docs napcat
```

Linux 上可让 NapCat 使用当前宿主用户的 UID/GID，以减少挂载目录权限问题：

```bash
NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) \
  docker compose -f compose-with-napcat.yml up -d --build
```

该 Compose 默认发布：

- `6185`：AstrBot WebUI。
- `6186`：本仓库构建的文档站点。
- `6099`：NapCat WebUI。

并持久化：

- `./data`
- `./napcat/config`
- `./ntqq`

AstrBot 与 NapCat 位于同一个 Docker 网络。使用 `MODE=ws` 时，请在 AstrBot 中创建独立的 `NapCat` 平台，将 `ws_url` 填为 `ws://napcat:3001`；如果 NapCat 的正向 WebSocket 配置了 token，两端必须填写同一个值。此路径不需要向宿主机发布 QQ WebSocket 端口。

> [!NOTE]
> NapCat 的 `MODE` 是启动模板选择器，会在每次启动时重写 `onebot11.json`，模板中的 token 为空。如果需要自定义并持久化 token，可先用 `MODE=ws` 启动一次生成配置，再从 Compose 删除 `MODE`，然后在 NapCat WebUI 中设置 token；配置会保存在 `./napcat/config`。

如果保留 Compose 原有的 `MODE=astrbot`，则不要创建独立 `NapCat` 平台。请创建 `OneBot v11` 平台，将 `ws_reverse_host` 设为 `0.0.0.0`，端口保持 `6199`。`6199` 只需在内部 Docker 网络可达，不需要发布到宿主机。如需鉴权，同样要在第一次生成配置后从 Compose 删除 `MODE`，再在 NapCat 与 AstrBot 两端设置相同 token。

## 首次登录和更新

首次启动时，AstrBot 会在日志中打印 WebUI 地址和随机初始密码，默认用户名为 `astrbot`。登录后请立即修改密码。

更新时先备份 `data/`，再拉取代码并重新构建所用服务：

```bash
git pull --ff-only
docker compose up -d --build
```

NapCat 组合部署则使用：

```bash
git pull --ff-only
docker compose -f compose-with-napcat.yml up -d --build
```
