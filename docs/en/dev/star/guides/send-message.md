# Sending Messages

## Passive Replies

An event handler can return one or more message results with `yield`:

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("hello")
async def hello(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.image_result("path/to/image.jpg")
    yield event.image_result("https://example.com/image.jpg")
```

Local paths are resolved on the host or in the container running AstrBot. Image
URLs must start with `http://` or `https://`. Whether a message type can be
delivered still depends on the platform adapter.

## Proactive Messages

A scheduled task or another delayed workflow can save
`event.unified_msg_origin` and later call `PluginContext.messages.send()` for the same
session:

```python
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter


@filter.command("remember-me")
async def remember_me(self, event: AstrMessageEvent):
    session = event.unified_msg_origin
    chain = MessageChain().message("Hello!").file_image("path/to/image.jpg")

    send_result = await self.context.messages.send(session, chain)
    if not send_result.success:
        logger.warning(
            "Message delivery failed: %s",
            send_result.error_message or "unknown error",
        )

    yield event.plain_result("Proactive delivery was attempted.")
```

`PluginContext.messages.send()` returns a `PlatformSendResult` with `platform_id`,
`success`, `target`, `message_count`, and `error_message`. A missing adapter or
an adapter send exception produces `success=False`; an invalid session string
raises `ValueError`. Not every platform supports proactive delivery. QQ
Official Bot requires usable locally cached session state, while the WeChat
Official Account adapter currently rejects proactive sends. Check
`send_result` and provide a fallback for platform limitations.

`unified_msg_origin` is AstrBot's unified session identifier and contains the
information needed to locate a platform instance and conversation. Treat a
stored value as user data; do not expose it in public logs or to untrusted
clients.

## Cross-session watches and sending

To forward or deliver to **another** session, do not keep your own observers
and do not bypass authorization with `messages.send()`. Use
`PluginContext.bridges`:

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.permission("session.watch")
@filter.command("watch-room")
async def watch_room(self, event: AstrMessageEvent, target_umo: str):
    watch = await self.context.bridges.watch(event, target_umo)
    yield event.plain_result(f"watching {watch.target_umo}")
```

- `watch(event, target_umo, *, source_umo=None, ttl_seconds=None)`: create an expiring watch owned by the event's trusted actor; returns `SessionWatch`. `source_umo` is the listening session that receives forwards and defaults to the current session. `ttl_seconds` is 1–864000, default 43200. `expires_at` is wall-clock UTC unix seconds. `rule_id` is a stable 12-character lowercase hex id. When it expires, the listener session receives an end notice.
- `unwatch(event, target_umo, *, source_umo=None)`: stop a matching watch this actor created.
- `list(event, *, source_umo=None)`: list this actor's active watches (not connects). `source_umo` is the listening session and defaults to the current session.
- `connect(event, target_umo)`: create an unbounded 1:1 link from the current session; returns `SessionWatch` with `expires_at is None`. There is no `ttl_seconds` argument.
- `disconnect(event)`: drop that link.
- `connection(event)`: return the current unbounded link, or `None`.
- `send(event, target_umo, *, target_in_header=True)`: deliver the current message body and attachments after stripping the command header; returns `DeliveryReceipt`. Linked `/send` without a UMO passes `target_in_header=False`.
- `pair(event, target_umo)`: create two reverse edges that share a `pair_id` between the current session and target; returns two `SessionWatch` values. Both sides require `session.watch`.
- `unpair(event, target_umo=None)`: remove both edges that share the pair id owned by the actor. Omitting `target_umo` requires the current session to touch a single pair.
- `list_links(event)`: list the watch, connect, and pair edges visible to the actor as `(SessionWatch, kind)` tuples, where `kind` is `watch`/`connect`/`pair`; visibility follows the operator role.
- `unlink(event, rule_id)`: remove a watch or connect by public id; a pair edge cannot be removed this way and requires `unpair`. Creator and operator rules apply.
- `get_filter(event, rule_id)`: read the `match`/`except` filters visible for one edge as `(match, except)`, or `None` when unauthorized or missing.
- `append_filter(event, rule_id, side, dimension, value)`: append one `match` or `except` value; returns the updated `(match, except)`. `side` is `match`/`except`; `dimension` is `subjects`/`roles`/`text`.
- `clear_filter(event, rule_id, side)`: clear one side or both, with `side` as `match`/`except`/`all`.
- `quota_usage(event)`: return per-kind usage and cap for the actor as `dict[str, SessionBridgeQuota]`; import `SessionBridgeQuota` from `astrbot.api.platform`.

Operations that reach another session (`watch`, `connect`, `send`, `pair`)
call `authorize()` again and require `session.watch` or `session.send`; both
sessions must share a configuration. The other reads and writes only touch
rules the actor owns or can see as an operator, so they need no target
permission. Watches, links, and pairs persist in SQLite, so unexpired rules
survive process restart. `remaining_seconds` uses the wall clock; unbounded
links return `0`. Do not construct `SessionBridgeManager` yourself. Import
`SessionWatch`, `SessionBridgeQuota`, and the duration constants from
`astrbot.api.platform`. A pair is two directed edges that share a `pair_id`:
the far side sees the destination Bot account with the same localized source
header as a watch, the source platform identity is not forged, `/send` is not
bound, and splitting the pair requires `unpair`. There is no Dashboard
management surface, and plugins must not assume a matching HTTP API.

## Rich-Media Chains

Build an ordered chain with the public message components:

```python
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("picture")
async def picture(self, event: AstrMessageEvent):
    chain = [
        Comp.Mention(
            target=event.get_sender_id(),
            name=event.get_sender_name(),
        ),
        Comp.Plain("Look at this image:"),
        Comp.Image.fromURL("https://example.com/image.jpg"),
        Comp.Image.fromFileSystem("path/to/image.jpg"),
        Comp.Plain("Components are sent in list order."),
    ]
    yield event.chain_result(chain)
```

Builders `MessageEventResult.mention()` / `mention_all()` do the same:

```python
yield (
    event.make_result()
    .mention(event.get_sender_name(), event.get_sender_id())
    .message("hello")
)
yield event.make_result().mention_all().message("everyone")
```

`MentionAll` is a sibling type. Do not write `Mention(target="all")`. Some platforms degrade everyone-mentions to text (for example LINE and Mattermost). Telegram has no Bot API-wide notification token, so it ignores `MentionAll` for delivery. QQ Official drops `MentionAll`. Outbound `Mention(target="all")` is also not everyone: OneBot, NapCat, Lark, Satori, and KOOK degrade it to plain `@all` instead of the platform everyone token. Some adapters render `@` from `name`, so set both `name` and `target` when building a `Mention`.

Some platforms split or degrade unsupported components. OneBot adapters may
also trim leading and trailing whitespace from plain-text segments. If that
whitespace is essential, place a zero-width space (`\u200b`) at the boundary.
OneBot v11 and NapCat send file, voice, video, and forward nodes as separate
messages; consecutive split sends are spaced 0.5 seconds apart.

### Files

```python
Comp.File(name="file.txt", file="path/to/file.txt")
```

File messages are not supported by every platform. OneBot v11 and NapCat send
each file as its own message, separate from mixable text and image segments.

### Audio Records

```python
Comp.Record.fromFileSystem("path/to/record.wav")
Comp.Record.fromURL("https://example.com/record.mp3")
Comp.Record.fromBase64(encoded_audio)
```

The `Record` component is not globally restricted to WAV input. AstrBot
resolves or converts audio where needed, but usable formats depend on the target
adapter and the runtime media toolchain. WAV is usually the safest
cross-platform input. OneBot v11 and NapCat send each voice record as its own
message, separate from mixable text and image segments.

### Video

```python
Comp.Video.fromFileSystem("path/to/video.mp4")
Comp.Video.fromURL("https://example.com/video.mp4")
```

A local file must exist in the AstrBot runtime environment. The target platform
must also support the URL and video format. OneBot v11 and NapCat send each
video as its own message, separate from mixable text and image segments.

## Group Forward Messages

Forward nodes are not a general cross-platform component and are currently
intended primarily for OneBot v11:

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Node, Plain


@filter.command("forward-demo")
async def forward_demo(self, event: AstrMessageEvent):
    node = Node(
        uin="10001",
        name="Example User",
        content=[
            Plain("Hello"),
            Image.fromFileSystem("test.jpg"),
        ],
    )
    yield event.chain_result([node])
```

Check adapter support before using this component on another platform, and
provide a plain-text or other fallback when it is unavailable.
