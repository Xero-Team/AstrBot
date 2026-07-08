from dataclasses import dataclass, field


@dataclass(slots=True)
class ExtractedMemoryFact:
    fact_text: str
    fact_type: str
    confidence: float = 0.6


@dataclass(slots=True)
class MemoryEpisodeCandidate:
    episode_id: str
    title: str
    summary: str
    participant_ids: list[str] = field(default_factory=list)
    source_message_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MemoryWritebackItem:
    person_id: str
    chat_id: str
    scope_id: str
    user_text: str
    assistant_text: str
    source_message_id: str
    evidence_message_ids: list[str] = field(default_factory=list)
