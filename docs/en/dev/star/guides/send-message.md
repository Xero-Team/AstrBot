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

## Rich-Media Chains

Build an ordered chain with the public message components:

```python
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("picture")
async def picture(self, event: AstrMessageEvent):
    chain = [
        Comp.At(qq=event.get_sender_id()),
        Comp.Plain("Look at this image:"),
        Comp.Image.fromURL("https://example.com/image.jpg"),
        Comp.Image.fromFileSystem("path/to/image.jpg"),
        Comp.Plain("Components are sent in list order."),
    ]
    yield event.chain_result(chain)
```

Some platforms split or degrade unsupported components. OneBot adapters may
also trim leading and trailing whitespace from plain-text segments. If that
whitespace is essential, place a zero-width space (`\u200b`) at the boundary.

### Files

```python
Comp.File(name="file.txt", file="path/to/file.txt")
```

File messages are not supported by every platform.

### Audio Records

```python
Comp.Record.fromFileSystem("path/to/record.wav")
Comp.Record.fromURL("https://example.com/record.mp3")
Comp.Record.fromBase64(encoded_audio)
```

The `Record` component is not globally restricted to WAV input. AstrBot
resolves or converts audio where needed, but usable formats depend on the target
adapter and the runtime media toolchain. WAV is usually the safest
cross-platform input.

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
