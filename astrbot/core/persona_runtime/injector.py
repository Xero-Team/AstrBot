from datetime import UTC, datetime

from astrbot.core.agent.message import TextPart
from astrbot.core.db.po import PersonaSessionState
from astrbot.core.provider.entities import ProviderRequest


class PersonaRuntimeInjector:
    def build_context_text(self, state: PersonaSessionState) -> str:
        cooldown = "none"
        if state.cooldown_until:
            cooldown = state.cooldown_until.astimezone(UTC).isoformat()
        last_interaction = (
            state.last_interaction_at.astimezone(UTC).isoformat()
            if state.last_interaction_at
            else "unknown"
        )
        return (
            "<persona_runtime_context>\n"
            f"persona_id: {state.persona_id}\n"
            f"chat_stream: {state.umo}\n"
            f"agent_state: {state.agent_state}\n"
            f"talk_frequency_adjust: {state.talk_frequency_adjust:.2f}\n"
            f"consecutive_idle_count: {state.consecutive_idle_count}\n"
            f"cooldown_until: {cooldown}\n"
            f"last_interaction_at: {last_interaction}\n"
            "Use this as transient behavior context for this turn only. "
            "Do not quote it verbatim.\n"
            "</persona_runtime_context>"
        )

    def inject(self, req: ProviderRequest, state: PersonaSessionState) -> None:
        req.extra_user_content_parts.append(
            TextPart(text=self.build_context_text(state)).mark_as_temp()
        )


def is_in_cooldown(state: PersonaSessionState, now: datetime | None = None) -> bool:
    if not state.cooldown_until:
        return False
    return state.cooldown_until > (now or datetime.now(UTC))
