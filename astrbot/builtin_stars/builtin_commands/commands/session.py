from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.umo_alias import get_event_auto_name, normalize_umo_name


class SessionCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def info(self, event: AstrMessageEvent) -> None:
        """Show identifiers and metadata for the current session."""
        umo = event.unified_msg_origin
        user_id = str(event.get_sender_id())
        platform_id = event.session.platform_id
        message_type = event.session.message_type.value
        session_id = event.session.session_id
        message = (
            f"UMO: 「{umo}」\n"
            f"UID: 「{user_id}」\n"
            "*Use UMO to set whitelist and configure routing, use UID to set "
            "admin list(UMO 可用于设置白名单和配置文件路由，UID 可用于设置管理员列表)\n\n"
            "Your session information:\n"
            f"Bot ID: 「{platform_id}」\n"
            f"Message Type: 「{message_type}」\n"
            f"Session ID: 「{session_id}」\n\n"
        )

        if (
            self.context.get_config()["platform_settings"]["unique_session"]
            and event.get_group_id()
        ):
            message += (
                f"\n\nThe group's ID: 「{event.get_group_id()}」. "
                "Set this ID to whitelist to allow the entire group."
            )

        event.set_result(MessageEventResult().message(message).use_t2i(False))

    async def name(self, event: AstrMessageEvent, alias: str) -> None:
        """Show or set the display name for the current session."""
        umo = event.unified_msg_origin
        auto_name = get_event_auto_name(event)
        alias = normalize_umo_name(alias)
        if not alias:
            saved_alias = await self.context.get_db().get_umo_alias(umo)
            user_alias = normalize_umo_name(
                saved_alias.user_alias if saved_alias else ""
            )
            event.set_result(
                MessageEventResult()
                .message(
                    "\n".join(
                        [
                            "Usage: /session name <name>",
                            f"UMO: {umo}",
                            f"Auto name: {auto_name or '(empty)'}",
                            f"Alias: {user_alias or '(empty)'}",
                        ]
                    )
                )
                .use_t2i(False)
            )
            return

        sender_id = str(event.get_sender_id() or "")

        await self.context.get_db().upsert_umo_alias(
            umo=umo,
            creator_sender_id=sender_id,
            auto_name=auto_name,
            user_alias=alias,
        )

        event.set_result(
            MessageEventResult()
            .message(f"UMO name set to: {alias}\nUMO: {umo}")
            .use_t2i(False)
        )
