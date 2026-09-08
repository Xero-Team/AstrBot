import asyncio
import uuid
from typing import TYPE_CHECKING

from astrbot.core.message.components import (
    BaseMessageComponent,
    File,
    Image,
    Markdown,
    Mention,
    MentionAll,
    Plain,
    Record,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import DeliveryAttempt, PlatformSendResult

from .weixin_oc_text import STREAM_IDLE_S, STREAM_MIN_CHARS

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from .weixin_oc_adapter import WeixinOCAdapter


class WeixinOCMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        platform: WeixinOCAdapter,
        *,
        run_id: str | None = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.platform = platform
        self.run_id = str(run_id or "").strip()
        self._typing_owner_id: str | None = None

    def _get_typing_owner_id(self) -> str:
        if not self._typing_owner_id:
            self._typing_owner_id = uuid.uuid4().hex
        return self._typing_owner_id

    @staticmethod
    def _segment_to_text(segment: BaseMessageComponent) -> str:
        if isinstance(segment, Plain):
            return segment.text
        if isinstance(segment, Image):
            return "[图片]"
        if isinstance(segment, File):
            return f"[文件:{segment.name}]"
        if isinstance(segment, Video):
            return "[视频]"
        if isinstance(segment, Record):
            return "[音频]"
        if isinstance(segment, Markdown):
            return segment.content
        if isinstance(segment, MentionAll):
            return "@all"
        if isinstance(segment, Mention):
            return f"@{segment.name or segment.target}"
        return "[消息]"

    @staticmethod
    def _build_plain_text(message: MessageChain) -> str:
        return "".join(
            WeixinOCMessageEvent._segment_to_text(seg) for seg in message.chain
        )

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        if not message.chain:
            return
        await self.platform.send_by_session(
            self.session,
            message,
            run_id=self.run_id or None,
        )
        return await super().send(message)

    async def send_typing(self) -> None:
        await self.platform.start_typing(
            self.session.session_id,
            self._get_typing_owner_id(),
        )

    async def stop_typing(self) -> None:
        await self.platform.stop_typing(
            self.session.session_id,
            self._get_typing_owner_id(),
        )

    async def send_streaming(self, generator, use_fallback: bool = False):
        buffer = ""
        attempts: list[DeliveryAttempt] = []

        async def flush_text() -> None:
            nonlocal buffer
            text = buffer
            buffer = ""
            if not text.strip():
                return
            attempts.append(
                await self._send_streaming_fragment(MessageChain([Plain(text)]))
            )

        stream = generator.__aiter__()

        async def take_next() -> MessageChain:
            return await anext(stream)

        pending: asyncio.Task[MessageChain] = asyncio.create_task(take_next())
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=STREAM_IDLE_S)
                if not done:
                    await flush_text()
                    continue
                try:
                    chain = pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.create_task(take_next())
                if not isinstance(chain, MessageChain):
                    continue
                if chain.type == "reasoning":
                    continue
                if chain.type == "break":
                    await flush_text()
                    continue
                if chain.type == "tool_call":
                    await flush_text()
                    attempts.append(await self._send_streaming_fragment(chain))
                    continue
                for component in chain.chain:
                    if isinstance(component, Plain):
                        buffer += component.text
                        if len(buffer) >= STREAM_MIN_CHARS:
                            await flush_text()
                        continue
                    if isinstance(component, Markdown) and component.content:
                        buffer += component.content
                        if len(buffer) >= STREAM_MIN_CHARS:
                            await flush_text()
                        continue
                    await flush_text()
                    attempts.append(
                        await self._send_streaming_fragment(MessageChain([component]))
                    )
        finally:
            if not pending.done():
                pending.cancel()
                try:
                    await pending
                except asyncio.CancelledError:
                    if not pending.cancelled():
                        raise
                except StopAsyncIteration:
                    # anext() already closed the generator; cancel is a no-op.
                    pass

        await flush_text()
        if not attempts:
            return None
        return await self._streaming_result_from_attempts(
            attempts,
            generator,
            use_fallback,
        )
