"""Platform public names with lazy imports.

Keeping this package initializer light is important for source-independent
plugin contracts such as :mod:`astrbot.api.onebot`.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.astrbot_message import (
        AstrBotMessage,
        Group,
        MessageMember,
    )
    from astrbot.core.platform.message_delivery import (
        batch_to_message_chain,
        plan_message_delivery,
    )
    from astrbot.core.platform.message_projection import envelope_from_event
    from astrbot.core.platform.message_protocol import (
        ContentKind,
        DeliveryBatch,
        MediaReference,
        MessageDeliveryCapabilities,
        MessageEnvelope,
        NativeContent,
        PortablePart,
        QuoteReference,
        SenderSnapshot,
        plan_delivery,
    )
    from astrbot.core.platform.message_renderers import render_source_header
    from astrbot.core.platform.message_session import MessageSession
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.platform.platform import Platform
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.platform.route_identity import PlatformRouteIdentity
    from astrbot.core.platform.send_result import PlatformSendResult
    from astrbot.core.platform.session_bridge import (
        DEFAULT_WATCH_TTL_SECONDS,
        MAX_WATCH_TTL_SECONDS,
        MIN_WATCH_TTL_SECONDS,
        SessionBridgeManager,
        SessionWatch,
    )

_EXPORTS = {
    "AstrBotMessage": ("astrbot.core.platform.astrbot_message", "AstrBotMessage"),
    "Group": ("astrbot.core.platform.astrbot_message", "Group"),
    "MessageMember": ("astrbot.core.platform.astrbot_message", "MessageMember"),
    "MessageType": ("astrbot.core.platform.message_type", "MessageType"),
    "AstrMessageEvent": (
        "astrbot.core.platform.astr_message_event",
        "AstrMessageEvent",
    ),
    "Platform": ("astrbot.core.platform.platform", "Platform"),
    "PlatformMetadata": ("astrbot.core.platform.platform_metadata", "PlatformMetadata"),
    "PlatformRouteIdentity": (
        "astrbot.core.platform.route_identity",
        "PlatformRouteIdentity",
    ),
    "PlatformSendResult": ("astrbot.core.platform.send_result", "PlatformSendResult"),
    "MessageSession": ("astrbot.core.platform.message_session", "MessageSession"),
}

_PROTOCOL_EXPORTS = {
    "ContentKind": ("astrbot.core.platform.message_protocol", "ContentKind"),
    "DeliveryBatch": ("astrbot.core.platform.message_protocol", "DeliveryBatch"),
    "MediaReference": ("astrbot.core.platform.message_protocol", "MediaReference"),
    "MessageDeliveryCapabilities": (
        "astrbot.core.platform.message_protocol",
        "MessageDeliveryCapabilities",
    ),
    "MessageEnvelope": (
        "astrbot.core.platform.message_protocol",
        "MessageEnvelope",
    ),
    "NativeContent": ("astrbot.core.platform.message_protocol", "NativeContent"),
    "PortablePart": ("astrbot.core.platform.message_protocol", "PortablePart"),
    "QuoteReference": ("astrbot.core.platform.message_protocol", "QuoteReference"),
    "SenderSnapshot": ("astrbot.core.platform.message_protocol", "SenderSnapshot"),
    "plan_delivery": ("astrbot.core.platform.message_protocol", "plan_delivery"),
    "envelope_from_event": (
        "astrbot.core.platform.message_projection",
        "envelope_from_event",
    ),
    "batch_to_message_chain": (
        "astrbot.core.platform.message_delivery",
        "batch_to_message_chain",
    ),
    "plan_message_delivery": (
        "astrbot.core.platform.message_delivery",
        "plan_message_delivery",
    ),
    "render_source_header": (
        "astrbot.core.platform.message_renderers",
        "render_source_header",
    ),
    "SessionBridgeManager": (
        "astrbot.core.platform.session_bridge",
        "SessionBridgeManager",
    ),
    "SessionWatch": ("astrbot.core.platform.session_bridge", "SessionWatch"),
    "DEFAULT_WATCH_TTL_SECONDS": (
        "astrbot.core.platform.session_bridge",
        "DEFAULT_WATCH_TTL_SECONDS",
    ),
    "MAX_WATCH_TTL_SECONDS": (
        "astrbot.core.platform.session_bridge",
        "MAX_WATCH_TTL_SECONDS",
    ),
    "MIN_WATCH_TTL_SECONDS": (
        "astrbot.core.platform.session_bridge",
        "MIN_WATCH_TTL_SECONDS",
    ),
}
_EXPORTS.update(_PROTOCOL_EXPORTS)


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module = import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value


__all__ = [
    "AstrBotMessage",
    "AstrMessageEvent",
    "Group",
    "MessageMember",
    "MessageType",
    "Platform",
    "PlatformMetadata",
    "PlatformRouteIdentity",
    "PlatformSendResult",
    "MessageSession",
    "ContentKind",
    "DeliveryBatch",
    "MediaReference",
    "MessageDeliveryCapabilities",
    "MessageEnvelope",
    "NativeContent",
    "PortablePart",
    "QuoteReference",
    "SenderSnapshot",
    "plan_delivery",
    "envelope_from_event",
    "batch_to_message_chain",
    "plan_message_delivery",
    "render_source_header",
    "SessionBridgeManager",
    "SessionWatch",
    "DEFAULT_WATCH_TTL_SECONDS",
    "MAX_WATCH_TTL_SECONDS",
    "MIN_WATCH_TTL_SECONDS",
]
