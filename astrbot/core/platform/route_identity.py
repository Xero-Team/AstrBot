from dataclasses import dataclass

from astrbot.core.platform.message_type import MessageType


@dataclass(frozen=True, slots=True)
class PlatformRouteIdentity:
    """Immutable transport routing identity for replying on a platform."""

    platform_id: str
    message_type: MessageType
    target_id: str
    origin: str = ""

    def as_origin(self) -> str:
        if self.origin:
            return self.origin
        return f"{self.platform_id}:{self.message_type.value}:{self.target_id}"
