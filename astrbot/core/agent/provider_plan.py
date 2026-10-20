"""One normalized provider candidate plan for an agent run."""

from dataclasses import dataclass

from .chat_model import ChatModel


def _provider_id(provider: ChatModel) -> str:
    return str(provider.provider_config.get("id", ""))


@dataclass(frozen=True, slots=True)
class ProviderPlan:
    """The primary chat model and its ordered fallbacks.

    Construction is the only place candidate de-duplication happens, so the
    request builder and the runner cannot disagree about the fallback order.
    """

    primary: ChatModel
    fallbacks: tuple[ChatModel, ...] = ()

    @classmethod
    def from_candidates(
        cls,
        primary: ChatModel,
        fallbacks: list[ChatModel] | tuple[ChatModel, ...] | None = None,
    ) -> ProviderPlan:
        seen: set[str] = set()
        primary_id = _provider_id(primary)
        if primary_id:
            seen.add(primary_id)

        unique: list[ChatModel] = []
        for candidate in fallbacks or ():
            if candidate is primary:
                continue
            candidate_id = _provider_id(candidate)
            if candidate_id and candidate_id in seen:
                continue
            unique.append(candidate)
            if candidate_id:
                seen.add(candidate_id)
        return cls(primary=primary, fallbacks=tuple(unique))

    @property
    def candidates(self) -> tuple[ChatModel, ...]:
        """Return the primary followed by the ordered fallbacks."""
        return (self.primary, *self.fallbacks)

    def with_primary(self, primary: ChatModel) -> ProviderPlan:
        """Return a plan whose primary is ``primary``.

        Re-normalizing removes a fallback with the same non-empty id as the
        promoted provider, not just the same object, so a candidate is never
        attempted twice.
        """
        if primary is self.primary:
            return self
        return type(self).from_candidates(primary, self.fallbacks)
