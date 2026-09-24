# Connect NapCat

`napcat` is AstrBot's built-in NapCat QQ adapter. It now runs on a forward OneBot v11 WebSocket only.

Compared with the generic `OneBot v11` adapter:

- the WebUI exposes NapCat-specific fields directly
- AstrBot keeps a single outbound WebSocket connection to NapCat
- platform actions and inbound event parsing share that same connection

> [!TIP]
> If you only need a generic OneBot v11 implementation, see [OneBot v11](/en/platform/aiocqhttp).

## 1. Prepare NapCat

Deploy NapCat first, then confirm:

- NapCat OneBot v11 forward WebSocket is enabled
- you know its WebSocket URL, for example `ws://127.0.0.1:3001`
- if WebSocket auth is enabled, you also know the token

## 2. Create a NapCat bot in AstrBot

1. Open AstrBot WebUI
2. Go to `Bots`
3. Click `+ Create Bot`
4. Select `NapCat`

At minimum, fill in:

- `id`: bot instance ID
- `enable`: turn it on
- `ws_url`: NapCat OneBot v11 forward WebSocket URL
- `token`: optional, only if NapCat uses WebSocket auth

Advanced fields:

- `verify_ssl`: disable only for self-signed WSS certificates
- `timeout_seconds`: action response timeout
- `reconnect_interval_seconds`: reconnect delay after disconnect
- `max_frame_size_mb`: maximum accepted frame size

## 3. Ingress expansion of merged forwards

These settings live in the global `platform_settings` and are shared by `napcat` and `OneBot v11` (`aiocqhttp`). Set them on the `Config` page:

- `platform_settings.onebot_forward.expand_on_ingress`: on by default. When an inbound merged forward carries only a `forward` id and no expanded content, the adapter first calls `get_forward_msg` to fill in the nodes before later stages run. A failed or timed-out fetch keeps the forward unchanged and never blocks the message.
- `platform_settings.onebot_forward.max_fetch`: maximum number of recursive `get_forward_msg` calls per message during ingress expansion; default 8.
- `t2i_forward_card`: global system setting, on by default. When a session bridge delivers an expanded merged forward to a target that does **not** support native `forward`, the forward is rendered as one image card. Rendering failures fall back to the labeled text transcript. Targets that support `forward` still receive the merged-forward card.

## 4. Confirm the NapCat service

In NapCat WebUI, make sure the OneBot v11 forward WebSocket service is enabled and matches AstrBot's configuration.

Common examples:

- local host: `ws://127.0.0.1:3001`
- Docker Compose: `ws://napcat:3001`
- same Pod: `ws://localhost:3001`

## 5. Verify

After AstrBot starts, you should see logs like:

```text
[NapCat] Connecting forward WebSocket to ws://127.0.0.1:3001
[NapCat] Forward WebSocket connected to ws://127.0.0.1:3001
[NapCat] Forward WebSocket adapter ready: ...
```

Then send a QQ message and confirm AstrBot receives and replies to it.

## 6. Common Issues

- AstrBot starts but no inbound messages arrive
  - make sure NapCat forward WebSocket is actually enabled
  - verify `ws_url`
  - verify the token on both sides
- startup check fails
  - make sure NapCat is logged in and serving WebSocket
  - make sure you did not enter an HTTP URL by mistake
  - if you use `wss://`, verify the certificate and `verify_ssl`
- Docker networking fails
  - prefer container-local addresses such as `ws://napcat:3001` or `ws://localhost:3001`
