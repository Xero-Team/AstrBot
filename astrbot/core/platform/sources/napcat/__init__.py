"""NapCat platform support."""

from .exceptions import NapCatApiError, NapCatError, NapCatTransportError
from .forward_ws_client import NapCatForwardWebSocketClient
from .message_event import NapCatMessageEvent
from .napcat_platform_adapter import NapCatPlatformAdapter
from .types import (
    NapCatFetchedMessage,
    NapCatLoginInfo,
    NapCatSendMessageResult,
    NapCatStatus,
    NapCatVersionInfo,
)

__all__ = [
    "NapCatApiError",
    "NapCatError",
    "NapCatFetchedMessage",
    "NapCatForwardWebSocketClient",
    "NapCatLoginInfo",
    "NapCatMessageEvent",
    "NapCatPlatformAdapter",
    "NapCatSendMessageResult",
    "NapCatStatus",
    "NapCatTransportError",
    "NapCatVersionInfo",
]
