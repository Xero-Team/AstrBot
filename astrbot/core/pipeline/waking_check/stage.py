from collections.abc import AsyncGenerator, Callable

from astrbot import logger
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.utils.quoted_message.onebot_client import OneBotClient

from ..context import PipelineContext
from ..stage import Stage, register_stage

UNIQUE_SESSION_ID_BUILDERS: dict[str, Callable[[AstrMessageEvent], str | None]] = {
    "aiocqhttp": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "napcat": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "slack": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "dingtalk": lambda e: e.get_sender_id(),
    "qq_official": lambda e: e.get_sender_id(),
    "qq_official_webhook": lambda e: e.get_sender_id(),
    "lark": lambda e: f"{e.get_sender_id()}%{e.get_group_id()}",
    "misskey": lambda e: f"{e.get_session_id()}_{e.get_sender_id()}",
    "matrix": lambda e: f"{e.get_sender_id()}_{e.get_group_id() or e.get_session_id()}",
}


def build_unique_session_id(event: AstrMessageEvent) -> str | None:
    platform = event.get_platform_name()
    builder = UNIQUE_SESSION_ID_BUILDERS.get(platform)
    return builder(event) if builder else None


@register_stage
class WakingCheckStage(Stage):
    """检查是否需要唤醒。唤醒机器人有如下几点条件：

    1. 机器人被 @ 了
    2. 机器人的消息被提到了
    3. 以 wake_prefix 前缀开头，并且消息没有以 At 消息段开头
    4. 插件（Star）的 handler filter 通过
    5. 私聊情况下，位于 admins_id 列表中的管理员的消息（在白名单阶段中）
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化唤醒检查阶段

        Args:
            ctx (PipelineContext): 消息管道上下文对象, 包括配置和插件管理器

        """
        self.ctx = ctx
        self.session_plugins = SessionPluginManager(ctx.preferences)
        self.no_permission_reply = self.ctx.astrbot_config["platform_settings"].get(
            "no_permission_reply",
            True,
        )
        # 私聊是否需要 wake_prefix 才能唤醒机器人
        self.friend_message_needs_wake_prefix = self.ctx.astrbot_config[
            "platform_settings"
        ].get("friend_message_needs_wake_prefix", False)
        # 是否忽略机器人自己发送的消息
        self.ignore_bot_self_message = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_bot_self_message",
            False,
        )
        self.ignore_at_all = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_at_all",
            False,
        )
        self.disable_builtin_commands = self.ctx.astrbot_config.get(
            "disable_builtin_commands", False
        )
        platform_settings = self.ctx.astrbot_config.get("platform_settings", {})
        self.unique_session = platform_settings.get("unique_session", False)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None]:
        self._apply_unique_session(event)
        if self._is_bot_self_message(event):
            event.stop_event()
            return

        event.message_str = event.message_str.strip()
        self._assign_admin_role(event)
        is_wake = await self._detect_wake(event)
        (
            activated_handlers,
            handlers_parsed_params,
            permission_denied,
        ) = await self._collect_activated_handlers(event)
        if permission_denied:
            return

        activated_handlers = await self.session_plugins.filter_handlers_by_session(
            event,
            activated_handlers,
        )
        event.set_extra("activated_handlers", activated_handlers)
        event.set_extra("handlers_parsed_params", handlers_parsed_params)
        if not (is_wake or event.is_wake):
            event.stop_event()

    def _apply_unique_session(self, event: AstrMessageEvent) -> None:
        onebot_post_type = event.get_extra("onebot_post_type")
        should_keep_group_session = onebot_post_type in {"notice", "request"}
        if (
            self.unique_session
            and event.message_obj.type == MessageType.GROUP_MESSAGE
            and not should_keep_group_session
        ):
            sid = build_unique_session_id(event)
            if sid:
                event.session_id = sid

    def _is_bot_self_message(self, event: AstrMessageEvent) -> bool:
        return self.ignore_bot_self_message and (
            event.get_self_id() == event.get_sender_id()
        )

    def _assign_admin_role(self, event: AstrMessageEvent) -> None:
        for admin_id in self.ctx.astrbot_config["admins_id"]:
            if str(event.get_sender_id()) == admin_id:
                event.role = "admin"
                break

    async def _detect_wake(self, event: AstrMessageEvent) -> bool:
        wake_prefixes = self.ctx.astrbot_config["wake_prefix"]
        messages = event.get_messages()
        skip_private_wake = bool(event.get_extra("skip_private_wake", False))
        for wake_prefix in wake_prefixes:
            if event.message_str.startswith(wake_prefix):
                if (
                    not event.is_private_chat()
                    and messages
                    and isinstance(messages[0], At)
                    and str(messages[0].qq) != str(event.get_self_id())
                    and str(messages[0].qq) != "all"
                ):
                    # 如果是群聊，且第一个消息段是 At 消息，但不是 At 机器人或 At 全体成员，则不唤醒
                    break
                event.is_at_or_wake_command = True
                event.is_wake = True
                event.message_str = event.message_str[len(wake_prefix) :].strip()
                return True

        unresolved_replies: list[Reply] = []
        for message in messages:
            reply_sender_id = self._reply_sender_id(message)
            if self._message_wakes_event(message, event, reply_sender_id):
                event.is_wake = True
                event.is_at_or_wake_command = True
                return True
            if isinstance(message, Reply) and not reply_sender_id:
                unresolved_replies.append(message)
        if await self._unresolved_reply_wakes_event(event, unresolved_replies):
            return True
        if (
            event.is_private_chat()
            and not skip_private_wake
            and (
                not self.friend_message_needs_wake_prefix
                or event.get_platform_name() == "webchat"
            )
        ):
            event.is_wake = True
            event.is_at_or_wake_command = True
            return True
        return False

    @staticmethod
    def _reply_sender_id(message: object) -> str:
        if isinstance(message, Reply) and message.sender_id not in (None, "", 0, "0"):
            return str(message.sender_id)
        return ""

    def _message_wakes_event(
        self, message: object, event: AstrMessageEvent, reply_sender_id: str
    ) -> bool:
        return (
            (isinstance(message, At) and str(message.qq) == str(event.get_self_id()))
            or (isinstance(message, AtAll) and not self.ignore_at_all)
            or (
                isinstance(message, Reply)
                and reply_sender_id == str(event.get_self_id())
            )
        )

    async def _unresolved_reply_wakes_event(
        self, event: AstrMessageEvent, replies: list[Reply]
    ) -> bool:
        if not replies:
            return False
        onebot_client = OneBotClient(event)
        for reply in replies:
            resolved_sender_id = await onebot_client.get_msg_sender_id(reply.id)
            if not resolved_sender_id:
                continue
            reply.sender_id = resolved_sender_id
            if resolved_sender_id == str(event.get_self_id()):
                event.is_wake = True
                event.is_at_or_wake_command = True
                return True
        return False

    async def _collect_activated_handlers(
        self, event: AstrMessageEvent
    ) -> tuple[list, dict, bool]:
        activated_handlers = []
        handlers_parsed_params = {}

        enabled_plugins_name = self.ctx.astrbot_config.get("plugin_set", ["*"])
        event.plugins_name = (
            None if enabled_plugins_name == ["*"] else enabled_plugins_name
        )
        logger.debug(f"enabled_plugins_name: {enabled_plugins_name}")

        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=event.plugins_name,
        ):
            if (
                self.disable_builtin_commands
                and handler.handler_module_path
                == "astrbot.builtin_stars.builtin_commands.main"
            ):
                continue

            # filter 需满足 AND 逻辑关系
            passed = True
            permission_not_pass = False
            permission_filter_raise_error = False
            if len(handler.event_filters) == 0:
                continue

            for filter in handler.event_filters:
                try:
                    if isinstance(filter, PermissionTypeFilter):
                        if not filter.filter(event, self.ctx.astrbot_config):
                            permission_not_pass = True
                            permission_filter_raise_error = filter.raise_error
                    elif not filter.filter(event, self.ctx.astrbot_config):
                        passed = False
                        break
                except Exception as e:
                    await event.send(
                        MessageEventResult().message(
                            f"插件 {star_map[handler.handler_module_path].name}: {e}",
                        ),
                    )
                    event.stop_event()
                    passed = False
                    break
            if passed:
                if permission_not_pass:
                    if not permission_filter_raise_error:
                        # 跳过
                        continue
                    if self.no_permission_reply:
                        await event.send(
                            MessageChain().message(
                                f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。通过 /sid 获取 ID 并请管理员添加。",
                            ),
                        )
                    logger.info(
                        f"触发 {star_map[handler.handler_module_path].name} 时, 用户(ID={event.get_sender_id()}) 权限不足。",
                    )
                    event.stop_event()
                    return activated_handlers, handlers_parsed_params, True

                event.is_wake = True

                is_group_cmd_handler = any(
                    isinstance(f, CommandGroupFilter) for f in handler.event_filters
                )
                if not is_group_cmd_handler:
                    activated_handlers.append(handler)
                    if "parsed_params" in event.get_extra(default={}):
                        handlers_parsed_params[handler.handler_full_name] = (
                            event.get_extra("parsed_params")
                        )

            event._extras.pop("parsed_params", None)
        return activated_handlers, handlers_parsed_params, False
