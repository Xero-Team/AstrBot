from astrbot.api import Subject, star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.platform import MAX_WATCH_TTL_SECONDS, MIN_WATCH_TTL_SECONDS

from .reply import reply_i18n


def _resolve_listener(token: str, current_umo: str) -> str:
    if token.lower() == "this":
        return current_umo
    return token


def parse_watch_spec(spec: str, current_umo: str) -> tuple[str, str, int | None]:
    """Parse `/session watch [listener|this] <target> [seconds]`."""
    parts = spec.split()
    if not parts or len(parts) > 3:
        raise ValueError("Invalid watch arguments")
    if len(parts) == 1:
        return current_umo, parts[0], None
    if len(parts) == 2:
        if parts[1].isdigit():
            return current_umo, parts[0], int(parts[1])
        return _resolve_listener(parts[0], current_umo), parts[1], None
    if not parts[2].isdigit():
        raise ValueError("Invalid watch arguments")
    return _resolve_listener(parts[0], current_umo), parts[1], int(parts[2])


def parse_unwatch_spec(spec: str, current_umo: str) -> tuple[str, str]:
    """Parse `/session unwatch [listener|this] <target>`."""
    parts = spec.split()
    if not parts or len(parts) > 2:
        raise ValueError("Invalid watch arguments")
    if len(parts) == 1:
        return current_umo, parts[0]
    return _resolve_listener(parts[0], current_umo), parts[1]


def _authorization_subject_id(event: AstrMessageEvent) -> str:
    """Return the authorization subject id for Dashboard binding import."""
    attached = getattr(event, "subject", None)
    attached_id = getattr(attached, "id", None)
    if isinstance(attached_id, str) and attached_id:
        return attached_id
    get_platform_id = getattr(event, "get_platform_id", None)
    platform_id = get_platform_id() if callable(get_platform_id) else None
    platform_instance = (
        platform_id if isinstance(platform_id, str) else event.get_platform_name()
    )
    return Subject.im(
        platform_instance=platform_instance,
        bot_account_id=event.get_self_id() or "default",
        sender_id=event.get_sender_id() or "unknown",
    ).id


class SessionCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def info(self, event: AstrMessageEvent) -> None:
        """Show identifiers and metadata for the current session."""
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        unique_session = bool(
            self.context.config.get()["platform_settings"]["unique_session"]
        )
        group_note = ""
        if unique_session and group_id:
            group_note = await self.context.i18n.t(
                event,
                "session.info.group",
                group_id=group_id,
            )
        await reply_i18n(
            self.context,
            event,
            "session.info.body",
            umo=umo,
            user_id=str(event.get_sender_id()),
            subject_id=_authorization_subject_id(event),
            platform_id=event.session.platform_id,
            message_type=event.session.message_type.value,
            session_id=event.session.session_id,
            group_note=group_note,
        )

    async def name(self, event: AstrMessageEvent, alias: str) -> None:
        """Show or set the display name for the current session."""
        umo = event.unified_msg_origin
        auto_name = self.context.sessions.auto_name(event)
        alias = self.context.sessions.normalize_name(alias)
        empty = await self.context.i18n.t(event, "session.name.empty")
        if not alias:
            saved_alias = await self.context.sessions.alias(umo)
            user_alias = self.context.sessions.normalize_name(
                saved_alias.user_alias if saved_alias else ""
            )
            await reply_i18n(
                self.context,
                event,
                "session.name.usage",
                umo=umo,
                auto_name=auto_name or empty,
                alias=user_alias or empty,
            )
            return

        await self.context.sessions.set_alias(
            umo=umo,
            creator_sender_id=str(event.get_sender_id() or ""),
            auto_name=auto_name,
            user_alias=alias,
        )
        await reply_i18n(
            self.context,
            event,
            "session.name.set",
            alias=alias,
            umo=umo,
        )

    async def watch(self, event: AstrMessageEvent, spec: str) -> None:
        """Watch another session under the trusted actor's authority."""
        try:
            source_umo, target_umo, ttl_seconds = parse_watch_spec(
                spec, event.unified_msg_origin
            )
            if ttl_seconds is not None and (
                ttl_seconds < MIN_WATCH_TTL_SECONDS
                or ttl_seconds > MAX_WATCH_TTL_SECONDS
            ):
                raise ValueError("Invalid watch duration")
            item = await self.context.bridges.watch(
                event,
                target_umo,
                source_umo=source_umo,
                ttl_seconds=ttl_seconds,
            )
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        except ValueError as exc:
            if str(exc) == "Invalid watch duration":
                await reply_i18n(self.context, event, "session.watch.ttl_invalid")
                return
            if str(exc) == "Invalid watch arguments":
                await reply_i18n(self.context, event, "session.watch.usage")
                return
            await reply_i18n(self.context, event, "session.watch.failed")
            return
        except LookupError:
            await reply_i18n(self.context, event, "session.watch.failed")
            return
        await reply_i18n(
            self.context,
            event,
            "session.watch.ok",
            source=item.source_umo,
            umo=item.target_umo,
            seconds=item.remaining_seconds,
        )

    async def unwatch(self, event: AstrMessageEvent, spec: str) -> None:
        """Stop a watch owned by the current actor."""
        try:
            source_umo, target_umo = parse_unwatch_spec(spec, event.unified_msg_origin)
        except ValueError:
            await reply_i18n(self.context, event, "session.unwatch.usage")
            return
        removed = await self.context.bridges.unwatch(
            event, target_umo, source_umo=source_umo
        )
        await reply_i18n(
            self.context,
            event,
            "session.unwatch.ok" if removed else "session.unwatch.missing",
        )

    async def watches(self, event: AstrMessageEvent) -> None:
        """List this actor's active watches in the current session."""
        items = await self.context.bridges.list(event)
        await reply_i18n(
            self.context,
            event,
            "session.watches.body" if items else "session.watches.empty",
            watches="\n".join(
                f"{item.target_umo} ({item.remaining_seconds}s)" for item in items
            ),
        )

    async def send(
        self, event: AstrMessageEvent, target_umo: str, content: str
    ) -> None:
        """Send the event's rich body; parsed text alone loses attachment order."""
        try:
            result = await self.context.bridges.send(event, target_umo.strip())
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        except ValueError, LookupError:
            await reply_i18n(self.context, event, "session.send.invalid")
            return
        await reply_i18n(self.context, event, f"session.send.{result.status}")
