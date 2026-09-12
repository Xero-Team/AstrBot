from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.db.po import PersonaSessionState
from astrbot.core.persona_runtime import PersonaRuntimeManager
from astrbot.core.persona_runtime.injector import PersonaRuntimeInjector


def _state(**overrides) -> PersonaSessionState:
    now = datetime.now(UTC)
    values = {
        "persona_id": "persona-a",
        "umo": "webchat:FriendMessage:u1",
        "agent_state": "running",
        "talk_frequency_adjust": 1.0,
        "consecutive_idle_count": 0,
        "cooldown_until": None,
        "last_interaction_at": now,
        "extra_state": {},
    }
    values.update(overrides)
    return PersonaSessionState(**values)


def test_injector_adds_transient_runtime_context():
    req = ProviderRequest(prompt="hi")
    PersonaRuntimeInjector().inject(req, _state())
    assert req.extra_user_content_parts
    assert req.extra_user_content_parts[0].is_temp is True
    assert "persona_runtime_context" in req.extra_user_content_parts[0].text
