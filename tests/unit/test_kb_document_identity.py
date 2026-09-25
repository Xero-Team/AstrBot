"""Tests for knowledge-base document identity lookups."""

import hashlib

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from astrbot.core.knowledge_base.kb_db_sqlite import (
    KBSQLiteDatabase,
    file_identity_key,
)
from astrbot.core.knowledge_base.models import KBDocument, KnowledgeBase


@pytest_asyncio.fixture
async def kb_db(tmp_path):
    db_path = str(tmp_path / "test_kb.db")
    db = KBSQLiteDatabase(db_path)
    await db.initialize()
    try:
        yield db
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_get_document_by_identity_returns_matching_row(kb_db):
    kb = KnowledgeBase(kb_name="Identity KB")
    async with kb_db.get_db() as session, session.begin():
        session.add(kb)
        await session.flush()
        kb_id = kb.kb_id

    doc = KBDocument(
        kb_id=kb_id,
        doc_name="readme.md",
        file_type="md",
        file_size=12,
        file_path="doc-live",
        identity_key="file:readme.md",
        content_hash="a" * 64,
        source_kind="file",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(doc)
        await session.flush()
        doc_id = doc.doc_id

    matched = await kb_db.get_document_by_identity(kb_id, "file:readme.md")
    assert matched is not None
    assert matched.doc_id == doc_id
    missing = await kb_db.get_document_by_identity(kb_id, "file:other.md")
    assert missing is None


@pytest.mark.asyncio
async def test_identity_unique_index_rejects_duplicate_keys(kb_db):
    kb = KnowledgeBase(kb_name="Unique Index KB")
    async with kb_db.get_db() as session, session.begin():
        session.add(kb)
        await session.flush()
        kb_id = kb.kb_id

    first = KBDocument(
        kb_id=kb_id,
        doc_name="one.md",
        file_type="md",
        file_size=1,
        file_path="one",
        identity_key="file:one.md",
        source_kind="file",
    )
    second = KBDocument(
        kb_id=kb_id,
        doc_name="two.md",
        file_type="md",
        file_size=1,
        file_path="two",
        identity_key="file:one.md",
        source_kind="file",
    )
    async with kb_db.get_db() as session, session.begin():
        session.add(first)
        await session.flush()

    with pytest.raises(IntegrityError):
        async with kb_db.get_db() as session, session.begin():
            session.add(second)


def test_file_identity_key_hashes_long_posix() -> None:
    posix = "docs/" + ("a" * 700)
    digest = hashlib.sha256(posix.encode("utf-8")).hexdigest()
    assert file_identity_key(posix) == f"file:sha256:{digest}"
    assert file_identity_key("short.md") == "file:short.md"
