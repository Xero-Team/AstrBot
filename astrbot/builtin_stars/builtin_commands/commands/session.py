from dataclasses import dataclass

from astrbot.api import Subject, star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.platform import (
    MAX_WATCH_TTL_SECONDS,
    MIN_WATCH_TTL_SECONDS,
    MessageSession,
)

from .reply import reply_i18n
from .target import resolve_target_umo

_RULE_ID_CHARS = frozenset("0123456789abcdef")
_FILTER_SIDES = frozenset({"match", "except"})
_COMMAND_DIMENSIONS = {
    "subject": "subjects",
    "role": "roles",
    "text": "text",
}


def _parse_rule_id(token: str) -> str:
    if len(token) != 12 or any(char not in _RULE_ID_CHARS for char in token):
        raise ValueError("Invalid filter arguments")
    return token


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


def _is_umo(token: str) -> bool:
    try:
        MessageSession.from_str(token)
    except ValueError, KeyError:
        return False
    return bool(token)


def parse_unwatch_spec(spec: str, current_umo: str) -> tuple[str, str]:
    """Parse `/session unwatch [listener|this] <target>`."""
    parts = spec.split()
    if not parts or len(parts) > 2:
        raise ValueError("Invalid watch arguments")
    if len(parts) == 1:
        return current_umo, parts[0]
    return _resolve_listener(parts[0], current_umo), parts[1]


def parse_unlink_spec(spec: str) -> str:
    """Parse `/session unlink <rule_id>`."""
    parts = spec.split()
    if len(parts) != 1:
        raise ValueError("Invalid unlink arguments")
    try:
        return _parse_rule_id(parts[0])
    except ValueError:
        raise ValueError("Invalid unlink arguments") from None


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """Parsed `/session filter` arguments."""

    rule_id: str
    action: str
    side: str = ""
    dimension: str = ""
    value: str = ""


def parse_filter_spec(spec: str) -> FilterSpec:
    """Parse `/session filter <rule_id> [match|except|clear ...]`.

    ``text`` consumes the remainder as ``GreedyStr``. ``clear`` without a
    side equals ``all``.
    """
    stripped = spec.strip()
    if not stripped:
        raise ValueError("Invalid filter arguments")
    parts = stripped.split()
    rule_id = _parse_rule_id(parts[0])
    if len(parts) == 1:
        return FilterSpec(rule_id, "show")
    if parts[1] == "clear":
        if len(parts) == 2:
            return FilterSpec(rule_id, "clear", "all")
        if len(parts) == 3 and parts[2] in {"match", "except", "all"}:
            return FilterSpec(rule_id, "clear", parts[2])
        raise ValueError("Invalid filter arguments")
    if parts[1] not in _FILTER_SIDES or len(parts) < 4:
        raise ValueError("Invalid filter arguments")
    command_dimension = parts[2]
    dimension = _COMMAND_DIMENSIONS.get(command_dimension)
    if dimension is None:
        raise ValueError("Invalid filter arguments")
    if command_dimension == "text":
        value = stripped.split(None, 3)[3]
    elif len(parts) == 4:
        value = parts[3]
    else:
        raise ValueError("Invalid filter arguments")
    return FilterSpec(rule_id, "append", parts[1], dimension, value)


def parse_pair_spec(spec: str) -> str:
    """Parse `/session pair <UMO>` and reject a duration token."""
    parts = spec.split()
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2 and parts[1].isdigit():
        raise ValueError("Invalid pair duration")
    raise ValueError("Invalid pair arguments")


def parse_unpair_spec(spec: str) -> str | None:
    """Parse `/session unpair [UMO]`."""
    parts = spec.split()
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    raise ValueError("Invalid unpair arguments")


def parse_watches_spec(spec: str, current_umo: str) -> str:
    """Parse `/session watches [listener|this]`."""
    parts = spec.split()
    if not parts:
        return current_umo
    if len(parts) > 1:
        raise ValueError("Invalid watch arguments")
    return _resolve_listener(parts[0], current_umo)


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

    async def _auto_name(self, event: AstrMessageEvent, umo: str) -> str:
        if umo == event.unified_msg_origin:
            return self.context.sessions.auto_name(event)
        saved = await self.context.sessions.alias(umo)
        return self.context.sessions.normalize_name(
            saved.auto_name if saved else "",
        )

    async def info(self, event: AstrMessageEvent, target: str = "") -> None:
        """Show identifiers and metadata for the current or selected session."""
        umo = await resolve_target_umo(
            self.context,
            event,
            target,
            action="session.read_target",
        )
        if umo is None:
            return
        if umo != event.unified_msg_origin:
            parsed = self.context.sessions.parse(umo)
            saved = await self.context.sessions.alias(umo)
            empty = await self.context.i18n.t(event, "session.name.empty")
            await reply_i18n(
                self.context,
                event,
                "session.info.target",
                umo=umo,
                auto_name=self.context.sessions.normalize_name(
                    saved.auto_name if saved else "",
                )
                or empty,
                alias=self.context.sessions.normalize_name(
                    saved.user_alias if saved else "",
                )
                or empty,
                platform_id=parsed["platform"],
                message_type=parsed["message_type"],
                session_id=parsed["session_id"],
            )
            return

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

    async def name(
        self,
        event: AstrMessageEvent,
        alias: str,
        target: str = "",
        *,
        clear: bool = False,
    ) -> None:
        """Show, set, or clear the display name for a session."""
        alias = self.context.sessions.normalize_name(alias)
        if clear and alias:
            await reply_i18n(self.context, event, "session.name.usage")
            return
        umo = await resolve_target_umo(
            self.context,
            event,
            target,
            action="session.manage_target",
        )
        if umo is None:
            return
        auto_name = await self._auto_name(event, umo)
        empty = await self.context.i18n.t(event, "session.name.empty")
        if clear:
            await self.context.sessions.set_alias(
                umo=umo,
                creator_sender_id=str(event.get_sender_id() or ""),
                auto_name=auto_name,
                user_alias=None,
            )
            await reply_i18n(
                self.context,
                event,
                "session.name.cleared",
                umo=umo,
            )
            return
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
            if str(exc) == "Direction is occupied by a pair":
                await reply_i18n(self.context, event, "session.watch.occupied")
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
            removed = await self.context.bridges.unwatch(
                event, target_umo, source_umo=source_umo
            )
        except ValueError:
            await reply_i18n(self.context, event, "session.unwatch.usage")
            return
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        await reply_i18n(
            self.context,
            event,
            "session.unwatch.ok" if removed else "session.unwatch.missing",
        )

    async def watches(self, event: AstrMessageEvent, spec: str = "") -> None:
        """List this actor's active watches for a listener session."""
        try:
            source_umo = parse_watches_spec(spec, event.unified_msg_origin)
            items = await self.context.bridges.list(event, source_umo=source_umo)
        except ValueError:
            await reply_i18n(self.context, event, "session.watches.usage")
            return
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        await reply_i18n(
            self.context,
            event,
            "session.watches.body" if items else "session.watches.empty",
            source=source_umo,
            watches="\n".join(
                f"{item.source_umo} -> {item.target_umo} ({item.remaining_seconds}s)"
                for item in items
            ),
        )

    async def connect(self, event: AstrMessageEvent, target: str) -> None:
        """Connect the current session to a target, or show the current link."""
        target = target.strip()
        if not target:
            try:
                item = await self.context.bridges.connection(event)
            except PermissionError:
                await reply_i18n(self.context, event, "session.bridge.denied")
                return
            if item is None:
                await reply_i18n(self.context, event, "session.connect.usage")
                return
            await reply_i18n(
                self.context,
                event,
                "session.connect.status",
                umo=item.target_umo,
            )
            return
        if len(target.split()) != 1:
            await reply_i18n(self.context, event, "session.connect.usage")
            return
        try:
            item = await self.context.bridges.connect(event, target)
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        except LookupError:
            await reply_i18n(self.context, event, "session.connect.failed")
            return
        except ValueError as exc:
            if str(exc) == "Direction is occupied by a pair":
                await reply_i18n(self.context, event, "session.connect.occupied")
                return
            await reply_i18n(self.context, event, "session.connect.failed")
            return
        await reply_i18n(
            self.context,
            event,
            "session.connect.ok",
            umo=item.target_umo,
        )

    async def links(self, event: AstrMessageEvent) -> None:
        """List watch, connect, and pair edges visible to the current actor."""
        try:
            items = await self.context.bridges._manager.list_links(event)
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        if not items:
            await reply_i18n(self.context, event, "session.links.empty")
            return
        lines = []
        for watch, kind in items:
            if watch.expires_at is None:
                ttl = await self.context.i18n.t(event, "session.links.ttl_unbounded")
            else:
                ttl = await self.context.i18n.t(
                    event,
                    "session.links.ttl_seconds",
                    seconds=watch.remaining_seconds,
                )
            if kind == "pair" and watch.pair_id:
                lines.append(
                    f"{watch.rule_id} pair {watch.pair_id} {watch.source_umo} -> {watch.target_umo} ({ttl})"
                )
            else:
                lines.append(
                    f"{watch.rule_id} {kind} {watch.source_umo} -> {watch.target_umo} ({ttl})"
                )
        await reply_i18n(
            self.context,
            event,
            "session.links.body",
            links="\n".join(lines),
        )

    async def unlink(self, event: AstrMessageEvent, spec: str) -> None:
        """Remove a watch or connect by public id."""
        try:
            rule_id = parse_unlink_spec(spec)
            removed = await self.context.bridges._manager.unlink(event, rule_id)
        except ValueError as exc:
            if str(exc) == "Pair edges cannot be unlinked":
                await reply_i18n(self.context, event, "session.unlink.pair")
                return
            await reply_i18n(self.context, event, "session.unlink.usage")
            return
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        await reply_i18n(
            self.context,
            event,
            "session.unlink.ok" if removed else "session.unlink.missing",
        )

    async def pair(self, event: AstrMessageEvent, spec: str) -> None:
        """Create a pair between the current session and a target."""
        try:
            target_umo = parse_pair_spec(spec)
            left, right = await self.context.bridges._manager.pair(event, target_umo)
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        except ValueError as exc:
            if str(exc) == "Invalid pair duration":
                await reply_i18n(self.context, event, "session.pair.ttl_invalid")
                return
            if str(exc) == "Invalid pair arguments":
                await reply_i18n(self.context, event, "session.pair.usage")
                return
            await reply_i18n(self.context, event, "session.pair.failed")
            return
        except LookupError:
            await reply_i18n(self.context, event, "session.pair.failed")
            return
        await reply_i18n(
            self.context,
            event,
            "session.pair.ok",
            umo=left.target_umo,
            pair_id=left.pair_id or "",
            rule_ids=f"{left.rule_id}/{right.rule_id}",
        )

    async def unpair(self, event: AstrMessageEvent, spec: str = "") -> None:
        """Remove both pair edges that share a pair id."""
        try:
            target_umo = parse_unpair_spec(spec)
            removed = await self.context.bridges._manager.unpair(event, target_umo)
        except ValueError as exc:
            if str(exc) == "Multiple pairs require a UMO":
                await reply_i18n(self.context, event, "session.unpair.ambiguous")
                return
            await reply_i18n(self.context, event, "session.unpair.usage")
            return
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        await reply_i18n(
            self.context,
            event,
            "session.unpair.ok" if removed else "session.unpair.missing",
        )

    async def _format_filter_side(self, event: AstrMessageEvent, payload: dict) -> str:
        lines = []
        for key in ("subjects", "roles", "text"):
            values = payload.get(key) or []
            if values:
                lines.append(f"  {key}: {', '.join(values)}")
        if lines:
            return "\n".join(lines)
        return await self.context.i18n.t(event, "session.filter.empty")

    async def filter_rule(self, event: AstrMessageEvent, spec: str) -> None:
        """Show or change match/except filters on one directed edge."""
        try:
            parsed = parse_filter_spec(spec)
            manager = self.context.bridges._manager
            if parsed.action == "show":
                result = await manager.get_filter(event, parsed.rule_id)
            elif parsed.action == "clear":
                result = await manager.clear_filter(event, parsed.rule_id, parsed.side)
            else:
                result = await manager.append_filter(
                    event,
                    parsed.rule_id,
                    parsed.side,
                    parsed.dimension,
                    parsed.value,
                )
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        except ValueError as exc:
            message = str(exc)
            if message == "Invalid filter role":
                await reply_i18n(self.context, event, "session.filter.invalid_role")
                return
            if message == "Invalid filter pattern":
                await reply_i18n(self.context, event, "session.filter.invalid_pattern")
                return
            if message == "Filter limit exceeded":
                await reply_i18n(self.context, event, "session.filter.limit")
                return
            await reply_i18n(self.context, event, "session.filter.usage")
            return
        if result is None:
            await reply_i18n(self.context, event, "session.filter.missing")
            return
        match, except_ = result
        match_text = await self._format_filter_side(event, match)
        except_text = await self._format_filter_side(event, except_)
        key = "session.filter.body"
        if parsed.action == "clear":
            key = "session.filter.cleared"
        elif parsed.action == "append":
            key = "session.filter.updated"
        await reply_i18n(
            self.context,
            event,
            key,
            rule_id=parsed.rule_id,
            match=match_text,
            except_=except_text,
        )

    async def disconnect(self, event: AstrMessageEvent) -> None:
        """Drop the unbounded link owned by the current actor."""
        try:
            removed = await self.context.bridges.disconnect(event)
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        await reply_i18n(
            self.context,
            event,
            "session.disconnect.ok" if removed else "session.disconnect.missing",
        )

    async def send(self, event: AstrMessageEvent, spec: str) -> None:
        """Send the event's rich body; parsed text alone loses attachment order."""
        spec = spec.strip()
        dest = ""
        target_in_header = False
        if spec and _is_umo(spec.split()[0]):
            dest = spec.split()[0]
            target_in_header = True
        try:
            if not dest:
                item = await self.context.bridges.connection(event)
                if item is None:
                    await reply_i18n(self.context, event, "session.send.invalid")
                    return
                dest = item.target_umo
            result = await self.context.bridges.send(
                event, dest, target_in_header=target_in_header
            )
        except PermissionError:
            await reply_i18n(self.context, event, "session.bridge.denied")
            return
        except ValueError, LookupError:
            await reply_i18n(self.context, event, "session.send.invalid")
            return
        await reply_i18n(self.context, event, f"session.send.{result.status}")
