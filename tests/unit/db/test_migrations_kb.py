"""Tests for the knowledge-base metadata migrations."""

from __future__ import annotations

import sqlite3

import pytest
from sqlmodel import select

from astrbot.core.db.migrations.runner import LEDGER_TABLE
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import KBMedia

pytestmark = pytest.mark.asyncio

_OLD_KB_MEDIA_DDL = """
CREATE TABLE kb_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id VARCHAR(36) NOT NULL,
    doc_id VARCHAR(36) NOT NULL,
    kb_id VARCHAR(36) NOT NULL,
    media_type VARCHAR(20) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL
)
"""


def _write_old_kb_media(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_OLD_KB_MEDIA_DDL)
        conn.execute(
            "INSERT INTO kb_media (media_id, doc_id, kb_id, media_type, file_name, "
            "file_path, file_size, mime_type, created_at) VALUES "
            "('m1', 'd1', 'kb1', 'image', 'a.png', '/tmp/a.png', 10, 'image/png', "
            "'2026-09-24 12:10:43.876623')",
        )
        conn.commit()
    finally:
        conn.close()


async def _ledger_revisions(engine, store: str) -> list[int]:
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql(
            f"SELECT revision FROM {LEDGER_TABLE} WHERE store = '{store}' "
            "ORDER BY revision",
        )
        return [row[0] for row in rows.fetchall()]


async def _column_names(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        return {row[1] for row in rows.fetchall()}


async def test_old_kb_media_gains_updated_at(tmp_path):
    db_path = tmp_path / "kb.db"
    _write_old_kb_media(db_path)
    db = KBSQLiteDatabase(str(db_path))
    try:
        await db.initialize()
        assert "updated_at" in await _column_names(db.engine, "kb_media")
        assert await _ledger_revisions(db.engine, "kb") == [1, 2]

        async with db.get_db() as session:
            media = (await session.execute(select(KBMedia))).scalars().one()
        assert media.media_id == "m1"
        assert media.updated_at is not None
    finally:
        await db.close()


async def test_fresh_kb_media_has_updated_at_after_migrations(tmp_path):
    db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    try:
        await db.initialize()
        assert "updated_at" in await _column_names(db.engine, "kb_media")
        assert await _ledger_revisions(db.engine, "kb") == [1, 2]
    finally:
        await db.close()
