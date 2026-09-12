"""Declared portable-message capabilities for bundled adapters.

These are conservative protocol defaults.  An adapter may override the class
value when an account, server, or protocol revision changes the effective
capability at runtime.
"""

from __future__ import annotations

from .message_protocol import MessageDeliveryCapabilities

_MEDIA = frozenset({"image", "audio", "video", "file"})


MESSAGE_CAPABILITIES: dict[str, MessageDeliveryCapabilities] = {
    "aiocqhttp": MessageDeliveryCapabilities(
        media=_MEDIA,
        standalone_media=frozenset({"audio", "video", "file"}),
        mixed_parts=True,
        media_caption=True,
        quote=True,
        forward=True,
        mention=True,
        native_namespaces=frozenset({"aiocqhttp"}),
        native_kinds=frozenset({"json", "xml", "face", "node", "nodes", "forward"}),
    ),
    "napcat": MessageDeliveryCapabilities(
        media=_MEDIA,
        standalone_media=frozenset({"audio", "video", "file"}),
        mixed_parts=True,
        media_caption=True,
        quote=True,
        forward=True,
        mention=True,
        native_namespaces=frozenset({"napcat"}),
        native_kinds=frozenset(
            {
                "json",
                "xml",
                "markdown",
                "miniapp",
                "face",
                "mface",
                "node",
                "nodes",
                "forward",
            }
        ),
    ),
    "telegram": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown", "markdown_v2", "entities"}),
        media=_MEDIA,
        media_caption=False,
        album=False,
        quote=True,
        mention=True,
        native_namespaces=frozenset({"telegram"}),
        max_text_length=4096,
        max_parts_per_request=10,
    ),
    "discord": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=frozenset({"image", "audio", "file"}),
        mixed_parts=False,
        quote=True,
        mention=True,
        native_namespaces=frozenset({"discord"}),
        max_text_length=2000,
    ),
    "kook": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        mixed_parts=False,
        mention=True,
        quote=True,
        native_namespaces=frozenset({"kook"}),
        native_kinds=frozenset({"json"}),
    ),
    "lark": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown", "rich_text"}),
        media=_MEDIA,
        quote=False,
        mention=True,
        native_namespaces=frozenset({"lark"}),
        native_kinds=frozenset({"json"}),
    ),
    "line": MessageDeliveryCapabilities(
        media=_MEDIA,
        public_media_urls=True,
        max_text_length=5000,
        mixed_parts=True,
        mention=True,
        native_namespaces=frozenset({"line"}),
        max_parts_per_request=5,
    ),
    "mattermost": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        quote=True,
        native_namespaces=frozenset({"mattermost"}),
    ),
    "misskey": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        quote=False,
        native_namespaces=frozenset({"misskey"}),
    ),
    "satori": MessageDeliveryCapabilities(
        media=_MEDIA,
        mixed_parts=True,
        quote=True,
        forward=True,
        mention=True,
        native_namespaces=frozenset({"satori"}),
    ),
    "slack": MessageDeliveryCapabilities(
        formatting=frozenset({"mrkdwn", "blocks"}),
        media=frozenset({"image", "file"}),
        quote=False,
        mention=True,
        native_namespaces=frozenset({"slack"}),
        # Block Kit section text objects accept at most 3,000 characters.
        # Bridge text is rendered in sections rather than as fallback text.
        max_text_length=3000,
    ),
    "dingtalk": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        quote=False,
        mention=True,
        native_namespaces=frozenset({"dingtalk"}),
    ),
    "qqofficial": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        mixed_parts=False,
        media_caption=True,
        mention=True,
        native_namespaces=frozenset({"qqofficial"}),
    ),
    "qqofficial_webhook": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        native_namespaces=frozenset({"qqofficial"}),
    ),
    "webchat": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown", "html"}),
        media=_MEDIA,
        mixed_parts=False,
        quote=False,
        forward=True,
        mention=True,
        native_namespaces=frozenset({"webchat"}),
    ),
    "wecom": MessageDeliveryCapabilities(
        media=frozenset({"image", "audio", "video", "file"}),
        mention=True,
        native_namespaces=frozenset({"wecom"}),
    ),
    "wecom_ai_bot": MessageDeliveryCapabilities(
        formatting=frozenset({"markdown"}),
        media=_MEDIA,
        native_namespaces=frozenset({"wecom"}),
    ),
    "weixin_oc": MessageDeliveryCapabilities(
        media=frozenset({"image", "audio", "video", "file"}),
        native_namespaces=frozenset({"weixin_oc"}),
    ),
    "weixin_official_account": MessageDeliveryCapabilities(
        proactive=False,
        media=frozenset({"image", "audio"}),
        native_namespaces=frozenset({"weixin_official_account"}),
    ),
}


def get_message_capabilities(platform_name: str) -> MessageDeliveryCapabilities:
    """Return a conservative snapshot for a bundled platform name."""
    profile = {
        "qq_official": "qqofficial",
        "qq_official_webhook": "qqofficial_webhook",
    }.get(platform_name, platform_name)
    return MESSAGE_CAPABILITIES.get(profile, MessageDeliveryCapabilities())


__all__ = ["MESSAGE_CAPABILITIES", "get_message_capabilities"]
