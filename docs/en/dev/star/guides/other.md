# Miscellaneous

## Call OneBot capabilities

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.onebot import OneBotMessageEvent


@filter.command("test")
async def test_(self, event: AstrMessageEvent):
    onebot_event = self.context.onebot.event(event)
    if not isinstance(onebot_event, OneBotMessageEvent):
        return

    client = self.context.onebot.for_event(event)
    if client is not None and self.context.onebot.supports(
        event, "onebot.v11", "delete"
    ):
        await client.messages.delete(message_id=onebot_event.message_id or "")
```

Plugins no longer expose a `Platform` instance or `platform_manager`. Prefer these for ordinary platform IO:

- `self.context.messages.send(...)`
- `self.context.platform_actions.invoke(...)`
- `self.context.platform_actions.invoke_for_event(...)`

Use `self.context.messages.create_event(...)` only when you truly need to construct a new inbound platform event.

## Call QQ protocol APIs

Do not depend on `event.bot`, `event.client`, or a platform SDK client from plugin code.

Standard OneBot v11 actions go through `client.messages`, `client.directory`, `client.groups`, `client.requests`, and `client.history`. NapCat-specific actions live on `client.qq` and should be probed with `supports(event, "napcat.qq", action)` first. Do not access `event.bot` or `event.client`, and do not call arbitrary raw actions.

CQHTTP API references:

NapCat API: <https://napcat.apifox.cn/>

Lagrange API: <https://lagrange-onebot.apifox.cn/>

## List loaded plugins

```py
plugins = self.context.runtime_info.plugins()  # read-only PluginInfo
```

## List loaded platforms

Plugins no longer get an API that enumerates every platform instance.

If a plugin must act on a platform, use an explicit platform ID:

```py
client = self.context.onebot.for_event(event)
status = await client.directory.status() if client else None
```
