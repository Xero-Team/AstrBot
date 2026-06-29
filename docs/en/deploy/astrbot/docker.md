# Deploy AstrBot with Docker

> [!WARNING]
> Docker provides a convenient way to deploy AstrBot on Windows, Mac, and Linux.
>
> This tutorial assumes you have Docker installed in your environment. If not, please refer to the [Docker official documentation](https://docs.docker.com/get-docker/) for installation.

## Deploy with Docker Compose

::: details Deploy AstrBot Only (General Method)

Clone this repository first:

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
```

Then start the repository's built-in `compose.yml`:

```bash
docker compose up -d
```

> [!TIP]
> If your network environment is in mainland China, the above command will not pull properly. You may need to modify the compose.yml file and replace `image: soulter/astrbot:latest` with `image: m.daocloud.io/docker.io/soulter/astrbot:latest`.
> :::

::: details Deploy AstrBot and NapCat Together

This repository also ships `compose-with-napcat.yml` for a combined AstrBot + NapCat setup.

Usage:

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
docker compose -f compose-with-napcat.yml up -d --build
```

This compose file keeps AstrBot and NapCat on the same internal Docker network, so NapCat can connect to AstrBot through `ws://astrbot:6199/ws` without exposing the reverse WebSocket port to the host.

After the containers are up:

1. In AstrBot WebUI, create a `OneBot v11` bot with reverse WebSocket host `0.0.0.0` and port `6199`.
2. In NapCat WebUI, add a reverse WebSocket client pointing to `ws://astrbot:6199/ws`.

If you need the sandbox runtime, use the [Shipyard Neo guide](/en/use/astrbot-agent-sandbox.md). This fork no longer documents the legacy Shipyard compatibility path.
:::

## Deploy with Docker

```bash
mkdir astrbot
cd astrbot
sudo docker run -itd -p 6185:6185 -p 6199:6199 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot soulter/astrbot:latest
```

> [!TIP]
> If your network environment is in mainland China, the above command will not pull properly. Please use the following command to pull the image:
>
> ```bash
> sudo docker run -itd -p 6185:6185 -p 6199:6199 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
> ```
>
> (Thanks to DaoCloud ❤️)

> No need to add sudo on Windows, same below
> Sync Host Time on Windows (requires WSL2)

```text
-v \\wsl.localhost\(your-wsl-os)\etc\timezone:/etc/timezone:ro
-v \\wsl.localhost\(your-wsl-os)\etc\localtime:/etc/localtime:ro
```

View AstrBot logs with the following command:

```bash
sudo docker logs -f astrbot
```

## 🎉 All Done

If everything goes well, you will see logs printed by AstrBot.

If there are no errors, AstrBot will print the WebUI URL and the initial credentials in the container logs. Open the WebUI URL to access AstrBot.

> [!TIP]
> Since Docker isolates the network environment, you cannot use `localhost` to access the dashboard.
>
> New users must use the random password printed in the startup logs to log in for the first time. Use the username shown in the logs (usually `astrbot`) and change the password after first login.
>
> If deployed on a cloud server, you need to open ports `6180-6200` and `11451` in the cloud provider's console.

Next, you need to deploy any messaging platform to use AstrBot on that platform.
