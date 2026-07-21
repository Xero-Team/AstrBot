from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult


class AdminCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def list_admins(self, event: AstrMessageEvent) -> None:
        """List configured administrator IDs."""
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        admin_ids = [str(admin_id) for admin_id in cfg.get("admins_id", [])]
        if not admin_ids:
            message = "✅ No administrator IDs are configured."
        else:
            entries = "\n".join(f"- {admin_id}" for admin_id in admin_ids)
            message = f"✅ Administrator IDs:\n{entries}"

        event.set_result(MessageEventResult().message(message).use_t2i(False))

    async def grant(self, event: AstrMessageEvent, admin_id: str) -> None:
        """Grant admin permission."""
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        admin_ids = cfg.setdefault("admins_id", [])
        admin_id = str(admin_id)
        if admin_id not in admin_ids:
            admin_ids.append(admin_id)
            cfg.save_config()

        event.set_result(
            MessageEventResult().message(f"✅ Added {admin_id} to admin IDs."),
        )

    async def revoke(self, event: AstrMessageEvent, admin_id: str) -> None:
        """Revoke admin permission."""
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
