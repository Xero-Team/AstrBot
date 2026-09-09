"""Tests for knowledge-base document identity schema and backfill."""

import hashlib
import sqlite3
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from astrbot.core.knowledge_base.kb_db_sqlite import (
    KBSQLiteDatabase,
    file_identity_key,
    posix_identity_input,
)
from astrbot.core.knowledge_base.models import KBDocument, KnowledgeBase

_LEGACY_KB_DOCUMENTS_DDL = """
CREATE TABLE kb_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id VARCHAR(36) NOT NULL UNIQUE,
    kb_id VARCHAR(36) NOT NULL,
    doc_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    file_size INTEGER NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    media_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _create_legacy_db(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(_LEGACY_KB_DOCUMENTS_DDL)
        conn.commit()
    finally:
        conn.close()


def _insert_legacy_document(
    path: str,
    *,
    kb_id: str,
    doc_id: str,
    doc_name: str,
    file_type: str = "md",
) -> None:
    conn = sqlite3.connect(path)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO kb_documents (
                doc_id, kb_id, doc_name, file_type, file_size, file_path,
                chunk_count, media_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 10, '', 0, 0, ?, ?)
            """,
            (doc_id, kb_id, doc_name, file_type, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _column_names(path: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("PRAGMA table_info(kb_documents)").fetchall()
        return {row[1] for row in rows}
    finally:
        conn.close()


def _index_sql(path: str) -> str:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='uix_kb_identity'",
        ).fetchall()
        return " ".join(row[0] or "" for row in rows)
    finally:
        conn.close()


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
async def test_fresh_initialize_adds_identity_fields_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / "fresh_kb.db")
    db = KBSQLiteDatabase(db_path)
    await db.initialize()
    try:
        columns = _column_names(db_path)
        assert {
            "identity_key",
            "content_hash",
            "source_kind",
            "source_url",
        }.issubset(columns)
        assert "kb_id" in _index_sql(db_path)
        assert "identity_key" in _index_sql(db_path)
        await db.initialize()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_duplicate_historical_names_get_distinct_legacy_keys(tmp_path):
    db_path = str(tmp_path / "dup_kb.db")
    _create_legacy_db(db_path)
    kb_id = "kb-dup"
    _insert_legacy_document(
        db_path,
        kb_id=kb_id,
        doc_id="doc-a",
        doc_name="a.md",
    )
    _insert_legacy_document(
        db_path,
        kb_id=kb_id,
        doc_id="doc-b",
        doc_name="a.md",
    )

    db = KBSQLiteDatabase(db_path)
    await db.initialize()
    try:
        first = await db.get_document_by_id("doc-a")
        second = await db.get_document_by_id("doc-b")
        assert first is not None
        assert second is not None
        assert first.identity_key == "legacy:doc-a"
        assert second.identity_key == "legacy:doc-b"
        assert first.source_kind == "file"
        assert second.source_kind == "file"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_historical_url_row_uses_legacy_key_not_url_sha256(tmp_path):
    db_path = str(tmp_path / "url_kb.db")
    _create_legacy_db(db_path)
    kb_id = "kb-url"
    _insert_legacy_document(
        db_path,
        kb_id=kb_id,
        doc_id="doc-url",
        doc_name="article.url",
        file_type="url",
    )

    db = KBSQLiteDatabase(db_path)
    await db.initialize()
    try:
        doc = await db.get_document_by_id("doc-url")
        assert doc is not None
        assert doc.identity_key == "legacy:doc-url"
        assert doc.source_kind == "url"
        hashed = hashlib.sha256(b"https://example.com/article").hexdigest()
        matched = await db.get_document_by_identity(kb_id, f"url:sha256:{hashed}")
        assert matched is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_unique_file_name_backfills_live_file_key(tmp_path):
    db_path = str(tmp_path / "unique_kb.db")
    _create_legacy_db(db_path)
    kb_id = "kb-unique"
    _insert_legacy_document(
        db_path,
        kb_id=kb_id,
        doc_id="doc-unique",
        doc_name="guides/ops.md",
    )

    db = KBSQLiteDatabase(db_path)
    await db.initialize()
    try:
        doc = await db.get_document_by_id("doc-unique")
        assert doc is not None
        expected = file_identity_key(posix_identity_input("guides/ops.md"))
        assert doc.identity_key == expected
        assert expected == "file:guides/ops.md"
        matched = await db.get_document_by_identity(kb_id, expected)
        assert matched is not None
        assert matched.doc_id == "doc-unique"
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
