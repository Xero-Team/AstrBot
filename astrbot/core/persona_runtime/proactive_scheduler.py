from dataclasses import dataclass
from datetime import UTC, datetime

from astrbot.core.db.po import PersonaSessionState

from .injector import is_in_cooldown


@dataclass(slots=True)
class ProactiveDecision:
    should_enqueue: bool
    reason: str


class ProactiveScheduler:
    """Pure decision layer; it never sends messages by itself."""

    def evaluate(
        self,
        state: PersonaSessionState,
        *,
        unread_count: int = 0,
        mentioned: bool = False,
        now: datetime | None = None,
    ) -> ProactiveDecision:
        current = now or datetime.now(UTC)
        if not (state.extra_state or {}).get("proactive_enabled", False):
            return ProactiveDecision(False, "proactive_disabled")
        if is_in_cooldown(state, current):
            return ProactiveDecision(False, "cooldown")
        if state.agent_state == "stop":
            return ProactiveDecision(False, "agent_stopped")
        if mentioned:
            return ProactiveDecision(True, "mentioned")
        if unread_count >= 3 and state.talk_frequency_adjust >= 1.0:
            return ProactiveDecision(True, "unread_threshold")
        return ProactiveDecision(False, "insufficient_signal")
