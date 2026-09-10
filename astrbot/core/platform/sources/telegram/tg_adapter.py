import asyncio
import math
import re
import uuid
from collections.abc import Sequence
from contextlib import suppress
from typing import override

import httpx
from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import BotCommand, MessageEntity, Update
from telegram.constants import ChatType
from telegram.error import Forbidden, InvalidToken, NetworkError
from telegram.ext import ApplicationBuilder, ContextTypes, filters
from telegram.ext import MessageHandler as TelegramMessageHandler
from telegram.request import HTTPXRequest

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    Group,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.proxy_route import (
    destination_host_from_url,
    resolve_proxy_route,
)
from astrbot.utils.http_ssl_common import build_ssl_context_with_certifi

from .tg_event import TelegramPlatformEvent


def _telegram_member_status(raw_message: object) -> str | None:
    if raw_message is None:
        return None
    for attr in ("chat_member", "my_chat_member"):
        change = getattr(raw_message, attr, None)
        new_member = (
            getattr(change, "new_chat_member", None) if change is not None else None
        )
        status = getattr(new_member, "status", None)
        if status is not None:
            return str(getattr(status, "value", status))
    return None


@register_platform_adapter("telegram", "telegram 适配器")
class TelegramPlatformAdapter(Platform):
    _FORUM_TOPIC_NAME_CACHE_MAX_SIZE = 1000
    _MEDIA_GROUP_MAX_ACTIVE = 128
    _MEDIA_GROUP_MAX_ITEMS = 10
    _MEDIA_GROUP_PROCESS_TIMEOUT = 60.0

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings

        base_url = self.config.get(
            "telegram_api_base_url",
            "https://api.telegram.org/bot",
        )
        if not base_url:
            base_url = "https://api.telegram.org/bot"

        file_base_url = self.config.get(
            "telegram_file_base_url",
            "https://api.telegram.org/file/bot",
        )
        if not file_base_url:
            file_base_url = "https://api.telegram.org/file/bot"

        self.base_url = base_url
        self.file_base_url = file_base_url

        self.enable_command_register = self.config.get(
            "telegram_command_register",
            True,
        )
        self.enable_command_refresh = self.config.get(
            "telegram_command_auto_refresh",
            True,
        )
        self._last_command_snapshot: tuple[tuple[str, str], ...] | None = None
        self._command_refresh_lock = asyncio.Lock()

        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_listener(
            lambda ev: logger.error(
                "Scheduled job %s raised: %s",
                ev.job_id,
                ev.exception,
                exc_info=ev.exception,
            ),
            EVENT_JOB_ERROR,
        )
        self._terminating = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._polling_recovery_requested = asyncio.Event()
        self._consecutive_polling_failures = 0
        self._last_polling_failure_at = 0.0
        raw_delay = self.config.get("telegram_polling_restart_delay", 5.0)
        try:
            delay = float(raw_delay)
        except TypeError, ValueError:
            logger.warning(
                "Invalid 'telegram_polling_restart_delay' value %r in config, "
                "falling back to default 5.0s",
                raw_delay,
            )
            delay = 5.0

        if delay < 0.1:
            logger.warning(
                "Configured 'telegram_polling_restart_delay' (%s) is too small; "
                "enforcing minimum of 0.1s to avoid tight restart loops",
                delay,
            )
            delay = 0.1
        self._polling_restart_delay = delay
        self._polling_recovery_threshold = 3
        self._polling_failure_window = 60.0
        self._application_started = False
        self._forum_topic_names: dict[tuple[str, int | None], str] = {}
        self._build_application()

        # Media groups own their asyncio tasks. Command menu refresh intentionally
        # remains on ``scheduler`` because either menu setting may be disabled.
        self.media_group_cache: dict[str, dict] = {}
        self._media_group_tasks: dict[str, asyncio.Task[None]] = {}
        self._accept_media_groups = True
        self.media_group_timeout = self._media_group_duration(
            "telegram_media_group_timeout", 2.5
        )
        self.media_group_max_wait = self._media_group_duration(
            "telegram_media_group_max_wait", 10.0
        )

    def _media_group_duration(self, key: str, default: float) -> float:
        raw_value = self.config.get(key, default)
        if isinstance(raw_value, bool):
            raw_value = default
        try:
            value = float(raw_value)
        except TypeError, ValueError:
            value = default

        if not math.isfinite(value) or value <= 0:
            logger.warning("Invalid '%s' value; using %.1fs", key, default)
            return default
        return value

    def _build_application(self) -> None:
        api_host = destination_host_from_url(self.base_url)
        api_route = resolve_proxy_route(
            local_config=self.config,
            destination_host=api_host,
        )
        file_host = destination_host_from_url(self.file_base_url)
        file_route = resolve_proxy_route(
            local_config=self.config,
            destination_host=file_host,
        )
        ssl_context = build_ssl_context_with_certifi()
        bot_httpx_kwargs = {
            "trust_env": api_route.trust_env,
            "verify": ssl_context,
        }
        if file_host and file_route.httpx_proxy != api_route.httpx_proxy:
            bot_httpx_kwargs["mounts"] = {
                f"all://{file_host}": httpx.AsyncHTTPTransport(
                    proxy=file_route.httpx_proxy,
                    verify=ssl_context,
                )
            }

        builder = ApplicationBuilder()
        builder.request(
            HTTPXRequest(proxy=api_route.httpx_proxy, httpx_kwargs=bot_httpx_kwargs)
        )
        builder.get_updates_request(
            HTTPXRequest(
                proxy=api_route.httpx_proxy,
                httpx_kwargs={
                    "trust_env": api_route.trust_env,
                    "verify": ssl_context,
                },
            )
        )
        self.application = (
            builder.token(self.config["telegram_token"])
            .base_url(self.base_url)
            .base_file_url(self.file_base_url)
            .build()
        )
        message_handler = TelegramMessageHandler(
            filters=filters.ALL,
            callback=self.message_handler,
        )
        self.application.add_handler(message_handler)
        self.client = self.application.bot
        logger.debug(f"Telegram base url: {self.client.base_url}")

    async def _start_application(self) -> None:
        await self.application.initialize()
        await self.application.start()

        if self.enable_command_register:
            await self.register_commands()

        self._application_started = True
        self._accept_media_groups = True

    async def _shutdown_application(
        self,
        *,
        delete_commands: bool,
    ) -> None:
        self._application_started = False
        await self._cleanup_media_groups()

        updater = self.application.updater
        if updater is not None:
            with suppress(Exception):
                await updater.stop()

        if delete_commands and self.enable_command_register:
            with suppress(Exception):
                await self.client.delete_my_commands()

        with suppress(Exception):
            await self.application.stop()

        shutdown = getattr(self.application, "shutdown", None)
        if shutdown is not None:
            with suppress(Exception):
                await shutdown()

    async def _recreate_application(self) -> None:
        if self._terminating:
            self._polling_recovery_requested.clear()
            return

        logger.warning(
            "Telegram polling hit repeated network errors; rebuilding the "
            "Telegram application and HTTP client.",
        )
        await self._shutdown_application(delete_commands=False)
        self._build_application()
        self._consecutive_polling_failures = 0
        self._last_polling_failure_at = 0.0
        self._polling_recovery_requested.clear()

    def _start_command_scheduler(self) -> None:
        if not self.enable_command_refresh or not self.enable_command_register:
            return
        if self.scheduler.running:
            return

        self.scheduler.add_job(
            self.register_commands,
            "interval",
            seconds=self.config.get("telegram_command_register_interval", 300),
            id="telegram_command_register",
            misfire_grace_time=60,
        )
        self.scheduler.start()

    @override
    async def send_by_session(
        self,
        session: MessageSession,
        message_chain: MessageChain,
    ):
        from_username = session.session_id
        await TelegramPlatformEvent.send_with_client(
            self.client,
            message_chain,
            from_username,
        )
        return await super().send_by_session(session, message_chain)

    @override
    def meta(self) -> PlatformMetadata:
        id_ = self.config.get("id") or "telegram"
        return PlatformMetadata(name="telegram", description="telegram 适配器", id=id_)

    @override
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._start_command_scheduler()

        while not self._terminating:
            try:
                if not self._application_started:
                    await self._start_application()

                self._polling_recovery_requested.clear()
                updater = self.application.updater
                if updater is None:
                    logger.error(
                        "Telegram Updater is not initialized. Cannot start polling."
                    )
                    self._application_started = False
                    await asyncio.sleep(self._polling_restart_delay)
                    continue
                logger.info("Starting Telegram polling...")
                await updater.start_polling(error_callback=self._on_polling_error)
                logger.info("Telegram Platform Adapter is running.")
                while updater.running and not self._terminating:  # noqa: ASYNC110
                    if self._polling_recovery_requested.is_set():
                        await self._recreate_application()
                        break
                    await asyncio.sleep(1)
                else:
                    if not self._terminating:
                        logger.warning(
                            "Telegram polling loop exited unexpectedly, "
                            f"retrying in {self._polling_restart_delay}s."
                        )
                    continue

                if not self._terminating:
                    logger.info("Telegram polling restarted with a fresh client.")
                    continue
            except asyncio.CancelledError:
                raise
            except (Forbidden, InvalidToken) as e:
                logger.error(
                    f"Telegram token is invalid or unauthorized: {e}. Polling stopped."
                )
                break
            except Exception as e:
                logger.exception(
                    "Telegram polling crashed with exception: "
                    f"{type(e).__name__}: {e!s}. "
                    f"Retrying in {self._polling_restart_delay}s.",
                )
                with suppress(Exception):
                    await self._shutdown_application(delete_commands=False)
                self._build_application()

            if not self._terminating:
                await asyncio.sleep(self._polling_restart_delay)

    def _on_polling_error(self, error: Exception) -> None:
        logger.error(
            f"Telegram polling request failed: {type(error).__name__}: {error!s}",
            exc_info=error,
        )
        if not isinstance(error, NetworkError):
            return

        if self._loop is None:
            return

        now = self._loop.time()
        if now - self._last_polling_failure_at > self._polling_failure_window:
            self._consecutive_polling_failures = 0
        self._last_polling_failure_at = now
        self._consecutive_polling_failures += 1

        if self._consecutive_polling_failures < self._polling_recovery_threshold:
            return

        logger.warning(
            "Telegram polling encountered %s network failures within %.1fs; "
            "scheduling client rebuild.",
            self._consecutive_polling_failures,
            self._polling_failure_window,
        )
        if self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(self._polling_recovery_requested.set)
        except RuntimeError:
            return

    async def register_commands(self) -> None:
        """收集所有注册的指令并注册到 Telegram"""
        async with self._command_refresh_lock:
            try:
                commands = self.collect_commands()
                snapshot = tuple((cmd.command, cmd.description) for cmd in commands)
                if snapshot == self._last_command_snapshot:
                    return
                await self.client.delete_my_commands()
                if commands:
                    await self.client.set_my_commands(commands)
                self._last_command_snapshot = snapshot

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"向 Telegram 注册指令时发生错误: {e!s}")

    @override
    async def refresh_registered_commands(self) -> None:
        if (
            self.enable_command_register
            and self._application_started
            and self.client is not None
        ):
            await self.register_commands()

    def collect_commands(self) -> list[BotCommand]:
        """从注册的处理器中收集所有指令"""
        command_dict = {}
        skip_commands = {"start"}

        for handler_md in self.get_handler_registry().get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            only_activated=False,
        ):
            plugin = self.get_plugin_registry().get_by_module(
                handler_md.handler_module_path,
            )
            if plugin is None or not plugin.activated:
                continue
            handler_metadata = handler_md
            for event_filter in handler_metadata.event_filters:
                cmd_info_list = self._extract_command_info(
                    event_filter,
                    handler_metadata,
                    skip_commands,
                )
                if cmd_info_list:
                    for cmd_name, description in cmd_info_list:
                        if cmd_name in command_dict:
                            logger.warning(
                                f"命令名 '{cmd_name}' 重复注册，将使用首次注册的定义: "
                                f"'{command_dict[cmd_name]}'"
                            )
                        command_dict.setdefault(cmd_name, description)

        commands_a = sorted(command_dict.keys())
        return [BotCommand(cmd, command_dict[cmd]) for cmd in commands_a]

    @staticmethod
    def _extract_command_info(
        event_filter,
        handler_metadata,
        skip_commands: set,
    ) -> list[tuple[str, str]] | None:
        """从事件过滤器中提取指令信息，包括所有别名"""
        cmd_names = []
        is_group = False
        if isinstance(event_filter, CommandFilter) and event_filter.command_name:
            if (
                event_filter.parent_command_names
                and event_filter.parent_command_names != [""]
            ):
                return None
            # 收集主命令名和所有别名
            cmd_names = [event_filter.command_name]
            if event_filter.alias:
                cmd_names.extend(event_filter.alias)
        elif isinstance(event_filter, CommandGroupFilter):
            if event_filter.parent_group:
                return None
            cmd_names = [event_filter.group_name, *sorted(event_filter.alias)]
            is_group = True

        result = []
        for cmd_name in cmd_names:
            if not cmd_name or cmd_name in skip_commands:
                continue
            if not re.match(r"^[a-z0-9_]+$", cmd_name) or len(cmd_name) > 32:
                continue

            # Build description.
            description = handler_metadata.desc or (
                f"Command group: {cmd_name}" if is_group else f"Command: {cmd_name}"
            )
            if len(description) > 30:
                description = description[:30] + "..."
            result.append((cmd_name, description))

        return result if result else None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat:
            logger.warning(
                "Received a start command without an effective chat, skipping /start reply.",
            )
            return
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.config["start_message"],
        )

    async def message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.debug(f"Telegram message: {update.message}")

        # Handle media group messages
        if update.message and update.message.media_group_id:
            await self.handle_media_group_message(update, context)
            return

        # Handle regular messages
        abm = await self.convert_message(update, context)
        if abm:
            await self.handle_msg(abm)

    @staticmethod
    async def _resolve_telegram_attachment_file_path(attachment) -> str | None:
        fetched = await attachment.get_file()
        file_path = getattr(fetched, "file_path", None)
        if not file_path:
            logger.warning("Telegram attachment file_path is None.")
            return None
        return str(file_path)

    @staticmethod
    def _normalize_telegram_mentions(
        text: str,
        entities: Sequence[MessageEntity] | None,
        bot_username: str,
        bot_id: int,
    ) -> tuple[str, list[Comp.Mention]]:
        """Extract mentions in entity order and remove own mentions from text."""
        # Telegram offsets count UTF-16 code units, not Python code points.
        boundaries = {0: 0}
        offset = 0
        for index, char in enumerate(text):
            offset += 2 if ord(char) > 0xFFFF else 1
            boundaries[offset] = index + 1

        mentions: list[Comp.Mention] = []
        removals: set[tuple[int, int]] = set()
        for entity in entities or ():
            if entity.type != "mention":
                continue
            if (
                type(entity.offset) is not int
                or type(entity.length) is not int
                or entity.length <= 0
            ):
                continue
            start = boundaries.get(entity.offset)
            end = boundaries.get(entity.offset + entity.length)
            if start is None or end is None:
                continue
            value = text[start:end]
            if re.fullmatch(r"@[A-Za-z0-9_]+", value) is None:
                continue
            name = value[1:]
            is_self_mention = name.lower() == bot_username.lower()
            target = str(bot_id) if is_self_mention else name
            mentions.append(Comp.Mention(target=target, name=name))
            if is_self_mention:
                removals.add((start, end))

        parts = []
        cursor = 0
        for start, end in sorted(removals):
            if start >= cursor:
                parts.append(text[cursor:start])
            cursor = max(cursor, end)
        parts.append(text[cursor:])
        return "".join(parts), mentions

    def _apply_telegram_caption(
        self,
        message: AstrBotMessage,
        telegram_message,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if telegram_message.caption:
            text, mentions = self._normalize_telegram_mentions(
                telegram_message.caption,
                telegram_message.caption_entities,
                context.bot.username,
                context.bot.id,
            )
            message.message_str = text
            if text:
                message.message.append(Comp.Plain(text))
            message.message.extend(mentions)

    async def _populate_telegram_message_content(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        message: AstrBotMessage,
    ) -> bool:
        """Populate text or media components; return False for /start."""
        telegram_message = update.message
        if telegram_message is None:
            return True

        if telegram_message.text:
            plain_text, mentions = self._normalize_telegram_mentions(
                telegram_message.text,
                telegram_message.entities,
                context.bot.username,
                context.bot.id,
            )
            message.message.extend(mentions)

            if plain_text.startswith("/"):
                command_parts = plain_text.split(" ", 1)
                if "@" in command_parts[0]:
                    command, bot_name = command_parts[0].split("@")
                    if bot_name == self.client.username:
                        plain_text = command + (
                            f" {command_parts[1]}" if len(command_parts) > 1 else ""
                        )

            if plain_text:
                message.message.append(Comp.Plain(plain_text))
            message.message_str = plain_text
            if message.message_str.strip() == "/start":
                await self.start(update, context)
                return False
            return True

        if telegram_message.voice:
            record = Comp.Record(file="")
            record.set_source_resolver(
                lambda voice=telegram_message.voice: (
                    self._resolve_telegram_attachment_file_path(voice)
                )
            )
            message.message.append(record)
        elif telegram_message.audio:
            record = Comp.Record(file="")
            record.set_source_resolver(
                lambda audio=telegram_message.audio: (
                    self._resolve_telegram_attachment_file_path(audio)
                )
            )
            message.message.append(record)
            self._apply_telegram_caption(message, telegram_message, context)
        elif telegram_message.photo:
            photo = telegram_message.photo[-1]
            image = Comp.Image(file="")
            image.set_source_resolver(
                lambda photo=photo: self._resolve_telegram_attachment_file_path(photo)
            )
            message.message.append(image)
            self._apply_telegram_caption(message, telegram_message, context)
        elif telegram_message.sticker:
            sticker = telegram_message.sticker
            sticker_attachment = sticker
            if getattr(sticker, "is_animated", False) or getattr(
                sticker, "is_video", False
            ):
                sticker_attachment = getattr(sticker, "thumbnail", None)
            if sticker_attachment is not None:
                image = Comp.Image(file="")
                image.set_source_resolver(
                    lambda sticker=sticker_attachment: (
                        self._resolve_telegram_attachment_file_path(sticker)
                    )
                )
                message.message.append(image)
            if sticker.emoji:
                sticker_text = f"Sticker: {sticker.emoji}"
                message.message_str = sticker_text
                message.message.append(Comp.Plain(sticker_text))
        elif telegram_message.document:
            file_name = telegram_message.document.file_name or uuid.uuid4().hex
            file_component = Comp.File(name=file_name)
            file_component.set_url_resolver(
                lambda document=telegram_message.document, file_name=file_name: (
                    self._resolve_telegram_document_url(document, file_name)
                )
            )
            message.message.append(file_component)
            self._apply_telegram_caption(message, telegram_message, context)
        elif telegram_message.video:
            file_name = telegram_message.video.file_name or uuid.uuid4().hex
            video = Comp.Video(file="")
            video.set_source_resolver(
                lambda video=telegram_message.video: (
                    self._resolve_telegram_attachment_file_path(video)
                )
            )
            message.message.append(video)
            self._apply_telegram_caption(message, telegram_message, context)
        elif telegram_message.video_note:
            video_note = telegram_message.video_note
            video = Comp.Video(file="")
            video.set_source_resolver(
                lambda video_note=video_note: (
                    self._resolve_telegram_attachment_file_path(video_note)
                )
            )
            message.message.append(video)
        return True

    async def convert_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        get_reply=True,
    ) -> AstrBotMessage | None:
        """转换 Telegram 的消息对象为 AstrBotMessage 对象。

        @param update: Telegram 的 Update 对象。
        @param context: Telegram 的 Context 对象。
        @param get_reply: 是否获取回复消息。这个参数是为了防止多个回复嵌套。
        """
        if not update.message:
            logger.warning("Received an update without a message.")
            return None

        message = AstrBotMessage()
        message.session_id = str(update.message.chat.id)

        # 获得是群聊还是私聊
        if update.message.chat.type == ChatType.PRIVATE:
            message.type = MessageType.FRIEND_MESSAGE
        else:
            message.type = MessageType.GROUP_MESSAGE
            chat_id = str(update.message.chat.id)
            group_id = chat_id
            is_forum = getattr(update.message.chat, "is_forum", False) is True
            raw_thread_id = (
                update.message.message_thread_id
                if update.message.is_topic_message
                else None
            )
            thread_id = (
                raw_thread_id
                if raw_thread_id and not (is_forum and raw_thread_id == 1)
                else None
            )
            if thread_id is not None:
                # Telegram Topic Group: include thread id to isolate per-topic sessions.
                group_id += "#" + str(thread_id)
                message.session_id = group_id

            chat_title = getattr(update.message.chat, "title", None)
            group_name = chat_title if isinstance(chat_title, str) else None
            topic_name = None
            topic_created = getattr(update.message, "forum_topic_created", None)
            topic_edited = getattr(update.message, "forum_topic_edited", None)
            discovered_topic_name = getattr(topic_created, "name", None)
            if not isinstance(discovered_topic_name, str):
                discovered_topic_name = getattr(topic_edited, "name", None)
            if not isinstance(discovered_topic_name, str):
                reply_message = update.message.reply_to_message
                reply_topic_created = getattr(
                    reply_message, "forum_topic_created", None
                )
                discovered_topic_name = getattr(reply_topic_created, "name", None)

            topic_key = None
            if thread_id is not None:
                topic_key = (chat_id, thread_id)
            elif is_forum:
                topic_key = (chat_id, None)

            if topic_key is not None:
                cached_topic_name = self._forum_topic_names.pop(topic_key, None)
                if (
                    isinstance(discovered_topic_name, str)
                    and discovered_topic_name.strip()
                ):
                    cached_topic_name = discovered_topic_name.strip()
                if cached_topic_name:
                    self._forum_topic_names[topic_key] = cached_topic_name
                    if (
                        len(self._forum_topic_names)
                        > self._FORUM_TOPIC_NAME_CACHE_MAX_SIZE
                    ):
                        oldest_topic_key = next(iter(self._forum_topic_names))
                        del self._forum_topic_names[oldest_topic_key]
                topic_name = cached_topic_name

            if group_name and topic_name:
                group_name = f"{group_name}-{topic_name}"
            message.group = Group(
                group_id=group_id,
                group_name=group_name,
            )
            setattr(message, "_telegram_topic_name", topic_name)
        message.message_id = str(update.message.message_id)
        _from_user = update.message.from_user
        if not _from_user:
            logger.warning("[Telegram] Received a message without a from_user.")
            return None
        message.sender = MessageMember(
            str(_from_user.id),
            _from_user.username or "Unknown",
        )
        message.self_id = str(context.bot.id)
        message.raw_message = update
        message.message_str = ""
        message.message = []

        if (
            get_reply
            and update.message.reply_to_message
            and not (
                update.message.is_topic_message
                and update.message.message_thread_id
                == update.message.reply_to_message.message_id
            )
        ):
            # 获取回复消息
            reply_update = Update(
                update_id=1,
                message=update.message.reply_to_message,
            )
            reply_abm = await self.convert_message(reply_update, context, False)

            if reply_abm:
                quote_text = getattr(update.message.quote, "text", None)
                reply_chain = reply_abm.message
                reply_message_str = reply_abm.message_str
                if isinstance(quote_text, str) and quote_text:
                    reply_chain = [Comp.Plain(quote_text)]
                    reply_message_str = quote_text
                message.message.append(
                    Comp.Reply(
                        id=reply_abm.message_id,
                        chain=reply_chain,
                        sender_id=reply_abm.sender.user_id,
                        sender_nickname=reply_abm.sender.nickname,
                        time=reply_abm.timestamp,
                        message_str=reply_message_str,
                        text=reply_message_str,
                        qq=reply_abm.sender.user_id,
                    ),
                )

        if not await self._populate_telegram_message_content(update, context, message):
            return None

        return message

    @staticmethod
    async def _resolve_telegram_document_url(
        document,
        file_name: str,
    ) -> tuple[str | None, str | None]:
        fetched = await document.get_file()
        file_path = getattr(fetched, "file_path", None)
        if not file_path:
            logger.warning(
                "Telegram document file_path is None, cannot resolve the file %s.",
                file_name,
            )
            return None, file_name
        return str(file_path), file_name

    async def handle_media_group_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle messages that are part of a media group (album).

        Caches incoming messages and schedules delayed processing to collect all
        media items before sending to the pipeline. Uses debounce mechanism with
        a hard cap (max_wait) to prevent indefinite delay.
        """
        if not update.message:
            return

        media_group_id = update.message.media_group_id
        if not media_group_id:
            return

        chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
        cache_key = f"{chat_id}:{media_group_id}"
        if not self._accept_media_groups:
            return

        loop = asyncio.get_running_loop()
        now = loop.time()
        entry = self.media_group_cache.get(cache_key)
        if entry is None:
            if len(self._media_group_tasks) >= self._MEDIA_GROUP_MAX_ACTIVE:
                logger.warning("Telegram media group capacity reached; dropping album")
                return
            entry = {
                "created_at": now,
                "deadline": now + self.media_group_max_wait,
                "items": [],
                "message_ids": set(),
                "event": asyncio.Event(),
                "processing": False,
            }
            self.media_group_cache[cache_key] = entry
            task = asyncio.create_task(
                self._wait_for_media_group(cache_key, media_group_id, entry),
                name=f"telegram-media-group-{media_group_id}",
            )
            self._media_group_tasks[cache_key] = task
            logger.debug("Created Telegram media group cache: %s", media_group_id)

        if entry["processing"]:
            return

        message_id = getattr(update.message, "message_id", None)
        message_ids: set[int | None] = entry["message_ids"]
        if message_id in message_ids:
            return
        if len(entry["items"]) >= self._MEDIA_GROUP_MAX_ITEMS:
            logger.warning("Telegram media group item capacity reached; dropping item")
            return

        message_ids.add(message_id)
        entry["items"].append((update, context))
        logger.debug(
            f"Add message to media group {media_group_id}, "
            f"currently has {len(entry['items'])} items.",
        )

        entry["deadline"] = min(
            now + self.media_group_timeout,
            entry["created_at"] + self.media_group_max_wait,
        )
        entry["event"].set()

    async def _wait_for_media_group(
        self, cache_key: str, media_group_id: str, entry: dict
    ) -> None:
        try:
            while True:
                remaining = entry["deadline"] - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                event: asyncio.Event = entry["event"]
                event.clear()
                try:
                    await asyncio.wait_for(event.wait(), timeout=remaining)
                except TimeoutError:
                    break

            entry["processing"] = True
            await asyncio.wait_for(
                self._process_media_group_entry(media_group_id, entry),
                timeout=self._MEDIA_GROUP_PROCESS_TIMEOUT,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            logger.warning("Telegram media group processing timed out")
        except Exception:
            logger.exception("Failed to process Telegram media group")
        finally:
            if self.media_group_cache.get(cache_key) is entry:
                self.media_group_cache.pop(cache_key, None)
            if self._media_group_tasks.get(cache_key) is asyncio.current_task():
                self._media_group_tasks.pop(cache_key, None)

    async def _cleanup_media_groups(self) -> None:
        self._accept_media_groups = False
        tasks = list(self._media_group_tasks.values())
        current_task = asyncio.current_task()
        for task in tasks:
            if task is not current_task:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.media_group_cache.clear()
        self._media_group_tasks.clear()

    async def _process_media_group_entry(
        self, media_group_id: str, entry: dict
    ) -> None:
        updates_and_contexts = entry["items"]
        if not updates_and_contexts:
            logger.warning(f"Media group {media_group_id} is empty")
            return

        logger.info(
            f"Processing media group {media_group_id}, total {len(updates_and_contexts)} items"
        )

        try:
            # Use the first update to create the base message (with reply, caption, etc.)
            first_update, first_context = updates_and_contexts[0]
            abm = await self.convert_message(first_update, first_context)

            if not abm:
                logger.warning(
                    f"Failed to convert the first message of media group {media_group_id}"
                )
                return

            # Add additional media from remaining updates by reusing convert_message
            for update, context in updates_and_contexts[1:]:
                # Convert the message but skip reply chains (get_reply=False)
                extra = await self.convert_message(update, context, get_reply=False)
                if not extra:
                    continue

                # Merge only the message components (keep base session/meta from first)
                abm.message.extend(extra.message)
                logger.debug(
                    f"Added {len(extra.message)} components to media group {media_group_id}"
                )

            # Process the merged message
            await self.handle_msg(abm)
        except Exception:
            logger.error(
                f"Failed to process media group {media_group_id}", exc_info=True
            )

    def create_event(self, message: AstrBotMessage) -> TelegramPlatformEvent:
        """Creates a Telegram message event.

        Args:
            message: AstrBot message object to wrap.

        Returns:
            Created Telegram message event.
        """
        event = TelegramPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
        )
        if not event.is_private_chat():
            status = _telegram_member_status(getattr(message, "raw_message", None))
            if status == "restricted":
                status = "member"
            event.set_platform_member_role(
                status if status is not None else "unknown",
                source="adapter",
            )
        return event

    async def handle_msg(self, message: AstrBotMessage) -> None:
        self.commit_event(self.create_event(message))

    async def terminate(self) -> None:
        try:
            self._terminating = True
            if self.scheduler.running:
                self.scheduler.shutdown()
            self._polling_recovery_requested.set()
            await self._shutdown_application(delete_commands=True)

            logger.info("Telegram adapter has been closed.")
        except Exception as e:
            logger.error(f"Error occurred while closing Telegram adapter: {e}")
