import json

import pytest

from astrbot.core.conversation_mgr import (
    WORK_LOOP_SCOPE,
    ConversationManager,
    load_sanitized_history,
)
from astrbot.core.utils.shared_preferences import SharedPreferences


@pytest.mark.asyncio
async def test_conversation_manager_creates_loads_and_isolates_sessions(
    temp_db, tmp_path
):
    await temp_db.initialize()
    preferences = SharedPreferences(temp_db, tmp_path / "preferences.json")
    await preferences.initialize()
    manager = ConversationManager(temp_db, preferences)
    try:
        umo_a = "webchat:FriendMessage:alice"
        umo_b = "webchat:FriendMessage:bob"
        cid_a = await manager.new_conversation(umo_a, title="Alice chat")
        cid_b = await manager.new_conversation(umo_b, title="Bob chat")
        dirty_history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                    },
                ],
            }
        ]
        await manager.update_conversation(umo_a, cid_a, history=dirty_history)

        conv_a = await manager.get_conversation(umo_a, cid_a)
        conv_b = await manager.get_conversation(umo_b, cid_b)
        assert conv_a is not None
        assert conv_b is not None
        assert conv_a.title == "Alice chat"
        assert conv_b.title == "Bob chat"
        assert await manager.get_curr_conversation_id(umo_a) == cid_a
        assert await manager.get_curr_conversation_id(umo_b) == cid_b
        sanitized = load_sanitized_history(conv_a.history)
        assert sanitized[0]["content"][0]["text"] == "hello"
        assert "base64" not in json.dumps(sanitized)

        deleted: list[str] = []

        async def on_deleted(umo: str) -> None:
            deleted.append(umo)

        manager.register_on_session_deleted(on_deleted)
        await manager.delete_conversations_by_user_id(umo_a)

        assert deleted == [umo_a]
        assert await manager.get_conversation(umo_a, cid_a) is None
        remaining = await manager.get_conversation(umo_b, cid_b)
        assert remaining is not None
        assert remaining.title == "Bob chat"
    finally:
        await preferences.terminate()


@pytest.mark.asyncio
async def test_delete_current_conversation_loads_persisted_selection(temp_db, tmp_path):
    await temp_db.initialize()
    preferences = SharedPreferences(temp_db, tmp_path / "preferences.json")
    await preferences.initialize()
    manager = ConversationManager(temp_db, preferences)
    try:
        umo = "webchat:FriendMessage:alice"
        cid = await manager.new_conversation(umo, title="Alice chat")
        manager.session_conversations.clear()

        await manager.delete_conversation(umo)

        assert await manager.get_conversation(umo, cid) is None
        assert await preferences.session_get(umo, "sel_conv_id", None) is None
    finally:
        await preferences.terminate()


@pytest.mark.asyncio
async def test_work_loop_scope_keeps_a_separate_conversation_per_session(
    temp_db, tmp_path
):
    """The work loop writes its own conversation next to the session's chat."""
    await temp_db.initialize()
    preferences = SharedPreferences(temp_db, tmp_path / "preferences.json")
    await preferences.initialize()
    manager = ConversationManager(temp_db, preferences)
    try:
        umo = "webchat:FriendMessage:alice"
        chat_cid = await manager.new_conversation(umo, title="Alice chat")
        work_cid = await manager.new_conversation(
            umo,
            title="Work",
            scope=WORK_LOOP_SCOPE,
        )

        assert work_cid != chat_cid
        # The work loop does not take over the session's current chat.
        assert await manager.get_curr_conversation_id(umo) == chat_cid
        assert await manager.get_curr_conversation_id(umo, WORK_LOOP_SCOPE) == work_cid

        await manager.update_conversation(
            umo, chat_cid, history=[{"role": "user", "content": "chat turn"}]
        )
        await manager.update_conversation(
            umo, work_cid, history=[{"role": "user", "content": "work turn"}]
        )

        chat = await manager.get_conversation(umo, chat_cid)
        work = await manager.get_conversation(umo, work_cid)
        assert load_sanitized_history(chat.history) == [
            {"role": "user", "content": "chat turn"}
        ]
        assert load_sanitized_history(work.history) == [
            {"role": "user", "content": "work turn"}
        ]

        # Both conversations belong to the one session.
        listed = {
            conversation.cid for conversation in await manager.get_conversations(umo)
        }
        assert listed == {chat_cid, work_cid}

        # The selection survives a restart: a fresh cache reads it back.
        manager.session_conversations.clear()
        assert await manager.get_curr_conversation_id(umo, WORK_LOOP_SCOPE) == work_cid
        assert await manager.get_curr_conversation_id(umo) == chat_cid

        await manager.delete_conversations_by_user_id(umo)
        assert await manager.get_curr_conversation_id(umo, WORK_LOOP_SCOPE) is None
        assert await manager.get_curr_conversation_id(umo) is None
    finally:
        await preferences.terminate()
