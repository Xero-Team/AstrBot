from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.db.po import Prompt
from astrbot.core.prompt_mgr import DEFAULT_PROMPT_SPEC, PromptManager


def _prompt(prompt_id: str, text: str) -> Prompt:
    return Prompt(prompt_id=prompt_id, system_prompt=text)


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


@pytest.mark.asyncio
async def test_initialize_seeds_editable_default_prompt_when_absent():
    db = MagicMock()
    db.get_prompts = AsyncMock(return_value=[_prompt("custom", "Custom")])
    db.insert_prompt = AsyncMock(return_value=_prompt("default", "Default"))
    manager = PromptManager(
        db_helper=db,
        acm=SimpleNamespace(default_conf={}),
        preferences=SimpleNamespace(),
    )

    await manager.initialize()

    db.insert_prompt.assert_awaited_once_with(
        prompt_id="default",
        system_prompt=DEFAULT_PROMPT_SPEC["prompt"],
    )
    assert manager.get_runtime_prompt_by_id("default")["prompt"] == "Default"


@pytest.mark.asyncio
async def test_system_default_prompt_cannot_be_created_or_deleted():
    manager = PromptManager(
        db_helper=MagicMock(),
        acm=SimpleNamespace(default_conf={}),
        preferences=SimpleNamespace(),
    )

    with pytest.raises(ValueError, match="cannot be deleted"):
        await manager.delete_prompt("default")
    with pytest.raises(ValueError, match="reserved"):
        await manager.create_prompt("default", "Replacement")


@pytest.mark.asyncio
async def test_webchat_implicit_default_keeps_chatui_prompt() -> None:
    preferences = SimpleNamespace(get_async=AsyncMock(return_value={}))
    manager = PromptManager(
        db_helper=MagicMock(),
        acm=SimpleNamespace(
            default_conf={"agent_runner": {}},
            get_conf=lambda _umo: {"agent_runner": {}},
        ),
        preferences=preferences,
    )
    manager.runtime_prompts = [{"name": "default", "prompt": "Editable system default"}]

    prompt_id, prompt, _, use_webchat = await manager.resolve_selected_prompt(
        umo="webchat:FriendMessage:user",
        conversation_prompt_id=None,
        platform_name="webchat",
    )

    assert prompt_id == "_chatui_default_"
    assert prompt is None
    assert use_webchat is True
