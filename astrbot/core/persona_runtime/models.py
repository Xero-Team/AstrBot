from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class PersonaRuntimeSignal:
    persona_id: str
    umo: str
    user_text: str
    assistant_text: str
    sender_id: str
    conversation_id: str | None = None
    occurred_at: datetime | None = None
    mentioned: bool = False


@dataclass(slots=True)
class PersonaRuntimeContext:
    persona_id: str
    umo: str
    agent_state: str
    talk_frequency_adjust: float
    consecutive_idle_count: int
    cooldown_until: datetime | None
    last_interaction_at: datetime | None
    last_proactive_at: datetime | None
    extra_state: dict = field(default_factory=dict)
