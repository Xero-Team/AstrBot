from datetime import UTC, datetime

import pytest

from astrbot.core.db.po.sessions import PlatformSession
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError
from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiServiceError,
)


def _open_api_service(db: SQLiteDatabase) -> OpenApiService:
    """Build the service with only the database dependency used by these tests."""
    service = OpenApiService.__new__(OpenApiService)
    service.db = db
    return service


def _chat_service(db: SQLiteDatabase) -> ChatService:
    """Build a minimal ChatService for session-detail coverage."""
    service = ChatService.__new__(ChatService)
    service.db = db
    service.platform_history_mgr = PlatformMessageHistoryManager(db)
    service.chat_run_states = {}
    service.get_active_chat_runs = lambda *_: []
    service._is_session_running = lambda *_: False
    return service


async def _seed_owner_sessions(db: SQLiteDatabase, count: int) -> None:
    """Insert equally timestamped sessions in one transaction."""
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    async with db.get_db() as session:
        async with session.begin():
            session.add_all(
                [
                    PlatformSession(
                        creator="owner",
                        platform_id="webchat",
                        session_id=f"session-{index:03}",
                        display_name=f"Session {index}",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    for index in range(count)
                ]
            )


@pytest.mark.asyncio
async def test_get_chat_sessions_paginates_scopes_and_clamps(temp_db: SQLiteDatabase):
    """Paginate deterministically while enforcing owner and project scope."""
    await _seed_owner_sessions(temp_db, 125)
    await temp_db.create_platform_session(
        creator="other", platform_id="webchat", session_id="foreign"
    )
    project = await temp_db.create_chatui_project(creator="owner", title="Project")
    await temp_db.create_platform_session(
        creator="owner", platform_id="webchat", session_id="project-session"
    )
    await temp_db.add_session_to_project("project-session", project.project_id)

    service = _open_api_service(temp_db)
    ids: list[str] = []
    for page in range(1, 6):
        payload = await service.get_chat_sessions(
            username="owner",
            page=page,
            page_size=30,
            platform_id="webchat",
        )
        assert payload["total"] == 125
        assert payload["page"] == page
        assert payload["page_size"] == 30
        assert all(item["creator"] == "owner" for item in payload["sessions"])
        ids.extend(item["session_id"] for item in payload["sessions"])
    # Ties on updated_at fall back to descending session_id for stable pages.
    assert ids == [f"session-{index:03}" for index in reversed(range(125))]

    empty = await service.get_chat_sessions(
        username="owner", page=6, page_size=30, platform_id="webchat"
    )
    assert empty["sessions"] == []

    bounded = await service.get_chat_sessions(
        username="owner", page=0, page_size=1000, platform_id=None
    )
    assert bounded["page"] == 1
    assert bounded["page_size"] == 100

    with pytest.raises(OpenApiServiceError):
        await service.get_chat_sessions(
            username="owner", page="x", page_size=20, platform_id=None
        )


@pytest.mark.asyncio
async def test_get_session_returns_session_metadata(temp_db: SQLiteDatabase):
    """Return metadata for an owned session and reject foreign sessions."""
    service = _chat_service(temp_db)
    await temp_db.create_platform_session(
        creator="owner",
        platform_id="webchat",
        session_id="session-1",
        display_name="Session title",
    )
    await temp_db.create_platform_session(
        creator="other", platform_id="webchat", session_id="foreign"
    )

    result = await service.get_session("owner", "session-1", page_size=50)

    assert result["session"]["session_id"] == "session-1"
    assert result["session"]["display_name"] == "Session title"
    assert result["session"]["platform_id"] == "webchat"
    assert result["session"]["created_at"].startswith("2026-")
    assert result["page"] == 1
    assert result["page_size"] == 50

    with pytest.raises(ChatServiceError, match="Permission denied"):
        await service.get_session("owner", "foreign", page_size=50)
