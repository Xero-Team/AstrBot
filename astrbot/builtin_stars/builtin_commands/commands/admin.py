from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_dashboard


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """更新管理面板"""
        await event.send(MessageChain().message("⏳ Updating dashboard..."))
        await download_dashboard(version=f"v{VERSION}", latest=False)
        await event.send(MessageChain().message("✅ Dashboard updated successfully."))

    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """Grant admin permission."""
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "Usage: /op <id>. Use /sid to inspect the target user ID.",
                ),
            )
            return

        cfg = self.context.get_config(umo=event.unified_msg_origin)
        admin_ids = cfg.setdefault("admins_id", [])
        admin_id = str(admin_id)
        if admin_id not in admin_ids:
            admin_ids.append(admin_id)
            cfg.save_config()

        event.set_result(
            MessageEventResult().message(f"✅ Added {admin_id} to admin IDs."),
        )

    async def deop(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """Revoke admin permission."""
        if not admin_id:
            event.set_result(
                MessageEventResult().message(
                    "Usage: /deop <id>. Use /sid to inspect the target user ID.",
                ),
            )
            return

        cfg = self.context.get_config(umo=event.unified_msg_origin)
        admin_ids = cfg.setdefault("admins_id", [])
        admin_id = str(admin_id)
        if admin_id not in admin_ids:
            event.set_result(
                MessageEventResult().message(
                    f"❌ {admin_id} is not in the admin ID list.",
                ),
            )
            return

        admin_ids.remove(admin_id)
        cfg.save_config()
        event.set_result(
            MessageEventResult().message(f"✅ Removed {admin_id} from admin IDs."),
        )
