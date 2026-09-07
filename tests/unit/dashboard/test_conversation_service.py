from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.dashboard.services.conversation_service import ConversationService


@pytest.mark.asyncio
async def test_filter_options_include_builtin_webchat_when_history_has_it():
    service = ConversationService(
        db_helper=SimpleNamespace(
            get_conversation_platform_ids=AsyncMock(return_value=["webchat", "qq-bot"])
        ),
        conversation_manager=SimpleNamespace(),
        config={"platform": [{"id": "qq-bot", "type": "aiocqhttp"}]},
    )

    options = await service.get_filter_options()

    assert options["bots"] == [
        {"id": "qq-bot", "type": "aiocqhttp"},
        {"id": "webchat", "type": "webchat"},
    ]


@pytest.mark.asyncio
async def test_filter_options_keep_configured_webchat_id():
    service = ConversationService(
        db_helper=SimpleNamespace(
            get_conversation_platform_ids=AsyncMock(return_value=["webchat-main"])
        ),
        conversation_manager=SimpleNamespace(),
        config={"platform": [{"id": "webchat-main", "type": "webchat"}]},
    )

    options = await service.get_filter_options()

    assert options["bots"] == [{"id": "webchat-main", "type": "webchat"}]
