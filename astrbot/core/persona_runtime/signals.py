from astrbot.core.platform.astr_message_event import AstrMessageEvent


def event_mentions_bot(event: AstrMessageEvent) -> bool:
    message = getattr(getattr(event, "message_obj", None), "message", []) or []
    self_id = str(getattr(getattr(event, "message_obj", None), "self_id", "") or "")
    for comp in message:
        qq = getattr(comp, "qq", None)
        if qq is not None and str(qq) == self_id:
            return True
    return False
