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


@pytest.mark.asyncio
async def test_webchat_titles_are_batched_and_scoped_to_webchat():
    lookup = AsyncMock(
        return_value=[SimpleNamespace(session_id="session-a", display_name="Alice")]
    )
    service = ConversationService(
        db_helper=SimpleNamespace(get_platform_sessions_by_ids=lookup),
        conversation_manager=SimpleNamespace(),
        config={},
    )
    conversations = [
        SimpleNamespace(
            platform_id="webchat", user_id="webchat:FriendMessage:webchat!u!session-a"
        ),
        SimpleNamespace(platform_id="qq", user_id="qq:FriendMessage:session-a"),
    ]

    titles = await service._get_webchat_titles(conversations)

    assert titles == {"webchat:FriendMessage:webchat!u!session-a": "Alice"}
    lookup.assert_awaited_once_with(["session-a"], platform_id="webchat")


@pytest.mark.asyncio
async def test_export_continues_after_conversation_lookup_failure():
    conversation = SimpleNamespace(
        cid="second",
        user_id="qq:FriendMessage:bob",
        platform_id="qq",
        title="Bob chat",
        persona_id=None,
        created_at="2026-09-10T00:00:00+00:00",
        updated_at="2026-09-10T00:00:00+00:00",
        history='[{"role": "user", "content": "hello"}]',
    )
    get_conversation = AsyncMock(
        side_effect=[RuntimeError("temporary database failure"), conversation]
    )
    service = ConversationService(
        db_helper=SimpleNamespace(),
        conversation_manager=SimpleNamespace(get_conversation=get_conversation),
        config={},
    )

    export = await service.export_conversations(
        {
            "conversations": [
                {"user_id": "qq:FriendMessage:alice", "cid": "first"},
                {"user_id": "qq:FriendMessage:bob", "cid": "second"},
            ]
        }
    )

    assert export.file_obj.read().decode("utf-8") == (
        '{"cid": "second", "user_id": "qq:FriendMessage:bob", '
        '"platform_id": "qq", "title": "Bob chat", "persona_id": null, '
        '"created_at": "2026-09-10T00:00:00+00:00", '
        '"updated_at": "2026-09-10T00:00:00+00:00", '
        '"content": [{"role": "user", "content": "hello"}]}'
    )
    assert get_conversation.await_count == 2
