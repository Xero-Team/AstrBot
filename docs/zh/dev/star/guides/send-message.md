# 消息发送

## 被动回复

事件处理器可以通过 `yield` 返回一个或多个消息结果：

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("hello")
async def hello(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.image_result("path/to/image.jpg")
    yield event.image_result("https://example.com/image.jpg")
```

本地路径由 AstrBot 进程所在的主机或容器解析；URL 图片必须以 `http://` 或
`https://` 开头。具体消息类型是否可用仍取决于平台适配器。

## 主动发送

定时任务或其他延迟流程可以保存 `event.unified_msg_origin`，之后通过
`PluginContext.messages.send()` 向同一会话发送消息：

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

    yield event.plain_result("已尝试主动发送消息。")
```

`PluginContext.messages.send()` 返回 `PlatformSendResult`，其中包含 `platform_id`、
`success`、`target`、`message_count` 和 `error_message`。平台不存在、平台发送
抛出异常等情况会返回 `success=False`；格式非法的会话字符串会抛出 `ValueError`。
并非所有平台都支持主动发送。QQ 官方机器人需要仍可用的本地缓存会话状态；微信公众号适配器目前会明确拒绝主动发送。插件应检查 `send_result`，并为平台限制准备降级行为。

`unified_msg_origin` 是 AstrBot 的统一会话标识，包含定位平台实例和会话所需的信息。
持久化它时应按用户数据处理，不要把它公开到日志或不受信任的客户端。

## 富媒体消息链

使用公开的消息组件构建有序消息链：

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
        Comp.Plain("来看这张图片："),
        Comp.Image.fromURL("https://example.com/image.jpg"),
        Comp.Image.fromFileSystem("path/to/image.jpg"),
        Comp.Plain("消息组件会按列表顺序发送。"),
    ]
    yield event.chain_result(chain)
```

也可以用 `MessageEventResult.mention()` / `mention_all()`：

```python
yield (
    event.make_result()
    .mention(event.get_sender_name(), event.get_sender_id())
    .message("你好")
)
yield event.make_result().mention_all().message("全体注意")
```

`MentionAll` 是独立类型，不要写 `Mention(target="all")`。部分平台会把全体提及降级成文本，例如 LINE、Telegram、Mattermost 发出 `@all`；QQ 官方机器人会忽略 `MentionAll`。出站时 `Mention(target="all")` 也不是全体：OneBot、NapCat、飞书、Satori、KOOK 会把它降级成普通文本 `@all`，不会发平台的全体标记。部分适配器只用 `name` 渲染 `@`，构造 `Mention` 时请同时写 `name` 和 `target`。

部分平台会拆分或降级不支持的组件。OneBot 适配器还可能清理纯文本首尾空白；确实
需要保留时，可以在文本边界加入零宽空格 `\u200b`。OneBot v11 与 NapCat 把文件、
语音、视频和合并转发拆成独立消息，连续拆分发送之间间隔 0.5 秒。

### 文件

```python
Comp.File(name="file.txt", file="path/to/file.txt")
```

文件消息并非所有平台都支持。OneBot v11 与 NapCat 会把文件拆成单独一条发送，
不会和图文混排段放在同一条消息里。

### 语音

```python
Comp.Record.fromFileSystem("path/to/record.wav")
Comp.Record.fromURL("https://example.com/record.mp3")
Comp.Record.fromBase64(encoded_audio)
```

`Record` 组件本身并非全局仅接受 WAV。AstrBot 会在需要时解析或转换音频，但实际
可用格式取决于目标适配器以及运行环境的媒体工具链；WAV 通常是跨平台最稳妥的输入。
OneBot v11 与 NapCat 会把语音拆成单独一条发送，不会和图文混排段放在同一条消息里。

### 视频

```python
Comp.Video.fromFileSystem("path/to/video.mp4")
Comp.Video.fromURL("https://example.com/video.mp4")
```

本地文件必须存在于 AstrBot 运行环境中。URL 与视频格式还需要目标平台支持。
OneBot v11 与 NapCat 会把视频拆成单独一条发送，不会和图文混排段放在同一条消息里。

## 发送群合并转发消息

合并转发不是通用组件，目前主要用于 OneBot v11：

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Node, Plain


@filter.command("forward-demo")
async def forward_demo(self, event: AstrMessageEvent):
    node = Node(
        uin="10001",
        name="示例用户",
        content=[
            Plain("Hello"),
            Image.fromFileSystem("test.jpg"),
        ],
    )
    yield event.chain_result([node])
```

在其他平台使用前，应先检查适配器是否支持该组件，并为不支持的情况准备纯文本等
降级结果。
