from dataclasses import dataclass


@dataclass(slots=True)
class ScopeResolution:
    scope_id: str
    allowed_chat_ids: list[str]
    sharing_mode: str = "isolated"


class MemoryScopePolicy:
    def __init__(self, sharing_mode: str = "isolated") -> None:
        if sharing_mode not in {"isolated", "group-shared", "global-shared"}:
            raise ValueError(f"Unsupported memory sharing mode: {sharing_mode}")
        self.sharing_mode = sharing_mode

    def resolve(self, chat_id: str) -> ScopeResolution:
        if self.sharing_mode == "isolated":
            return ScopeResolution(
                scope_id=f"isolated:{chat_id}",
                allowed_chat_ids=[chat_id],
            )
        return ScopeResolution(
            scope_id=f"{self.sharing_mode}:{chat_id}",
            allowed_chat_ids=[chat_id],
            sharing_mode=self.sharing_mode,
        )
