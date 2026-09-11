import asyncio
import os
import re
from collections.abc import Callable
from typing import Any, Literal, cast
from urllib.parse import quote, unquote, urlsplit

import telegramify_markdown
from telegram import InputMediaPhoto, ReactionTypeCustomEmoji, ReactionTypeEmoji
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ExtBot

from astrbot import logger
from astrbot.core.message.components import (
    File,
    Image,
    Mention,
    MentionAll,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import AstrBotMessage, Group, MessageType, PlatformMetadata
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import DeliveryAttempt, PlatformSendResult
from astrbot.core.utils.error_redaction import safe_error

from .rate_limit import COALESCED, LimitedTelegramClient, TelegramDeliveryLimiter

DraftSendOutcome = Literal["sent", "bad_request", "failed", "skipped"]
TelegramClient = ExtBot | LimitedTelegramClient


def _is_draft_content_bad_request(error: BadRequest) -> bool:
    """Return whether a draft request can succeed after removing Markdown."""
    message = str(error).casefold()
    return "parse entities" in message or "message is too long" in message


def format_telegram_target(
    chat_id: str | int,
    message_thread_id: str | int | None,
    business_connection_id: str | None = None,
) -> str:
    """Keep chat, topic and Business namespace in a durable AstrBot target."""
    target = str(chat_id)
    if business_connection_id:
        target = f"business:{quote(business_connection_id, safe='')}:{target}"
    if message_thread_id is not None:
        target = f"{target}#{message_thread_id}"
    return target


def resolve_telegram_api_target(
    target_id: str,
) -> tuple[str, str | None, str | None]:
    """Resolve the Bot API chat, topic and Business connection parameters.

    Telegram's General topic has logical thread ID ``1`` but must be addressed
    by the parent chat without an explicit ``message_thread_id`` parameter.

    Returns:
        Chat ID, optional API thread ID, and optional Business connection ID.

    Raises:
        ValueError: The Business target lacks a connection or chat ID.
    """
    business_connection_id = None
    if target_id.startswith("business:"):
        _, encoded_connection_id, target_id = target_id.split(":", 2)
        business_connection_id = unquote(encoded_connection_id)
        if not business_connection_id or not target_id:
            raise ValueError("Invalid Telegram Business target")
    chat_id, separator, message_thread_id = target_id.partition("#")
    api_thread_id = (
        message_thread_id if separator and message_thread_id != "1" else None
    )
    return chat_id, api_thread_id, business_connection_id


def _is_gif(path: str) -> bool:
    if path.lower().endswith(".gif"):
        return True
    try:
        with open(path, "rb") as f:
            return f.read(6) in (b"GIF87a", b"GIF89a")
    except OSError:
        return False


def _escape_markdown_v2_text(text: str) -> str:
    """Escape user-controlled labels embedded in a MarkdownV2 link."""
    return re.sub(r"([_\*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


class TelegramPlatformEvent(AstrMessageEvent):
    # Telegram 的最大消息长度限制
    MAX_MESSAGE_LENGTH = 4096

    SPLIT_PATTERNS = {
        "paragraph": re.compile(r"\n\n"),
        "line": re.compile(r"\n"),
        "sentence": re.compile(r"[.!?。！？]"),
        "word": re.compile(r"\s"),
    }

    # sendMessageDraft 的 draft_id 类级递增计数器
    _TELEGRAM_DRAFT_ID_MAX = 2_147_483_647
    _next_draft_id: int = 0

    @classmethod
    def _allocate_draft_id(cls) -> int:
        """分配一个递增的 draft_id，溢出时归 1。"""
        cls._next_draft_id = (
            1
            if cls._next_draft_id >= cls._TELEGRAM_DRAFT_ID_MAX
            else cls._next_draft_id + 1
        )
        return cls._next_draft_id

    # 消息类型到 chat action 的映射，用于优先级判断
    ACTION_BY_TYPE: dict[type, str] = {
        Record: ChatAction.UPLOAD_VOICE,
        Video: ChatAction.UPLOAD_VIDEO,
        File: ChatAction.UPLOAD_DOCUMENT,
        Image: ChatAction.UPLOAD_PHOTO,
        Plain: ChatAction.TYPING,
    }

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: ExtBot,
        limiter: TelegramDeliveryLimiter | None = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._client: TelegramClient = (
            LimitedTelegramClient(client, limiter) if limiter is not None else client
        )

    @classmethod
    def _split_message(cls, text: str) -> list[str]:
        """Split raw Telegram text without changing or truncating it."""
        return [
            text[offset : offset + cls.MAX_MESSAGE_LENGTH]
            for offset in range(0, len(text), cls.MAX_MESSAGE_LENGTH)
        ]

    @classmethod
    async def _send_text_chunks(
        cls,
        client: TelegramClient,
        text: str,
        payload: dict[str, Any],
    ) -> None:
        """按 Telegram 限制切分文本后逐段发送。"""
        for chunk in cls._split_message(text):
            try:
                markdown_text = telegramify_markdown.markdownify(
                    chunk,
                )
                await client.send_message(
                    text=markdown_text,
                    parse_mode="MarkdownV2",
                    **cast(Any, payload),
                )
            except (ValueError, BadRequest) as e:
                logger.warning(
                    f"Failed to convert message to Markdown，using normal text: {e!s}"
                )
                await client.send_message(text=chunk, **cast(Any, payload))

    @classmethod
    async def _send_chat_action(
        cls,
        client: TelegramClient,
        chat_id: str,
        action: ChatAction | str,
        message_thread_id: str | None = None,
        business_connection_id: str | None = None,
    ) -> None:
        """Send a chat action in the originating Telegram namespace."""
        try:
            payload: dict[str, Any] = {"chat_id": chat_id, "action": action}
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            if business_connection_id:
                payload["business_connection_id"] = business_connection_id
            await client.send_chat_action(**payload)
        except Exception as e:
            logger.warning(f"[Telegram] 发送 chat action 失败: {e}")

    @classmethod
    def _get_chat_action_for_chain(cls, chain: list[Any]) -> ChatAction | str:
        """根据消息链中的组件类型确定合适的 chat action（按优先级）"""
        for seg_type, action in cls.ACTION_BY_TYPE.items():
            if any(isinstance(seg, seg_type) for seg in chain):
                return action
        return ChatAction.TYPING

    @classmethod
    async def _send_media_with_action(
        cls,
        client: TelegramClient,
        upload_action: ChatAction | str,
        send_coro,
        *,
        user_name: str,
        message_thread_id: str | None = None,
        **payload: Any,
    ) -> None:
        """发送媒体时显示 upload action，发送完成后恢复 typing"""
        effective_thread_id = message_thread_id or cast(
            str | None, payload.get("message_thread_id")
        )
        await cls._send_chat_action(
            client,
            user_name,
            upload_action,
            effective_thread_id,
            payload.get("business_connection_id"),
        )
        send_payload = dict(payload)
        if effective_thread_id and "message_thread_id" not in send_payload:
            send_payload["message_thread_id"] = effective_thread_id
        await send_coro(**send_payload)
        await cls._send_chat_action(
            client,
            user_name,
            ChatAction.TYPING,
            effective_thread_id,
            payload.get("business_connection_id"),
        )

    @classmethod
    async def _send_voice_with_fallback(
        cls,
        client: TelegramClient,
        path: str,
        payload: dict[str, Any],
        *,
        caption: str | None = None,
        user_name: str = "",
        message_thread_id: str | None = None,
        use_media_action: bool = False,
    ) -> None:
        """Send a voice message, falling back to a document if the user's
        privacy settings forbid voice messages (``BadRequest`` with
        ``Voice_messages_forbidden``).

        When *use_media_action* is ``True`` the helper wraps the send calls
        with ``_send_media_with_action`` (used by the streaming path).
        """
        try:
            if use_media_action:
                media_payload = dict(payload)
                if message_thread_id and "message_thread_id" not in media_payload:
                    media_payload["message_thread_id"] = message_thread_id
                await cls._send_media_with_action(
                    client,
                    ChatAction.UPLOAD_VOICE,
                    client.send_voice,
                    user_name=user_name,
                    voice=path,
                    **cast(Any, media_payload),
                )
            else:
                await client.send_voice(voice=path, **cast(Any, payload))
        except BadRequest as e:
            # python-telegram-bot raises BadRequest for Voice_messages_forbidden;
            # distinguish the voice-privacy case via the API error message.
            if "Voice_messages_forbidden" not in e.message:
                raise
            logger.warning(
                "User privacy settings prevent receiving voice messages, falling back to sending an audio file. "
                "To enable voice messages, go to Telegram Settings → Privacy and Security → Voice Messages → set to 'Everyone'."
            )
            if use_media_action:
                media_payload = dict(payload)
                if message_thread_id and "message_thread_id" not in media_payload:
                    media_payload["message_thread_id"] = message_thread_id
                await cls._send_media_with_action(
                    client,
                    ChatAction.UPLOAD_DOCUMENT,
                    client.send_document,
                    user_name=user_name,
                    document=path,
                    caption=caption,
                    **cast(Any, media_payload),
                )
            else:
                await client.send_document(
                    document=path,
                    caption=caption,
                    **cast(Any, payload),
                )

    async def _ensure_typing(
        self,
        user_name: str,
        message_thread_id: str | None = None,
    ) -> None:
        """确保显示 typing 状态"""
        _, _, business_connection_id = resolve_telegram_api_target(
            self.route_identity.target_id
        )
        await self._send_chat_action(
            self._client,
            user_name,
            ChatAction.TYPING,
            message_thread_id,
            business_connection_id,
        )

    async def send_typing(self) -> None:
        user_name, message_thread_id, _ = resolve_telegram_api_target(
            self.route_identity.target_id
        )

        await self._ensure_typing(user_name, message_thread_id)

    @classmethod
    async def send_with_client(
        cls,
        client: TelegramClient,
        message: MessageChain,
        user_name: str,
        limiter: TelegramDeliveryLimiter | None = None,
    ) -> None:
        if limiter is not None:
            client = LimitedTelegramClient(client, limiter)
        has_reply = False
        reply_message_id = None
        mention_prefix: list[str] = []
        for i in message.chain:
            if isinstance(i, Reply):
                has_reply = True
                reply_message_id = i.id
            elif isinstance(i, Mention):
                target = str(i.target)
                name = i.name or target
                if target.isdigit():
                    mention_prefix.append(
                        f"[{_escape_markdown_v2_text(name)}](tg://user?id={target})"
                    )
                else:
                    mention_prefix.append(f"@{name.lstrip('@')}")
            elif isinstance(i, MentionAll):
                logger.warning(
                    "Telegram has no Bot API token for notifying every group member; "
                    "ignoring MentionAll"
                )

        user_name, message_thread_id, business_connection_id = (
            resolve_telegram_api_target(user_name)
        )

        # 根据消息链确定合适的 chat action 并发送
        action = cls._get_chat_action_for_chain(message.chain)
        await cls._send_chat_action(
            client, user_name, action, message_thread_id, business_connection_id
        )

        mention_prefix_text = " ".join(mention_prefix)
        index = 0
        while index < len(message.chain):
            i = message.chain[index]
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = str(reply_message_id)
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            if business_connection_id:
                payload["business_connection_id"] = business_connection_id

            if isinstance(i, Plain):
                text = (
                    f"{mention_prefix_text} {i.text}" if mention_prefix_text else i.text
                )
                await cls._send_text_chunks(client, text, payload)
                mention_prefix_text = ""
            elif isinstance(i, Image):
                run: list[Image] = []
                while index < len(message.chain) and isinstance(
                    message.chain[index], Image
                ):
                    run.append(cast(Image, message.chain[index]))
                    index += 1
                caption = None
                if len(run) >= 2 and index < len(message.chain):
                    following = message.chain[index]
                    if isinstance(following, Plain) and following.text:
                        caption = following.text
                        index += 1
                if mention_prefix_text:
                    if caption:
                        caption = f"{mention_prefix_text} {caption}"
                    elif len(run) < 2:
                        await cls._send_text_chunks(
                            client, mention_prefix_text, payload
                        )
                    mention_prefix_text = ""
                await cls._send_image_run(client, run, payload, caption=caption)
                continue
            elif isinstance(i, File):
                path = await i.get_file()
                name = i.name or os.path.basename(path)
                await client.send_document(
                    document=path, filename=name, **cast(Any, payload)
                )
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await cls._send_voice_with_fallback(
                    client,
                    path,
                    payload,
                    caption=i.text or None,
                    use_media_action=False,
                )
            elif isinstance(i, Video):
                path = await i.convert_to_file_path()
                await client.send_video(
                    video=path,
                    caption=getattr(i, "text", None) or None,
                    **cast(Any, payload),
                )
            index += 1

    @classmethod
    async def _send_image_run(
        cls,
        client: ExtBot,
        images: list[Image],
        payload: dict[str, Any],
        *,
        caption: str | None = None,
    ) -> None:
        """Send compatible image runs as bounded albums with ordered fallback."""
        resolved = [(image, await image.convert_to_file_path()) for image in images]
        compatible = len(resolved) >= 2 and all(
            image.sub_type != "animation" and not _is_gif(path)
            for image, path in resolved
        )
        if compatible:
            sent = 0
            for start in range(0, len(resolved), 10):
                chunk = resolved[start : start + 10]
                if len(chunk) < 2:
                    break
                media = [
                    InputMediaPhoto(
                        media=path,
                        caption=caption if start == 0 and offset == 0 else None,
                    )
                    for offset, (_image, path) in enumerate(chunk)
                ]
                try:
                    await client.send_media_group(
                        media=media,
                        **cast(Any, payload),
                    )
                    sent += len(chunk)
                    continue
                except Exception as exc:
                    logger.warning(
                        "Telegram media group failed; falling back to ordered photos: %s",
                        safe_error("", exc),
                    )
                    break
            else:
                return
            resolved = resolved[sent:]
            if sent:
                caption = None
        for index, (image, path) in enumerate(resolved):
            item_caption = caption if index == 0 else None
            if image.sub_type == "animation" or _is_gif(path):
                send_payload = dict(payload)
                if item_caption is not None:
                    send_payload["caption"] = item_caption
                await client.send_animation(animation=path, **cast(Any, send_payload))
            else:
                send_payload = dict(payload)
                if item_caption is not None:
                    send_payload["caption"] = item_caption
                await client.send_photo(photo=path, **cast(Any, send_payload))

    async def send(self, message: MessageChain):
        await self.send_with_client(
            self._client,
            message,
            self.route_identity.target_id,
        )
        return await super().send(message)

    async def get_group(
        self, group_id: str | None = None, **kwargs: Any
    ) -> Group | None:
        """Get Telegram group metadata available to the bot.

        Telegram topics use ``<chat_id>#<thread_id>`` inside AstrBot. The Bot API
        calls target the parent chat while the returned group keeps the topic-aware ID.

        Args:
            group_id: AstrBot group ID to query. Defaults to the current group.
            **kwargs: Reserved for compatibility with the platform event interface.

        Returns:
            Enriched group metadata, or ``None`` when no group ID is available.
        """
        requested_group_id = str(group_id or self.get_group_id())
        if not requested_group_id:
            return None

        current_group = self.message_obj.group
        group = Group.from_inbound(current_group, requested_group_id)
        topic_name = (
            getattr(self.message_obj, "_telegram_topic_name", None)
            if current_group and current_group.group_id == requested_group_id
            else None
        )
        chat_id, _, _ = resolve_telegram_api_target(requested_group_id)
        api_chat_id: str | int = (
            int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        )

        try:
            chat = await self._client.get_chat(chat_id=api_chat_id)
            title = getattr(chat, "title", None)
            if isinstance(title, str):
                group.group_name = (
                    f"{title}-{topic_name}"
                    if isinstance(topic_name, str) and topic_name
                    else title
                )

            photo = getattr(chat, "photo", None)
            file_id = getattr(photo, "big_file_id", None) if photo else None
            if file_id:
                try:
                    photo_file = await self._client.get_file(file_id=file_id)
                    group.group_avatar = self._resolve_telegram_file_url(
                        getattr(photo_file, "file_path", None),
                    )
                except Exception as exc:
                    logger.warning(
                        "[Telegram] Failed to get group photo for %s: %s",
                        chat_id,
                        safe_error("", exc),
                    )
                    group.group_avatar = None
        except Exception as exc:
            logger.warning(
                "[Telegram] Failed to get group information for %s: %s",
                chat_id,
                safe_error("", exc),
            )

        try:
            group.member_count = await self._client.get_chat_member_count(
                chat_id=api_chat_id
            )
        except Exception as exc:
            logger.warning(
                "[Telegram] Failed to get group member count for %s: %s",
                chat_id,
                safe_error("", exc),
            )

        try:
            administrators = await self._client.get_chat_administrators(
                chat_id=api_chat_id
            )
            group.group_admins = []
            for administrator in administrators:
                status = getattr(administrator, "status", None)
                user = getattr(administrator, "user", None)
                user_id = getattr(user, "id", None)
                if user_id is None:
                    continue
                if status == "creator":
                    group.group_owner = str(user_id)
                elif status == "administrator":
                    group.group_admins.append(str(user_id))
        except Exception as exc:
            logger.warning(
                "[Telegram] Failed to get group administrators for %s: %s",
                chat_id,
                safe_error("", exc),
            )

        return group

    def _resolve_telegram_file_url(self, file_path: object) -> str | None:
        """Join a Bot API file path with the adapter file base URL.

        Args:
            file_path: Relative Bot API path or already-absolute file URL.

        Returns:
            A usable file URL, or ``None`` when the path cannot be resolved.
        """
        path = str(file_path or "").strip()
        if not path:
            return None
        if urlsplit(path).scheme:
            return path
        base = str(getattr(self._client, "base_file_url", "") or "").rstrip("/")
        if not base:
            return None
        return f"{base}/{path.lstrip('/')}"

    async def react(self, emoji: str | None, big: bool = False) -> None:
        """给原消息添加 Telegram 反应：
        - 普通 emoji：传入 '👍'、'😂' 等
        - 自定义表情：传入其 custom_emoji_id（纯数字字符串）
        - 取消本机器人的反应：传入 None 或空字符串
        """
        try:
            chat_id, _, business_connection_id = resolve_telegram_api_target(
                self.route_identity.target_id
            )
            if business_connection_id:
                logger.debug("Telegram Business reactions are unsupported")
                return
            message_id = int(self.message_obj.message_id)

            # 组装 reaction 参数（必须是 ReactionType 的列表）
            if not emoji:  # 清空本 bot 的反应
                reaction_param = []  # 空列表表示移除本 bot 的反应
            elif emoji.isdigit():  # 自定义表情：传 custom_emoji_id
                reaction_param = [ReactionTypeCustomEmoji(emoji)]
            else:  # 普通 emoji
                reaction_param = [ReactionTypeEmoji(emoji)]

            await self._client.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=reaction_param,  # 注意是列表
                is_big=big,  # 可选：大动画
            )
        except Exception as e:
            logger.error(f"[Telegram] 添加反应失败: {e}")

    async def _send_message_draft(
        self,
        chat_id: str,
        draft_id: int,
        text: str,
        message_thread_id: str | None = None,
        parse_mode: str | None = None,
    ) -> DraftSendOutcome:
        """通过 Bot.send_message_draft 发送草稿消息（流式推送部分消息）。

        该 API 仅支持私聊。

        Args:
            chat_id: 目标私聊的 chat_id
            draft_id: 草稿唯一标识，非零整数；相同 draft_id 的变更会以动画展示
            text: 消息文本，1-4096 字符
            message_thread_id: 可选，目标消息线程 ID
            parse_mode: 可选，消息文本的解析模式

        Returns:
            ``sent``、``bad_request``、``failed`` 或 ``skipped``。
        """
        if not text or not text.strip():
            return "skipped"

        try:
            kwargs: dict[str, Any] = {}
            if message_thread_id:
                kwargs["message_thread_id"] = int(message_thread_id)
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            logger.debug(
                f"[Telegram] sendMessageDraft: chat_id={chat_id}, draft_id={draft_id}, text_len={len(text)}"
            )
            result = await self._client.send_message_draft(
                chat_id=int(chat_id),
                draft_id=draft_id,
                text=text,
                **kwargs,
            )
            if result is COALESCED:
                return "skipped"
            return "sent"
        except asyncio.CancelledError:
            raise
        except (TypeError, ValueError) as e:
            logger.warning(f"[Telegram] sendMessageDraft 参数无效: {safe_error('', e)}")
            return "failed"
        except BadRequest as e:
            logger.warning(f"[Telegram] sendMessageDraft 请求无效: {safe_error('', e)}")
            if parse_mode and _is_draft_content_bad_request(e):
                return "bad_request"
            return "failed"
        except Exception as e:
            logger.warning(f"[Telegram] sendMessageDraft 失败: {safe_error('', e)}")
            return "failed"

    async def _process_chain_items(
        self,
        chain: MessageChain,
        payload: dict[str, Any],
        user_name: str,
        message_thread_id: str | None,
        on_text: Callable[[str], None],
    ) -> None:
        """处理 MessageChain 中的各类组件，文本通过 on_text 回调追加，媒体直接发送。"""
        for i in chain.chain:
            if isinstance(i, Plain):
                on_text(i.text)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                if i.sub_type == "animation" or _is_gif(image_path):
                    action = ChatAction.UPLOAD_VIDEO
                    send_coro = self._client.send_animation
                    media_kwarg = {"animation": image_path}
                else:
                    action = ChatAction.UPLOAD_PHOTO
                    send_coro = self._client.send_photo
                    media_kwarg = {"photo": image_path}
                await self._send_media_with_action(
                    self._client,
                    action,
                    send_coro,
                    user_name=user_name,
                    **media_kwarg,
                    **cast(Any, payload),
                )
            elif isinstance(i, File):
                path = await i.get_file()
                name = i.name or os.path.basename(path)
                await self._send_media_with_action(
                    self._client,
                    ChatAction.UPLOAD_DOCUMENT,
                    self._client.send_document,
                    user_name=user_name,
                    document=path,
                    filename=name,
                    **cast(Any, payload),
                )
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await self._send_voice_with_fallback(
                    self._client,
                    path,
                    payload,
                    caption=i.text or None,
                    user_name=user_name,
                    message_thread_id=message_thread_id,
                    use_media_action=True,
                )
            elif isinstance(i, Video):
                path = await i.convert_to_file_path()
                await self._send_media_with_action(
                    self._client,
                    ChatAction.UPLOAD_VIDEO,
                    self._client.send_video,
                    user_name=user_name,
                    video=path,
                    **cast(Any, payload),
                )
            else:
                logger.warning(f"不支持的消息类型: {type(i)}")

    async def _send_final_segment(self, delta: str, payload: dict[str, Any]) -> None:
        """将累积文本作为 MarkdownV2 真实消息发送，失败时回退到纯文本。"""
        await self._send_text_chunks(self._client, delta, payload)

    async def send_streaming(self, generator, use_fallback: bool = False):
        user_name, message_thread_id, business_connection_id = (
            resolve_telegram_api_target(self.route_identity.target_id)
        )
        payload = {
            "chat_id": user_name,
        }
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if business_connection_id:
            payload["business_connection_id"] = business_connection_id

        # Drafts cannot address a Business connection.
        use_draft = (
            self.get_message_type() == MessageType.FRIEND_MESSAGE
            and business_connection_id is None
        )

        if use_draft:
            logger.info("[Telegram] 流式输出: 使用 sendMessageDraft (私聊)")
            await self._send_streaming_draft(
                user_name, message_thread_id, payload, generator
            )
        else:
            logger.info("[Telegram] Streaming through send/edit messages")
            return await self._send_streaming_edit(
                user_name, message_thread_id, payload, generator
            )

        return await super().send_streaming(generator, use_fallback)

    async def _send_streaming_draft(
        self,
        user_name: str,
        message_thread_id: str | None,
        payload: dict[str, Any],
        generator,
    ) -> None:
        """使用 sendMessageDraft API 进行流式推送（私聊专用）。

        流式过程中使用 sendMessageDraft 推送草稿动画，
        流式结束后发送一条真实消息保留最终内容（draft 是临时的，会消失）。
        使用信号驱动的发送循环：每次有新 token 到达时唤醒发送，
        发送频率由网络 RTT 自然限制（最多一个请求 in-flight）。
        """
        draft_id = self._allocate_draft_id()
        delta = ""
        last_sent_text = ""
        done = False  # 信号：生成器已结束
        text_changed = asyncio.Event()  # 有新 token 到达时触发

        async def _draft_sender_loop() -> None:
            """信号驱动的草稿发送循环，有新内容就发，RTT 自然限流。"""
            nonlocal last_sent_text
            while not done:
                await text_changed.wait()
                text_changed.clear()
                if done:
                    break
                # 发送最新的缓冲区内容（MarkdownV2 渲染，与真实消息一致）
                if delta and delta != last_sent_text:
                    draft_text = delta[: self.MAX_MESSAGE_LENGTH]
                    if draft_text != last_sent_text:
                        try:
                            md = telegramify_markdown.markdownify(
                                draft_text,
                            )
                            outcome = await self._send_message_draft(
                                user_name,
                                draft_id,
                                md,
                                message_thread_id,
                                parse_mode="MarkdownV2",
                            )
                            if outcome == "bad_request":
                                outcome = await self._send_message_draft(
                                    user_name,
                                    draft_id,
                                    draft_text,
                                    message_thread_id,
                                )
                            if outcome == "sent":
                                last_sent_text = draft_text
                        except Exception:
                            # markdownify 对未闭合语法可能失败，回退纯文本
                            outcome = await self._send_message_draft(
                                user_name,
                                draft_id,
                                draft_text,
                                message_thread_id,
                            )
                            if outcome == "sent":
                                last_sent_text = draft_text

        sender_task = asyncio.create_task(_draft_sender_loop())

        def _append_text(t: str) -> None:
            nonlocal delta
            delta += t
            text_changed.set()  # 唤醒发送循环

        try:
            async for chain in generator:
                if not isinstance(chain, MessageChain):
                    continue

                if chain.type == "break":
                    # 分割符：发送真实消息保留内容，重置缓冲区
                    if delta:
                        # 用 emoji 清空 draft 显示，避免 draft 和真实消息同时可见
                        await self._send_message_draft(
                            user_name,
                            draft_id,
                            "\u23f3",
                            message_thread_id,
                        )
                        await self._send_final_segment(delta, payload)
                    delta = ""
                    last_sent_text = ""
                    draft_id = self._allocate_draft_id()
                    continue

                await self._process_chain_items(
                    chain, payload, user_name, message_thread_id, _append_text
                )
        finally:
            done = True
            text_changed.set()  # 唤醒循环使其退出
            await sender_task

        # 流式结束：用 emoji 清空 draft，然后发真实消息持久化
        if delta:
            await self._send_message_draft(
                user_name,
                draft_id,
                "\u23f3",
                message_thread_id,
            )
            await self._send_final_segment(delta, payload)

    async def _send_streaming_edit(
        self,
        user_name: str,
        message_thread_id: str | None,
        payload: dict[str, Any],
        generator,
    ) -> PlatformSendResult:
        """Stream with sends and edits for group or Business chats."""
        edit_payload = {"chat_id": payload["chat_id"]}
        if "business_connection_id" in payload:
            edit_payload["business_connection_id"] = payload["business_connection_id"]
        delta = ""
        current_content = ""
        message_id = None
        attempts: list[DeliveryAttempt] = []
        delivery_failed = False
        last_edit_time = 0  # 上次编辑消息的时间
        throttle_interval = 0.6  # 编辑消息的间隔时间 (秒)
        last_chat_action_time = 0  # 上次发送 chat action 的时间
        chat_action_interval = 0.5  # chat action 的节流间隔 (秒)

        # 发送初始 typing 状态
        await self._ensure_typing(user_name, message_thread_id)
        last_chat_action_time = asyncio.get_running_loop().time()

        def _append_text(t: str) -> None:
            nonlocal delta
            delta += t

        async def update_message(text: str, *, final: bool) -> bool:
            """Send or update the active segment and retain its accepted text."""
            nonlocal current_content, message_id
            try:
                if message_id is None:
                    message = await self._client.send_message(
                        text=text, **cast(Any, payload)
                    )
                    message_id = message.message_id
                elif current_content != text:
                    result = await self._client.edit_message_text(
                        text=text,
                        message_id=message_id,
                        **edit_payload,
                    )
                    if result is COALESCED:
                        return True
                current_content = text
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Telegram streaming submission failed: %s", safe_error("", exc)
                )
                if current_content:
                    attempts.append(
                        DeliveryAttempt(
                            status="accepted",
                            message_count=1,
                            message_ids=(str(message_id),),
                            semantic_text=current_content,
                        )
                    )
                attempts.append(
                    DeliveryAttempt(
                        status="failed",
                        semantic_text=text[len(current_content) :],
                        error_summary="telegram streaming submission failed",
                    )
                )
                return False

            if final:
                attempts.append(
                    DeliveryAttempt(
                        status="accepted",
                        message_count=1,
                        message_ids=(str(message_id),),
                        semantic_text=text,
                    )
                )
            return True

        async def finalize_segment() -> bool:
            """Persist the active raw segment before opening another message."""
            nonlocal current_content, delta, message_id
            if not delta:
                return True
            if not await update_message(delta, final=True):
                return False
            try:
                markdown_text = telegramify_markdown.markdownify(delta)
                if (
                    markdown_text != delta
                    and len(markdown_text) <= self.MAX_MESSAGE_LENGTH
                ):
                    await self._client.edit_message_text(
                        text=markdown_text,
                        message_id=message_id,
                        parse_mode="MarkdownV2",
                        **edit_payload,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Telegram streaming Markdown finalization failed: %s",
                    safe_error("", exc),
                )
            current_content = ""
            delta = ""
            message_id = None
            return True

        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue

            if chain.type == "break":
                if not await finalize_segment():
                    delivery_failed = True
                    break
                continue

            for component in chain.chain:
                if isinstance(component, Reply):
                    payload["reply_to_message_id"] = str(component.id)

            await self._process_chain_items(
                chain, payload, user_name, message_thread_id, _append_text
            )

            while len(delta) >= self.MAX_MESSAGE_LENGTH:
                overflow = delta[self.MAX_MESSAGE_LENGTH :]
                delta = delta[: self.MAX_MESSAGE_LENGTH]
                if not await finalize_segment():
                    if overflow:
                        attempts.append(
                            DeliveryAttempt(
                                status="skipped",
                                semantic_text=overflow,
                                error_summary="telegram stream stopped after submission failure",
                            )
                        )
                    delivery_failed = True
                    break
                delta = overflow
            if not delivery_failed and delta:
                current_time = asyncio.get_running_loop().time()
                time_since_last_edit = current_time - last_edit_time
                if message_id is None or time_since_last_edit >= throttle_interval:
                    current_time = asyncio.get_running_loop().time()
                    if current_time - last_chat_action_time >= chat_action_interval:
                        await self._ensure_typing(user_name, message_thread_id)
                        last_chat_action_time = current_time
                    if not await update_message(delta, final=False):
                        delivery_failed = True
                        break
                    last_edit_time = asyncio.get_running_loop().time()

            if delivery_failed:
                break

        if delta and not delivery_failed:
            await finalize_segment()
        await self._record_streaming_send()
        return PlatformSendResult.from_delivery_attempts(
            attempts,
            platform_id=self.get_platform_id(),
            target=self.route_identity.target_id,
        )
