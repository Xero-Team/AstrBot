# Deploy AstrBot with Docker

> [!WARNING]
> This fork does not publish an official Docker image. Docker deployment should build AstrBot locally from this repository.

## Recommended Path

For this fork, the maintained Docker path is based on `compose-with-napcat.yml`. It builds AstrBot from the local `Dockerfile` instead of pulling an upstream image.

Clone the repository first:

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
```

## Start AstrBot Only

If you only want AstrBot itself, start just the `astrbot` service:

```bash
docker compose -f compose-with-napcat.yml up -d --build astrbot
```

View logs with:

```bash
docker compose -f compose-with-napcat.yml logs -f astrbot
```

## Start AstrBot and NapCat Together

If you also need OneBot v11 + NapCat, start the full compose stack:

```bash
docker compose -f compose-with-napcat.yml up -d --build
```

This compose file:

- builds the AstrBot image locally from this repository
- starts the official NapCat container
- keeps AstrBot and NapCat on the same internal Docker network

Default ports:

- `6185`: AstrBot WebUI
- `6099`: NapCat WebUI

Default persistent directories:

- `./data`
- `./napcat/config`
- `./ntqq`

## NapCat Connection Notes

After the containers are up:

1. In AstrBot WebUI, create a `OneBot v11` bot with reverse WebSocket host `0.0.0.0` and port `6199`.
2. In NapCat WebUI, create a reverse WebSocket client with URL `ws://astrbot:6199/ws`.

Because both containers share the same internal network, NapCat does not need to call back through the host address.

## Old Paths That Are Not Recommended

The following are not the Docker deployment path for this fork anymore:

- using `soulter/astrbot:latest` directly
- switching upstream image pulls to a mirror
- deploying this fork through handwritten `docker run` commands

Those approaches do not match how this fork ships code, dependencies, and dashboard assets.

## After Startup

If startup succeeds, AstrBot prints the WebUI URL and initial credentials in container logs. Open the printed URL to access the dashboard.

> [!TIP]
> First-time logins use the random initial password printed in startup logs. The username is usually `astrbot`. Change it immediately after login.

To update later:

```bash
git pull
docker compose -f compose-with-napcat.yml up -d --build astrbot
```
