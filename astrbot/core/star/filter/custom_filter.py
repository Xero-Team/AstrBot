from abc import ABCMeta, abstractmethod

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class CustomFilterMeta(ABCMeta):
    def __and__(self, other):
        if not (isinstance(other, type) and issubclass(other, CustomFilter)):
            return NotImplemented
        return CustomFilterAnd(self(), other())

    def __or__(self, other):
        if not (isinstance(other, type) and issubclass(other, CustomFilter)):
            return NotImplemented
        return CustomFilterOr(self(), other())


class CustomFilter(HandlerFilter, metaclass=CustomFilterMeta):
    def __init__(self, raise_error: bool = True, **kwargs) -> None:
        self.raise_error = raise_error

    @abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """一个用于重写的自定义Filter"""
        ...

    def __or__(self, other):
        return CustomFilterOr(self, other)

    def __and__(self, other):
        return CustomFilterAnd(self, other)


class CustomFilterOr(CustomFilter):
    def __init__(self, filter1: CustomFilter, filter2: CustomFilter) -> None:
        super().__init__()
        if not isinstance(filter1, (CustomFilter, CustomFilterAnd, CustomFilterOr)):
            raise ValueError(
                "CustomFilter class can only operate with other CustomFilter.",
            )
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return self.filter1.filter(event, cfg) or self.filter2.filter(event, cfg)


class CustomFilterAnd(CustomFilter):
    def __init__(self, filter1: CustomFilter, filter2: CustomFilter) -> None:
        super().__init__()
        if not isinstance(filter1, (CustomFilter, CustomFilterAnd, CustomFilterOr)):
            raise ValueError(
                "CustomFilter lass can only operate with other CustomFilter.",
            )
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return self.filter1.filter(event, cfg) and self.filter2.filter(event, cfg)
