from datetime import UTC, datetime, timedelta

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PersonaSessionState

from .models import PersonaRuntimeSignal


class PersonaRuntimeStateStore:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def get_or_create(
        self,
        persona_id: str,
        umo: str,
    ) -> PersonaSessionState:
        existing = await self.db.get_persona_session_state(persona_id, umo)
        if existing:
            return existing
        return await self.db.upsert_persona_session_state(
            persona_id=persona_id,
            umo=umo,
            last_interaction_at=datetime.now(UTC),
            extra_state={"proactive_enabled": False},
        )

    async def apply_signal(self, signal: PersonaRuntimeSignal) -> PersonaSessionState:
        now = signal.occurred_at or datetime.now(UTC)
        existing = await self.get_or_create(signal.persona_id, signal.umo)
        extra_state = dict(existing.extra_state or {})
        if signal.mentioned:
            extra_state["last_mention_at"] = now.isoformat()

        user_text = signal.user_text.strip()
        assistant_text = signal.assistant_text.strip()
        talk_frequency_adjust = float(existing.talk_frequency_adjust or 1.0)
        if signal.mentioned or user_text.endswith(("?", "？")):
            talk_frequency_adjust = min(talk_frequency_adjust + 0.1, 2.0)
            agent_state = "running"
            consecutive_idle_count = 0
        elif assistant_text:
            talk_frequency_adjust = max(talk_frequency_adjust * 0.98, 0.5)
            agent_state = "running"
            consecutive_idle_count = 0
        else:
            talk_frequency_adjust = max(talk_frequency_adjust * 0.95, 0.5)
            agent_state = "wait"
            consecutive_idle_count = existing.consecutive_idle_count + 1

        cooldown_until = existing.cooldown_until
        if signal.mentioned:
            cooldown_until = now + timedelta(seconds=30)

        return await self.db.upsert_persona_session_state(
            persona_id=signal.persona_id,
            umo=signal.umo,
            agent_state=agent_state,
            talk_frequency_adjust=talk_frequency_adjust,
            consecutive_idle_count=consecutive_idle_count,
            cooldown_until=cooldown_until,
            last_interaction_at=now,
            last_proactive_at=existing.last_proactive_at,
            extra_state=extra_state,
        )
