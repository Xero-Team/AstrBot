---
outline: deep
---

# Developing a Platform Adapter

A platform adapter converts an external messaging platform into AstrBot `AstrBotMessage` / `AstrMessageEvent` objects and sends `MessageChain` output back to the correct route. An adapter can be registered by a Star plugin, but documentation code must stay on the public `astrbot.api` SDK. If a required type is not exported, treat that as an SDK gap instead of importing `astrbot.core`.

## Core contract

An adapter must at least:

1. register its type and default configuration with `@register_platform_adapter`;
2. inherit `Platform` and implement `meta()`, `run()`, and real transport sending;
3. convert inbound platform messages into `AstrBotMessage`;
4. create events and submit them with `commit_event()`;
5. close long-lived connections, HTTP clients, polling tasks, and temporary resources in `terminate()`;
6. return the parent-generated `PlatformSendResult` so metrics and callers receive a logical send result.

`run()` is a long-lived coroutine. Re-raise `asyncio.CancelledError` from broad exception handling, and make `terminate()` safe after partial initialization.

## Minimal example

Assume the plugin owns a `FakeClient` with `listen(callback)`, `send_chain(target, chain)`, and `close()`. The example focuses on the AstrBot boundary; authentication, reconnection, rate limiting, and SDK error mapping remain adapter responsibilities.

### Event type

```python
from astrbot.api.event import AstrMessageEvent, MessageChain


class FakePlatformEvent(AstrMessageEvent):
    def __init__(self, *args, client, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = client

    async def send(self, message: MessageChain):
        target = self.get_sender_id() if self.is_private_chat() else self.get_group_id()
        await self.client.send_chain(target, message)
        return await super().send(message)
```

Call and return `super().send()` only after the platform SDK has sent the message. The parent records metrics and the logical result; calling it alone does not send through your SDK.

### Adapter type

```python
import asyncio

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)

from .client import FakeClient
from .fake_platform_event import FakePlatformEvent


@register_platform_adapter(
    "fake",
    "Fake platform adapter",
    default_config_tmpl={
        "id": "fake",
        "enable": False,
        "token": "",
    },
)
class FakePlatformAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.client = FakeClient(token=str(platform_config.get("token", "")))
        self.metadata = PlatformMetadata(
            name="fake",
            description="Fake platform adapter",
            id=str(platform_config.get("id", "fake")),
            adapter_display_name="Fake Platform",
            support_streaming_message=False,
            support_proactive_message=True,
        )

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def run(self) -> None:
        async def on_message(data: dict) -> None:
            try:
                message = self.convert_message(data)
                event = FakePlatformEvent(
                    message_str=message.message_str,
                    message_obj=message,
                    platform_meta=self.meta(),
                    session_id=message.session_id,
                    client=self.client,
                )
                if not self.commit_event(event):
                    logger.warning("Fake platform event queue is full")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to convert Fake platform message")

        await self.client.listen(on_message)

    async def terminate(self) -> None:
        await self.client.close()

    def convert_message(self, data: dict) -> AstrBotMessage:
        sender_id = str(data["user_id"])
        group_id = str(data.get("group_id") or "")
        is_group = bool(group_id)

        message = AstrBotMessage()
        message.type = (
            MessageType.GROUP_MESSAGE if is_group else MessageType.FRIEND_MESSAGE
        )
        message.session_id = group_id if is_group else sender_id
        message.group_id = group_id
        message.message_id = str(data["message_id"])
        message.self_id = str(data["bot_id"])
        message.sender = MessageMember(
            user_id=sender_id,
            nickname=str(data.get("nickname") or sender_id),
        )
        message.message_str = str(data.get("content") or "")
        message.message = [Plain(message.message_str)]
        message.raw_message = data
        return message

    async def send_by_session(self, session, message_chain: MessageChain):
        await self.client.send_chain(session.session_id, message_chain)
        return await super().send_by_session(session, message_chain)
```

### A group route is not the sender ID

`session_id` is the reply and proactive-message target:

- direct messages use the sender/direct-session ID;
- groups use the group, channel, or thread ID, not the member sender ID.

The event's `send()` implementation must use the same route. Otherwise inbound handling can look correct while replies become direct messages or reach the wrong target. If a platform needs more immutable route data, preserve it inside the platform event/client and validate it during send instead of relying on a mutable display name.

`send_by_session()` supports proactive sends without retaining the original event. Make the real SDK call, then `return await super().send_by_session(...)`. On failure, record a platform error and return or raise a diagnosable failure instead of letting the parent record a false success.

## Message components and media

Use public message components to build normalized chains:

```python
from astrbot.api.message_components import Image, Plain, Record, Video

message.message = [
    Plain("text"),
    Image.fromFileSystem("/tmp/image.png"),
    Record(file="https://example.com/audio.ogg"),
    Video(file="base64://..."),
]
```

Components can carry local paths, `file:` URIs, HTTP(S) URLs, `base64://`, or data URIs. When an outbound SDK needs a local file, call the component's `convert_to_file_path()` instead of parsing every URI prefix yourself.

AstrBot preprocessing attempts to download and normalize images, audio, and quoted-message media. Track temporary files created directly by the adapter:

```python
event.track_temporary_local_file(temp_path)
```

The platform SDK still controls final media formats. When converting AstrBot components, define unsupported-component behavior, size limits, URL download policy, and failure results explicitly.

## Capability metadata

`PlatformMetadata.name`, `description`, and `id` are required. The ID normally comes from the adapter instance configuration and must be unique across instances.

- Set `support_streaming_message=False` unless the adapter implements a native streaming protocol. Ordinary segmented replies are not native streaming.
- Declare `support_proactive_message=True` only when `send_by_session()` really works.
- Override the corresponding `Platform` methods for platform actions such as ban, kick, notice, or poke. Supported actions can be derived from those overrides.
- `adapter_display_name`, `logo_path`, i18n, and configuration metadata improve WebUI presentation but do not replace runtime validation.

## Loading from a Star

The registration decorator runs only after its module is imported. Import the adapter explicitly from the plugin entry point:

```python
from astrbot.api.star import PluginContext, Star

from .fake_platform_adapter import FakePlatformAdapter  # noqa: F401


class Main(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)
```

Keep all Star and third-party adapter examples inside the `astrbot.api` boundary.

## NapCat generated models

The built-in NapCat `generated/ob11_events.py` comes from a schema and must not be edited by hand. After updating type definitions, run:

```bash
make napcat-codegen
make napcat-test
make napcat-check
```

`make napcat-check` regenerates models and runs focused tests. Handwritten connection, event, and outbound-protocol code still needs ordinary unit tests.

## Cross-platform message delivery

Cross-session watches capture inbound semantics in `MessageEnvelope`. Its `content` is the only ordered sequence. `source_route` retains the transport route, while `source_umo` retains the inbound session identity. The source adapter resolves private file IDs and deferred media; the target owns uploads and protocol encoding. Forwarded transcripts are expanded with author labels and their original media order.

Adapters return immutable `MessageDeliveryCapabilities` from `message_capabilities(session)`. Plugin adapters can import these types from `astrbot.api.platform` and override the method. Describe the current sender, account mode, and target session instead of copying a platform protocol's theoretical capabilities. Native JSON snapshots must match both namespace and content kind. Delivery across Bot instances defaults to fallback; matching platform names alone does not make private payloads reusable.

The following conservative inventory was checked against this checkout's senders under `astrbot/core/platform/sources/` on 2026-09-11. It does not claim live-account testing on every platform:

| Adapter directory         | Deliverable media                         | Main restriction or handling                                                                                   |
| ------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `aiocqhttp`               | Image, audio, video, file                 | OneBot segments; preserve content order and mapped quotes                                                      |
| `napcat`                  | Image, audio, video, file                 | OneBot/NapCat segments; native content declared by kind                                                        |
| `telegram`                | Image, audio, video, file                 | Bridge sends parts in order; 4096 text limit; never reuse another Bot's file_id                                |
| `discord`                 | Image, audio, file                        | 2000 text limit; cross-session forwarding disables mention notifications; video is delivered as a generic file |
| `kook`                    | Image, audio, video, file                 | Separate component sends; quotes and JSON cards                                                                |
| `lark`                    | Image, audio, video, file                 | Lark sender handles cards and uploads; bridge quotes use summaries                                             |
| `line`                    | Image, audio, video, file                 | At most 5 parts per request and 5000 text characters; public HTTPS `callback_api_base`                         |
| `mattermost`              | Image, audio, video, file                 | Upload media first; quotes use root_id                                                                         |
| `misskey`                 | Image, audio, video, file                 | Media depends on the upload setting; instance-specific text limit; quote summaries                             |
| `satori`                  | Image, audio, video, file                 | Acceptance also depends on the Satori backend and connected platform                                           |
| `slack`                   | Image, file                               | Blocks/uploads; bridge text uses plain_text; quote summaries                                                   |
| `dingtalk`                | Image, audio, video, file                 | Media-specific uploads and templates; quote summaries                                                          |
| `qqofficial`              | Image, audio, video, file                 | Runtime name qq_official; checks cached IDs and proactive mode; channel media conservatively limited to images |
| `qqofficial_webhook`      | Image, audio, video, file                 | Runtime name qq_official_webhook; shares official sending logic and session restrictions                       |
| `webchat`                 | Image, audio, video, file                 | Delivered through the WebChat queue; bridge quote summaries                                                    |
| `wecom`                   | Image, audio, video, file                 | Application mode needs agent_id; customer-service mode cannot send proactively                                 |
| `wecom_ai_bot`            | Image, audio, video, file                 | Proactive sending needs a push Webhook; video uploads as a file                                                |
| `weixin_oc`               | Image, audio, video, file                 | Depends on the account connection and platform session context                                                 |
| `weixin_official_account` | Inbound images and audio can be projected | Current send_by_session rejects proactive delivery; usable as a watch source                                   |

These descriptors apply to cross-session delivery. Existing Stars' `MessageChain` sends still use adapter encoders. The planner splits content in order and enforces text and part limits. Delivery holds independent media copies; asynchronous media fetches use reusable file tokens whose copies are released on expiry. Receipts describe platform acceptance. Native quote mappings require returned message IDs; absent IDs must fall back to summaries.

Observer tasks belong to adapters, are attached to replacement instances on hot reload, and are cancelled on shutdown. Each adapter admits at most 128 pending observation tasks; overload skips forwarding while preserving the ordinary inbound queue. Watches do not replay history, persist across restarts, or forward the Bot's own inbound echoes.

## Verification checklist

- direct-message, group, and thread `session_id` values route replies correctly;
- both `send()` and `send_by_session()` perform a real SDK call and return a logical result;
- queue-full, disconnect, rate-limit, cancellation, and shutdown paths do not leak tasks or clients;
- multiple instances of one adapter use distinct metadata IDs;
- image, audio, file, quote, and unsupported-component behavior is defined;
- every declared streaming, proactive-message, and platform-action capability has an end-to-end test;
- plugin disable/hot reload leaves no duplicate callbacks or stale connections.
