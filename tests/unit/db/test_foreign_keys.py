"""Foreign-key enforcement and cascade behavior on the main store."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from astrbot.core.db.sqlite import SQLiteDatabase

pytestmark = pytest.mark.asyncio


async def _count(engine, table: str) -> int:
    async with engine.connect() as conn:
        return (
            await conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table}")
        ).scalar_one()


async def test_foreign_keys_are_enforced(temp_db: SQLiteDatabase):
    await temp_db.initialize()
    async with temp_db.engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.exec_driver_sql(
                "INSERT INTO session_project_relations "
                "(session_id, project_id, created_at, updated_at) VALUES "
                "('missing-session', 'missing-project', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            )


async def test_deleting_parents_cascades_children(temp_db: SQLiteDatabase):
    await temp_db.initialize()
    async with temp_db.engine.begin() as conn:
        await conn.exec_driver_sql(
            "INSERT INTO platform_sessions "
            "(session_id, platform_id, creator, created_at, updated_at) VALUES "
            "('s1', 'webchat', 'owner', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
        )
        await conn.exec_driver_sql(
            "INSERT INTO chatui_projects "
            "(project_id, creator, title, created_at, updated_at) VALUES "
            "('p1', 'owner', 'project', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
        )
        await conn.exec_driver_sql(
            "INSERT INTO session_project_relations "
            "(session_id, project_id, created_at, updated_at) VALUES "
            "('s1', 'p1', '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
        )
        await conn.exec_driver_sql(
            "INSERT INTO webchat_threads "
            "(thread_id, creator, parent_session_id, parent_message_id, "
            "base_checkpoint_id, selected_text, created_at, updated_at) VALUES "
            "('t1', 'owner', 's1', 1, 'cp1', 'text', "
            "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
        )

        await conn.exec_driver_sql(
            "DELETE FROM platform_sessions WHERE session_id = 's1'",
        )

    assert await _count(temp_db.engine, "session_project_relations") == 0
    assert await _count(temp_db.engine, "webchat_threads") == 0
    assert await _count(temp_db.engine, "chatui_projects") == 1
