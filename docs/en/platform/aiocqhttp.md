# Connect a OneBot v11 Implementation

> [!TIP]
> If you plan to connect AstrBot to QQ, we recommend using [QQ Official Bot (WebSockets)](/en/platform/qqofficial/websockets). It is officially provided by QQ, offers greater stability, and supports one-click login by scanning a QR code.

AstrBot's `OneBot v11` (`aiocqhttp`) platform uses a **reverse WebSocket**: AstrBot starts the WebSocket server, and the OneBot implementation connects to it as a client.

> [!TIP]
> For NapCat, prefer AstrBot's dedicated [NapCat](/en/platform/napcat) platform. It uses a forward AstrBot -> NapCat WebSocket and exposes clearer configuration and connection state. This page is for implementations that specifically need the generic OneBot v11 reverse WebSocket.

Common OneBot v11 implementations include:

- [NapCat](https://github.com/NapNeko/NapCatQQ) for QQ
- [OneDisc](https://github.com/ITCraftDevelopmentTeam/OneDisc) for Discord
- [Tele-KiraLink](https://github.com/Echomirix/Tele-KiraLink) for Telegram

## 1. Create the Platform in AstrBot

1. Open the AstrBot WebUI and go to `Bots`.
2. Click `+ Create Bot` and select `OneBot v11`.
3. Fill in the configuration and save it.

Important fields:

- `id`: unique platform instance ID.
- `enable`: enables the platform.
- `ws_reverse_host`: the **local bind address** of AstrBot's WebSocket server; default `127.0.0.1`.
- `ws_reverse_port`: listener port; default `6199`.
- `ws_reverse_token`: reverse WebSocket authentication token. Configure one and use the same value in the OneBot implementation.

### Understand `ws_reverse_host`

`ws_reverse_host` is not the destination entered in the OneBot client:

- Keep `127.0.0.1` when AstrBot and the OneBot implementation run on the same host.
- Only bind a reachable interface when the client runs in another container, Pod, or host. This is commonly `0.0.0.0`, or a specific interface address.
- `0.0.0.0` is a wildcard bind address and is never a valid client destination.

> [!CAUTION]
> After binding `0.0.0.0`, restrict source access with a firewall or container/cluster network policy and configure `ws_reverse_token`. Never expose an unauthenticated OneBot WebSocket directly to the public internet.

## 2. Configure the OneBot Implementation

Create a reverse WebSocket client in the OneBot implementation. Its target path is:

```text
ws://<reachable-AstrBot-address>:6199/ws
```

Common examples:

- same host: `ws://127.0.0.1:6199/ws`
- same Docker network, with AstrBot service name `astrbot`: `ws://astrbot:6199/ws`
- different host: `ws://<AstrBot-host-IP-or-domain>:6199/ws`

Across an untrusted network, use a protected private network or a TLS reverse proxy with `wss://`; do not rely on an open port alone. The client token must match `ws_reverse_token`.

## 3. Verify

Open `Console` in the AstrBot WebUI. This log indicates a successful connection:

```text
aiocqhttp(OneBot v11) 适配器已连接。
```

If it does not appear, check that:

- the OneBot implementation enabled a **reverse** WebSocket client;
- its target is reachable from its own network and is not incorrectly set to `0.0.0.0`;
- AstrBot is bound to the correct interface and the container port or firewall permits the connection;
- the tokens match.

## NapCat and the Repository Compose Stack

The root `compose-with-napcat.yml` currently sets NapCat `MODE=astrbot`. On every startup, NapCat writes a reverse WebSocket client that targets:

```text
ws://astrbot:6199/ws
```

If you keep this mode, create `OneBot v11` in AstrBot and set `ws_reverse_host` to `0.0.0.0` and port `6199`. The containers share an internal network, so port `6199` does not need to be published to the host. NapCat's `MODE` template rewrites its configuration on every startup and has an empty token by default; follow [Docker Deployment](/en/deploy/astrbot/docker) to remove the template mode before persisting a token.

To use the recommended dedicated `NapCat` platform instead, change `MODE=astrbot` to `MODE=ws` in the Compose file. Then create `NapCat` and set `ws_url` to `ws://napcat:3001`. Use only one connection method for a given NapCat instance.
