---
outline: deep
---

# 开发平台适配器

平台适配器把外部消息平台转换成 AstrBot 的 `AstrBotMessage` / `AstrMessageEvent`，并负责把 `MessageChain` 发送回正确的会话。适配器可以由 Star 插件注册，但文档代码只能使用 `astrbot.api` 公共 SDK；如果所需类型尚未导出，应先补 SDK，而不是从 `astrbot.core` 导入。

## 核心契约

一个适配器至少需要：

1. 用 `@register_platform_adapter` 注册类型和默认配置；
2. 继承 `Platform`，实现 `meta()`、`run()` 和实际的发送逻辑；
3. 把收到的平台消息转换为 `AstrBotMessage`；
4. 创建事件并通过 `commit_event()` 放入共享队列；
5. 在 `terminate()` 中关闭长连接、HTTP client、轮询任务和临时资源；
6. 返回父类生成的 `PlatformSendResult`，让指标和调用方知道发送结果。

`run()` 是长生命周期协程。捕获宽泛异常时必须重新抛出 `asyncio.CancelledError`，并保证部分初始化也能安全调用 `terminate()`。

## 最小示例

假设插件自带一个 `FakeClient`，它提供 `listen(callback)`、`send_chain(target, chain)` 和 `close()`。下面的示例只展示 AstrBot 边界；平台认证、重连、限流和 SDK 错误映射仍需由适配器实现。

### 事件类型

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

平台 SDK 完成实际发送后，再调用并返回 `super().send()`。父类负责统一指标和逻辑发送结果；只调用父类不会替你向平台 SDK 发消息。

### 适配器类型

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

### 会话路由不能使用发送者 ID 代替群 ID

`session_id` 是回复和主动消息的目标：

- 私聊使用发送者/私聊会话 ID；
- 群聊使用群、频道或 thread ID，而不是群成员的 sender ID。

事件的 `send()` 也必须使用相同路由。否则入站消息看似正常，回复却会被发成私聊或发给错误对象。如果平台需要更多不可变路由信息，应在平台事件/客户端内部保存并在发送时校验，不要依赖易变化的展示名称。

`send_by_session()` 用于没有原始 event 的主动发送。实际调用 SDK 成功后必须 `return await super().send_by_session(...)`；如果失败，适配器应记录平台错误并返回/抛出可诊断的失败，而不是让父类记录一次虚假的成功。

## 消息组件与媒体

使用公共消息组件构造标准消息链：

```python
from astrbot.api.message_components import Image, Plain, Record, Video

message.message = [
    Plain("文本"),
    Image.fromFileSystem("/tmp/image.png"),
    Record(file="https://example.com/audio.ogg"),
    Video(file="base64://..."),
]
```

组件可保存本地路径、`file:` URI、HTTP(S) URL、`base64://` 或 Data URI。发送端需要本地文件时使用组件的 `convert_to_file_path()`，不要手写各种 URI 前缀解析。

AstrBot 预处理会尽量下载和标准化图片、语音及引用消息媒体。适配器自行创建的临时文件应登记到事件：

```python
event.track_temporary_local_file(temp_path)
```

媒体格式最终仍受平台 SDK 限制。把 AstrBot 组件转换为平台消息时，应明确不支持的组件、大小限制、URL 下载策略和失败结果。

## 能力元数据

`PlatformMetadata` 的 `name`、`description` 和 `id` 都是必填项。`id` 通常来自平台实例配置，必须在多实例之间唯一。

- 未实现原生流式协议时设置 `support_streaming_message=False`；普通分段回复不等于原生流式。
- 只有真正实现 `send_by_session()` 时才声明 `support_proactive_message=True`。
- 平台动作（禁言、踢人、戳一戳等）应覆写对应 `Platform` 方法；`supported_actions` 可由覆写自动推导。
- `adapter_display_name`、`logo_path`、i18n 和配置元数据可改善 WebUI 展示，但不能代替运行时校验。

## 在 Star 中加载

注册装饰器只有在模块被导入后才会执行。插件入口中显式导入适配器：

```python
from astrbot.api.star import PluginContext, Star

from .fake_platform_adapter import FakePlatformAdapter  # noqa: F401


class Main(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)
```

所有 Star 和第三方适配器示例都应保持在 `astrbot.api` 边界内。

## NapCat 生成模型

内置 NapCat 的 `generated/ob11_events.py` 来自 schema，不要手改。更新类型定义后执行：

```bash
make napcat-codegen
make napcat-test
make napcat-check
```

`make napcat-check` 会重新生成模型并运行定向测试。手写的连接、事件和出站协议代码仍需普通单元测试覆盖。

## 跨平台消息投递

跨会话监听使用 `MessageEnvelope` 保存入站语义快照。`content` 是唯一的有序内容序列；`source_route` 保留传输路由，`source_umo` 保留入站会话身份，不能混为一个可变字段。源适配器负责解析私有文件 ID 和延迟媒体引用，目标适配器负责上传和协议编码。合并转发记录展开后保留作者标签和媒体顺序。

适配器通过 `message_capabilities(session)` 返回不可变的 `MessageDeliveryCapabilities`。插件适配器可以从 `astrbot.api.platform` 导入这些类型并覆写该方法。描述必须反映当前发送路径、账号模式和目标会话，不应直接照搬平台协议能力。支持的原生消息需要同时匹配命名空间与内容种类；跨 Bot 实例默认降级，不能仅凭平台名称复用私有 payload。

以下为 2026-09-11 核对本仓库 `astrbot/core/platform/sources/` 发送实现后的保守投递范围，不表示已用所有平台的真实账号联调：

| 适配器目录                | 可投递媒体             | 主要限制或处理                                                                          |
| ------------------------- | ---------------------- | --------------------------------------------------------------------------------------- |
| `aiocqhttp`               | 图片、音频、视频、文件 | OneBot 消息段；保留图文顺序和有映射的引用                                               |
| `napcat`                  | 图片、音频、视频、文件 | OneBot/NapCat 消息段；原生内容按种类声明                                                |
| `telegram`                | 图片、音频、视频、文件 | 当前桥接按顺序拆发；4096 文本上限；不复用其他 Bot 的 file_id                            |
| `discord`                 | 图片、音频、文件       | 2000 文本上限；跨会话转发禁用提及通知；视频作为普通文件投递                             |
| `kook`                    | 图片、音频、视频、文件 | 各组件分别发送；支持引用和 JSON 卡片                                                    |
| `lark`                    | 图片、音频、视频、文件 | 卡片及上传由飞书发送器处理；桥接引用降级为摘要                                          |
| `line`                    | 图片、音频、视频、文件 | 每次最多 5 段，文字 5000；媒体需要可访问的 HTTPS `callback_api_base`                    |
| `mattermost`              | 图片、音频、视频、文件 | 媒体先上传；引用使用 root_id                                                            |
| `misskey`                 | 图片、音频、视频、文件 | 媒体取决于文件上传开关；长度取实例配置；引用摘要                                        |
| `satori`                  | 图片、音频、视频、文件 | 能否接受具体内容仍取决于 Satori 后端及所接平台                                          |
| `slack`                   | 图片、文件             | blocks/上传路径；桥接文字使用 plain_text；引用摘要                                      |
| `dingtalk`                | 图片、音频、视频、文件 | 不同媒体使用不同上传和消息模板；引用摘要                                                |
| `qqofficial`              | 图片、音频、视频、文件 | 实际类型名为 qq_official；群/频道根据缓存消息 ID 和主动发送模式判断；频道媒体保守限图片 |
| `qqofficial_webhook`      | 图片、音频、视频、文件 | 实际类型名为 qq_official_webhook；共用官方发送逻辑及会话限制                            |
| `webchat`                 | 图片、音频、视频、文件 | 通过 WebChat 队列投递；桥接引用摘要                                                     |
| `wecom`                   | 图片、音频、视频、文件 | 应用模式需 agent_id；客服模式不支持主动发送                                             |
| `wecom_ai_bot`            | 图片、音频、视频、文件 | 主动发送要求配置推送 Webhook；视频作为文件上传                                          |
| `weixin_oc`               | 图片、音频、视频、文件 | 发送依赖当前账号连接及平台会话上下文                                                    |
| `weixin_official_account` | 接收侧图片、音频可投影 | 当前 send_by_session 拒绝主动发送，可作为监听来源                                       |

这些能力只用于当前跨会话投递路径。现有 Stars 的 `MessageChain` 发送接口仍由各适配器编码。规划器按顺序拆分并执行文本/段数限制，媒体在投递期间持有独立副本，需要异步拉取的目标使用可重复读取、到期释放的文件令牌。发送回执表示平台接受情况；仅有平台返回的消息 ID 才能建立原生引用映射，缺失 ID 时必须退回摘要。

监听通过适配器拥有的任务执行，热重载会为新实例注册观察者，关闭时取消任务。每个适配器最多积压 128 个观察任务，过载只跳过转发，不阻塞普通消息队列。监听不回放历史、不持久化、也不转发 Bot 自己的入站回显。

## 验证清单

- 私聊、群聊和 thread 的 `session_id` 都能正确回复；
- `send()` 与 `send_by_session()` 都进行真实 SDK 调用并返回逻辑发送结果；
- 队列满、连接断开、限流、取消和关闭不会泄漏任务/client；
- 同一适配器多实例使用不同 metadata ID；
- 图片、音频、文件、引用和不支持组件有明确行为；
- 声明的流式、主动消息和平台动作能力都有端到端测试；
- 插件停用/热重载后没有重复回调或旧连接残留。
