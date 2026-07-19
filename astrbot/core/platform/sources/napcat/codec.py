"""Pure OneBot/NapCat message formatting helpers."""


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).strip()


def decode_cq_text(value: str) -> str:
    """Decode OneBot CQ escaping in a text segment."""
    return (
        value.replace("&#91;", "[")
        .replace("&#93;", "]")
        .replace("&#44;", ",")
        .replace("&amp;", "&")
    )


def coerce_numeric_value(value: object) -> object:
    """Convert a decimal OneBot payload value to an integer when possible."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def coerce_bool_value(value: object) -> object:
    """Convert a textual OneBot boolean payload value when possible."""
    if isinstance(value, str):
        match value.strip().lower():
            case "true":
                return True
            case "false":
                return False
    return value


def sanitize_segment_type(value: object) -> str:
    """Return a bounded label safe for logs and user-facing placeholders."""
    text = str(value or "unknown").strip()[:64]
    sanitized = "".join(
        char if char.isalnum() or char in "_-" else "_" for char in text
    )
    return sanitized or "unknown"


def build_notice_message(event: object) -> str:
    """Format a OneBot notice event without depending on adapter state."""
    notice_type = _stringify(getattr(event, "notice_type", None))
    sub_type = _stringify(getattr(event, "sub_type", None))
    prefix = f"[notice:{notice_type or 'unknown'}"
    parts = [f"{prefix}:{sub_type}]" if sub_type else f"{prefix}]"]

    labels = (
        ("user", "user_id", True),
        ("peer", "peer_id", True),
        ("target", "target_id", True),
        ("operator", "operator_id", True),
        ("operator_nick", "operator_nick", False),
        ("message", "message_id", False),
        ("group", "group_id", True),
        ("honor", "honor_type", False),
        ("code", "code", False),
        ("count", "count", False),
        ("times", "times", False),
        ("event_type", "event_type", False),
        ("status", "status_text", False),
        ("busi", "busi_id", False),
        ("content", "content", False),
        ("name", "name_new", False),
        ("title", "title", False),
        ("tag", "tag", False),
    )
    values = {field: _stringify(getattr(event, field, None)) for _, field, _ in labels}
    for label, field, reject_zero in labels:
        value = values[field]
        if value and (not reject_zero or value != "0"):
            parts.append(f"{label} {value}")
    if (duration := getattr(event, "duration", None)) is not None:
        parts.append(f"duration {duration}s")
    if isinstance(likes := getattr(event, "likes", None), list):
        like_parts: list[str] = []
        for like in likes:
            emoji_id = _stringify(getattr(like, "emoji_id", None))
            count = _stringify(getattr(like, "count", None))
            if emoji_id:
                like_parts.append(f"{emoji_id}={count or '0'}")
        parts.append(f"likes {','.join(like_parts) if like_parts else len(likes)}")
    if (is_add := getattr(event, "is_add", None)) is not None:
        parts.append(f"action {'add' if bool(is_add) else 'remove'}")
    event_message = _stringify(getattr(event, "message", None))
    if event_message and event_message != values["message_id"]:
        parts.append(f"message {event_message}")
    if file_info := getattr(event, "file", None):
        if file_name := _stringify(getattr(file_info, "name", None)):
            parts.append(f"file {file_name}")
        if file_id := _stringify(getattr(file_info, "id", None)):
            parts.append(f"file_id {file_id}")
        if file_size := _stringify(getattr(file_info, "size", None)):
            parts.append(f"file_size {file_size}")
        if file_busid := _stringify(getattr(file_info, "busid", None)):
            parts.append(f"busid {file_busid}")
    if card_old := _stringify(getattr(event, "card_old", None)):
        parts.append(f"old_card {card_old}")
    if card_new := _stringify(getattr(event, "card_new", None)):
        parts.append(f"new_card {card_new}")
    return " ".join(parts)


def build_request_message(event: object) -> str:
    """Format a OneBot request event without depending on adapter state."""
    request_type = _stringify(getattr(event, "request_type", None))
    sub_type = _stringify(getattr(event, "sub_type", None))
    prefix = f"[request:{request_type or 'unknown'}"
    parts = [f"{prefix}:{sub_type}]" if sub_type else f"{prefix}]"]
    for label, field in (
        ("user", "user_id"),
        ("group", "group_id"),
        ("comment", "comment"),
        ("flag", "flag"),
    ):
        if value := _stringify(getattr(event, field, None)):
            parts.append(f"{label} {value}")
    return " ".join(parts)
