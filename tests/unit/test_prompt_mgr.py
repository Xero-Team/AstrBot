from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.prompt_mgr import PromptManager


@pytest.mark.asyncio
async def test_resolve_selected_prompt_uses_agent_runner_default_prompt():
    agent_runner = {
        "runner_type": "local",
        "config": {"prompt_id": "from-agent-runner"},
    }
    acm = SimpleNamespace(
        default_conf={"agent_runner": agent_runner},
        get_conf=lambda _umo: {"agent_runner": agent_runner},
    )
    preferences = SimpleNamespace(get_async=AsyncMock(return_value={}))
    manager = PromptManager(db_helper=MagicMock(), acm=acm, preferences=preferences)
    manager.runtime_prompts = [{"name": "from-agent-runner"}]

    prompt_id, prompt, force_id, use_webchat = await manager.resolve_selected_prompt(
        umo="webchat:FriendMessage:user",
        conversation_prompt_id=None,
        platform_name="webchat",
    )

    assert prompt_id == "from-agent-runner"
    assert prompt == {"name": "from-agent-runner"}
    assert force_id is None
    assert use_webchat is False
