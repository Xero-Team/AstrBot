"""Locale-aware placeholders and source headers for portable messages.

Delivery localizes synthetic text for the target session. Missing locales
fall back to ``zh-CN``, then the key.
"""

from __future__ import annotations

from .message_type import MessageType

DEFAULT_LOCALE = "zh-CN"
PLACEHOLDER_PREFIX = "astrbot.msg."

LOCALES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "astrbot.msg.header.compact": "[来自 {platform} · {name}]\n",
        "astrbot.msg.header.named": "来自 {name}（{platform}）\n",
        "astrbot.msg.header.named_md": "**来自 {name}（{platform}）**\n",
        "astrbot.msg.header.named_bracket": "[来自 {name}（{platform}）]\n",
        "astrbot.msg.header.napcat": "[来自 NapCat {chat_type} · {name}]\n",
        "astrbot.msg.chat.group": "群聊",
        "astrbot.msg.chat.friend": "私聊",
        "astrbot.msg.chat.other": "其他",
        "astrbot.msg.image": "[图片]",
        "astrbot.msg.audio": "[音频]",
        "astrbot.msg.video": "[视频]",
        "astrbot.msg.file": "[文件]",
        "astrbot.msg.location": "[位置]",
        "astrbot.msg.contact": "[联系人]",
        "astrbot.msg.quote": "[引用]",
        "astrbot.msg.forward_limit": "[转发嵌套上限]",
        "astrbot.msg.content_limit": "[消息内容上限]",
        "astrbot.msg.unknown_sender": "未知",
        "astrbot.msg.unknown_author": "[未知]\n",
        "astrbot.msg.unavailable": "{label}（无法获取）",
        "astrbot.msg.public_media_unavailable": "{label}：公网媒体 URL 不可用",
        "astrbot.msg.watch.expired": "对 {umo} 的监听已结束。",
    },
    "en-US": {
        "astrbot.msg.header.compact": "[From {platform} · {name}]\n",
        "astrbot.msg.header.named": "From {name} ({platform})\n",
        "astrbot.msg.header.named_md": "**From {name} ({platform})**\n",
        "astrbot.msg.header.named_bracket": "[From {name} ({platform})]\n",
        "astrbot.msg.header.napcat": "[From NapCat {chat_type} · {name}]\n",
        "astrbot.msg.chat.group": "group",
        "astrbot.msg.chat.friend": "DM",
        "astrbot.msg.chat.other": "other",
        "astrbot.msg.image": "[Image]",
        "astrbot.msg.audio": "[Audio]",
        "astrbot.msg.video": "[Video]",
        "astrbot.msg.file": "[File]",
        "astrbot.msg.location": "[Location]",
        "astrbot.msg.contact": "[Contact]",
        "astrbot.msg.quote": "[Quote]",
        "astrbot.msg.forward_limit": "[Forward nesting limit]",
        "astrbot.msg.content_limit": "[Message content limit]",
        "astrbot.msg.unknown_sender": "unknown",
        "astrbot.msg.unknown_author": "[unknown]\n",
        "astrbot.msg.unavailable": "{label} (unavailable)",
        "astrbot.msg.public_media_unavailable": "{label}: public media URL unavailable",
        "astrbot.msg.watch.expired": "The watch on {umo} has ended.",
    },
}

_CHAT_TYPE_KEYS: dict[MessageType, str] = {
    MessageType.GROUP_MESSAGE: "astrbot.msg.chat.group",
    MessageType.FRIEND_MESSAGE: "astrbot.msg.chat.friend",
    MessageType.OTHER_MESSAGE: "astrbot.msg.chat.other",
}


def normalize_locale(locale: str | None) -> str:
    """Return a catalog locale, defaulting to Chinese."""
    if locale in LOCALES:
        return locale
    return DEFAULT_LOCALE


def message_key(name: str) -> str:
    """Return a stable placeholder key."""
    return f"{PLACEHOLDER_PREFIX}{name}"


def is_message_key(value: str) -> bool:
    """Return whether ``value`` is a portable-message i18n key."""
    return value.startswith(PLACEHOLDER_PREFIX)


def kind_key(kind: str) -> str:
    """Return the placeholder key for a portable content kind value."""
    return message_key(kind)


def localize(locale: str, key: str, **kwargs: object) -> str:
    """Translate one key for a locale, falling back to zh-CN then the key."""
    resolved = normalize_locale(locale)
    bundle = LOCALES.get(resolved) or LOCALES[DEFAULT_LOCALE]
    template = bundle.get(key)
    if template is None:
        template = LOCALES[DEFAULT_LOCALE].get(key, key)
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except KeyError, IndexError, ValueError:
        return template


def localize_value(locale: str, value: str) -> str:
    """Translate a stored placeholder key, otherwise return the original text."""
    if is_message_key(value):
        return localize(locale, value)
    return value


def localize_kind(locale: str, kind: str) -> str:
    """Return the localized placeholder for a content kind value."""
    return localize(locale, kind_key(kind))


def chat_type_label(locale: str, message_type: MessageType) -> str:
    """Return the localized chat-type label for a source header."""
    return localize(locale, _CHAT_TYPE_KEYS.get(message_type, "astrbot.msg.chat.other"))


__all__ = [
    "DEFAULT_LOCALE",
    "LOCALES",
    "PLACEHOLDER_PREFIX",
    "chat_type_label",
    "is_message_key",
    "kind_key",
    "localize",
    "localize_kind",
    "localize_value",
    "message_key",
    "normalize_locale",
]
