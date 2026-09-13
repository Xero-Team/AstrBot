from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


async def resolve_target_umo(
    context,
    event: AstrMessageEvent,
    target: str,
    *,
    action: str,
) -> str | None:
    """Return the current or explicitly selected session UMO."""
    target = target.strip()
    if not target:
        return event.unified_msg_origin
    if len(target.split()) != 1:
        await reply_i18n(context, event, "bot.target.usage")
        return None
    if target.lower() == "this":
        return event.unified_msg_origin
    try:
        decision = await context.authz.authorize_target_session(
            event,
            action=action,
            umo=target,
        )
    except PermissionError, ValueError:
        await reply_i18n(context, event, "bot.target.denied")
        return None
    if not decision.allowed:
        await reply_i18n(context, event, "bot.target.denied")
        return None
    return target
