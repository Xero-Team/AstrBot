from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.contracts.telegram import TelegramCallbackEvent

from . import HandlerFilter


class TelegramCallbackFilter(HandlerFilter):
    """Match a normalized Telegram callback value."""

    def __init__(self, value: str | None = None) -> None:
        self.value = value

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        callback = event.get_extra("telegram_callback")
        if not isinstance(callback, TelegramCallbackEvent):
            return False
        return self.value is None or callback.data == self.value


__all__ = ["TelegramCallbackFilter"]
