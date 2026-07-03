import abc


class ContentSafetyStrategy(abc.ABC):
    @abc.abstractmethod
    async def check(self, content: str) -> tuple[bool, str]:
        raise NotImplementedError
