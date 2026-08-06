# Deploy AstrBot with Docker

> [!WARNING]
> This fork does not publish prebuilt Docker images. Clone this repository and build from its root `Dockerfile`, `Dockerfile.docs`, and Compose files.

## Choose a Compose File

The repository provides two locally built deployment paths:

- `compose.yml`: runs AstrBot and the locally built static documentation site. Use it for QQ Official Bot, Telegram, Discord, and other platforms, or when you manage the bot protocol implementation separately.
- `compose-with-napcat.yml`: runs AstrBot, the static documentation site, and NapCat together for personal QQ accounts. AstrBot and the documentation are still built from the local checkout; NapCat uses its official container image.

Clone the repository first:

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
```

## Allow Access to the WebUI from Outside the Container

The AstrBot WebUI listens on `127.0.0.1` by default. Inside a container, this means that publishing port `6185` alone does not make the WebUI reachable from the host.

Before starting, add the following entry under `astrbot.environment` in the Compose file you selected:

```yaml
environment:
  - TZ=Asia/Shanghai
  - ASTRBOT_DASHBOARD_HOST=0.0.0.0
```

`ASTRBOT_DASHBOARD_HOST` takes precedence over `dashboard.host` in `data/cmd_config.json`. If external access is no longer needed, remove the environment variable and restore the configured host to a loopback address.

> [!CAUTION]
> `0.0.0.0` makes the WebUI listen on every container interface. Do not expose the admin panel directly to the public internet. Restrict firewall access and use a reverse proxy, HTTPS, a strong password, and TOTP.

## Start AstrBot and the Documentation Site

The root `compose.yml` builds the current checkout as the local images `astrbot:local` and `astrbot-docs:local`:

```bash
docker compose up -d --build
docker compose logs -f astrbot docs
```

Its default mount and published ports are:

- `./data` -> `/AstrBot/data`: configuration, database, plugins, and other runtime data.
- `6185:6185`: AstrBot WebUI.
- `6199:6199`: optional OneBot v11 reverse WebSocket endpoint.
- `6186:8080`: the locally built documentation site, available at `http://localhost:6186`.

The documentation is an independent read-only static service. It neither reads `data/` nor shares the WebUI login state. Publish port `6186` only when you need to serve the documentation externally, and protect it with firewall rules or an HTTPS reverse proxy as appropriate.

Publishing `6199` does not change the OneBot listener address. Only set that platform's `ws_reverse_host` to `0.0.0.0` when its OneBot client runs outside the AstrBot container. Also configure `ws_reverse_token` and restrict network access to the port.

## Development CLIs and Host Privileges

The source-built AstrBot image preinstalls the Claude Code `claude` CLI and the OpenAI Codex CLI as development tools; neither is a built-in AstrBot Agent Runner. The BTW conversation loop does not receive shell, filesystem, or sandbox tools, while plugin LLM tools and MCP tools default to the work loop. External plugins can still launch these CLIs directly, so install only trusted plugins and review their BTW loop assignment and working directory.

Do not commit long-lived Claude Code, Codex, or other service credentials to the repository or bake them into image layers. If you use `.docker-local/` to place local configuration under `/root`, verify that it remains uncommitted, that the resulting image is not distributed, and that credentials and writable workspaces follow least privilege.

`compose-with-napcat.yml` mounts `/var/run/docker.sock` into the AstrBot container by default for local capabilities that need Docker. A process with access to that socket can usually gain near-root control of the host. Remove the mount when those capabilities are not needed; otherwise treat Dashboard access, administrator accounts, and plugin installation as a privileged management surface.

## Start AstrBot and NapCat Together

First add `ASTRBOT_DASHBOARD_HOST=0.0.0.0` to `compose-with-napcat.yml` as described above.

The file currently also sets NapCat `MODE=astrbot`. On every NapCat startup, that mode writes a **reverse** WebSocket client targeting `ws://astrbot:6199/ws`. To use AstrBot's currently recommended dedicated `NapCat` platform, change it first to:

```yaml
- MODE=ws
```

`MODE=ws` starts a OneBot v11 forward WebSocket server on `0.0.0.0:3001`. Then start the stack:

```bash
docker compose -f compose-with-napcat.yml up -d --build
docker compose -f compose-with-napcat.yml logs -f astrbot docs napcat
```

On Linux, you can run NapCat with your host user's UID/GID to reduce bind-mount permission issues:

```bash
NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) \
  docker compose -f compose-with-napcat.yml up -d --build
```

This Compose file publishes:

- `6185`: AstrBot WebUI.
- `6186`: the locally built documentation site.
- `6099`: NapCat WebUI.

It persists:

- `./data`
- `./napcat/config`
- `./ntqq`

AstrBot and NapCat share an internal Docker network. With `MODE=ws`, create the dedicated `NapCat` platform in AstrBot and set `ws_url` to `ws://napcat:3001`. If NapCat's forward WebSocket uses a token, configure the same token on both sides. This path does not require publishing a QQ WebSocket port to the host.

> [!NOTE]
> NapCat `MODE` selects a startup template and rewrites `onebot11.json` on every start; the template token is empty. To persist a custom token, start once with `MODE=ws`, remove `MODE` from the Compose file, and then set the token in NapCat WebUI. The resulting configuration remains under `./napcat/config`.

If you retain the Compose file's original `MODE=astrbot`, do not create the dedicated `NapCat` platform. Create `OneBot v11`, set `ws_reverse_host` to `0.0.0.0`, and keep port `6199`. It only needs to be reachable on the internal Docker network and does not need to be published to the host. For authentication, likewise remove `MODE` after the initial configuration is generated, then set the same token in NapCat and AstrBot.

## First Login and Updates

On first startup, AstrBot prints the WebUI address and a random initial password in its logs. The default username is `astrbot`. Change the password immediately after logging in.

To update, back up `data/`, pull the latest code, and rebuild the selected service:

```bash
git pull --ff-only
docker compose up -d --build
```

For the NapCat stack, use:

```bash
git pull --ff-only
docker compose -f compose-with-napcat.yml up -d --build
```
