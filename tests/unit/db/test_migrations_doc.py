"""Tests for the knowledge-base document-store migrations."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from astrbot.core.db import create_sqlite_async_engine, dispose_async_engine
from astrbot.core.db.migrations.runner import LEDGER_TABLE
from astrbot.core.db.vec_db.document_storage import (
    BaseDocModel,
    Document,
    DocumentStorage,
)

pytestmark = pytest.mark.asyncio


async def _ledger_revisions(engine, store: str) -> list[int]:
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql(
            f"SELECT revision FROM {LEDGER_TABLE} WHERE store = '{store}' "
            "ORDER BY revision",
        )
        return [row[0] for row in rows.fetchall()]


async def test_populated_pre_runner_doc_store_migrates_to_head(tmp_path):
    db_path = tmp_path / "doc.db"

    # A pre-runner store: tables created by the old ``create_all`` path with a
    # document row, but no migration ledger.
    seed_engine = create_sqlite_async_engine(str(db_path))
    try:
        async with seed_engine.begin() as conn:
            await conn.run_sync(BaseDocModel.metadata.create_all)
            await conn.exec_driver_sql(
                "INSERT INTO documents (doc_id, text, metadata) VALUES "
                "('d1', 'hello', '{\"kb_id\": \"kb1\"}')",
            )
    finally:
        await dispose_async_engine(seed_engine, None)

    storage = DocumentStorage(str(db_path))
    try:
        await storage.initialize()
        assert await _ledger_revisions(storage.engine, "doc") == [1]

        session_factory = async_sessionmaker(
            storage.engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            documents = (await session.execute(select(Document))).scalars().all()
        assert [document.doc_id for document in documents] == ["d1"]
    finally:
        await storage.close()
