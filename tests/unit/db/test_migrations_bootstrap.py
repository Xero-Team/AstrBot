"""Tests for the one-time legacy ``data_v4.db`` import."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel, col, select

from astrbot.core.db import create_sqlite_async_engine, dispose_async_engine
from astrbot.core.db.migrations import bootstrap
from astrbot.core.db.migrations.bootstrap import import_legacy_main_database
from astrbot.core.db.migrations.runner import MigrationError
from astrbot.core.db.migrations.main import MIGRATIONS
from astrbot.core.db.po import (
    ApiKey,
    AuthAuditLog,
    ConversationV2,
    SessionProjectRelation,
)
from astrbot.core.db.po.registry import import_all_models
from astrbot.core.db.schema import initialize_sqlite_schema
from astrbot.core.db.sqlite import SQLiteDatabase

pytestmark = pytest.mark.asyncio

_LEGACY_DDL = """
CREATE TABLE api_keys (
    inner_id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id TEXT NOT NULL,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    scopes TEXT,
    created_by TEXT NOT NULL,
    last_used_at TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    legacy_only TEXT
);
CREATE TABLE conversations (
    inner_conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT,
    title TEXT,
    prompt_id TEXT,
    token_usage INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE session_project_relations (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL
);
CREATE TABLE auth_audit_log (
    audit_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    request_id TEXT,
    subject_id TEXT NOT NULL,
    effective_role TEXT,
    source TEXT NOT NULL,
    platform TEXT,
    config_id TEXT,
    action TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    step_up_id TEXT,
    outcome TEXT,
    latency_ms INTEGER,
    metadata_json TEXT NOT NULL
);
"""


def _write_legacy(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_LEGACY_DDL)
        conn.execute(
            "INSERT INTO api_keys (inner_id, key_id, name, key_hash, key_prefix, "
            "scopes, created_by, last_used_at, expires_at, revoked_at, created_at, "
            "updated_at, legacy_only) VALUES "
            "(7, 'key-7', 'legacy', 'hash-7', 'sk-7', '[\"chat\"]', 'owner', NULL, "
            "NULL, NULL, '2026-09-24 12:10:43.876623', "
            "'2026-09-24 12:10:43.876623', 'ignored')",
        )
        conn.execute(
            "INSERT INTO conversations (inner_conversation_id, conversation_id, "
            "platform_id, user_id, content, title, prompt_id, token_usage, "
            "created_at, updated_at) VALUES "
            "(3, 'conv-3', 'aiocqhttp', 'user-a', '[{\"role\": \"user\", "
            '"content": "hi"}]\', \'title\', NULL, 12, '
            "'2026-09-24 12:10:43.876623', '2026-09-24 12:10:43.876623')",
        )
        conn.execute(
            "INSERT INTO session_project_relations (id, session_id, project_id) "
            "VALUES (1, 'session-1', 'project-1')",
        )
        conn.execute(
            "INSERT INTO auth_audit_log (audit_id, timestamp, subject_id, source, "
            "action, resource_id, decision, reason, metadata_json) VALUES "
            "('audit-1', '2026-09-24 12:10:43.876623', 'im:test', 'adapter', "
            "'read', 'res', 'allow', 'ok', '{\"scope\": \"instance\"}')",
        )
        conn.commit()
    finally:
        conn.close()


async def _column_names(engine, table: str) -> set[str]:
    def inspect(sync_conn):
        return {column["name"] for column in sa_inspect(sync_conn).get_columns(table)}

    async with engine.connect() as conn:
        return await conn.run_sync(inspect)


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ).fetchall()
    return {row[0] for row in rows}


async def test_import_maps_renames_drops_columns_and_keeps_types(tmp_path):
    import_all_models()
    legacy = tmp_path / "data_v4.db"
    _write_legacy(legacy)
    engine = create_sqlite_async_engine(str(tmp_path / "astrbot.db"))
    try:
        copied = await import_legacy_main_database(engine, legacy, MIGRATIONS)
        assert copied == 4

        api_key_columns = await _column_names(engine, "api_keys")
        assert "legacy_only" not in api_key_columns
        assert "inner_id" not in api_key_columns
        assert "id" in api_key_columns

        session_project_columns = await _column_names(
            engine, "session_project_relations"
        )
        assert {"created_at", "updated_at"} <= session_project_columns

        # Target tables absent from the legacy file are created empty.
        assert "attachments" in await _table_names(engine)

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            api_key = (await session.execute(select(ApiKey))).scalars().one()
            assert api_key.id == 7
            assert api_key.scopes == ["chat"]

            conversation = (
                (await session.execute(select(ConversationV2))).scalars().one()
            )
            assert conversation.id == 3
            assert conversation.content == [{"role": "user", "content": "hi"}]

            relation = (
                (await session.execute(select(SessionProjectRelation))).scalars().one()
            )
            assert relation.created_at is not None
            assert relation.updated_at is not None

            audit = (await session.execute(select(AuthAuditLog))).scalars().one()
            assert audit.metadata_json == {"scope": "instance"}
            assert isinstance(audit.timestamp, datetime)
            assert audit.timestamp == datetime(2026, 9, 24, 12, 10, 43, 876623)
    finally:
        await dispose_async_engine(engine, None)


async def test_database_initialize_imports_explicit_legacy_path(tmp_path):
    legacy = tmp_path / "data_v4.db"
    _write_legacy(legacy)
    db = SQLiteDatabase(str(tmp_path / "astrbot.db"), str(legacy))
    try:
        await db.initialize()
        async with db.get_db() as session:
            conversations = (
                (await session.execute(select(ConversationV2))).scalars().all()
            )
        assert [conversation.id for conversation in conversations] == [3]
        # The legacy file is left in place as a backup.
        assert legacy.exists()
    finally:
        await db.close()


async def test_import_handles_legacy_path_with_uri_characters(tmp_path):
    root = tmp_path / "data #1 dir"
    root.mkdir()
    legacy = root / "data_v4.db"
    _write_legacy(legacy)
    db = SQLiteDatabase(str(root / "astrbot.db"), str(legacy))
    try:
        await db.initialize()
        async with db.get_db() as session:
            conversations = (
                (await session.execute(select(ConversationV2))).scalars().all()
            )
        assert [conversation.id for conversation in conversations] == [3]
    finally:
        await db.close()


async def test_database_without_legacy_path_never_imports_sibling(tmp_path):
    legacy = tmp_path / "data_v4.db"
    _write_legacy(legacy)
    db = SQLiteDatabase(str(tmp_path / "astrbot.db"))
    try:
        await db.initialize()
        async with db.get_db() as session:
            conversations = (
                (await session.execute(select(ConversationV2))).scalars().all()
            )
        assert conversations == []
    finally:
        await db.close()


async def test_initialize_retries_import_when_marker_is_missing(tmp_path):
    legacy = tmp_path / "data_v4.db"
    _write_legacy(legacy)
    db = SQLiteDatabase(str(tmp_path / "astrbot.db"), str(legacy))
    try:
        # Simulate a crash after the baseline schema committed but before the
        # legacy copy: tables and the ``main`` ledger exist, but no rows and no
        # import marker.
        await initialize_sqlite_schema(db.engine)

        await db.initialize()

        async with db.get_db() as session:
            conversations = (
                (await session.execute(select(ConversationV2))).scalars().all()
            )
        assert [conversation.id for conversation in conversations] == [3]
    finally:
        await db.close()


async def test_import_writes_every_row_across_batches(tmp_path, monkeypatch):
    import_all_models()
    legacy = tmp_path / "data_v4.db"
    conn = sqlite3.connect(legacy)
    try:
        conn.executescript(_LEGACY_DDL)
        conn.executemany(
            "INSERT INTO api_keys (inner_id, key_id, name, key_hash, key_prefix, "
            "scopes, created_by, last_used_at, expires_at, revoked_at, created_at, "
            "updated_at) VALUES (?, ?, 'batch', ?, ?, NULL, 'owner', NULL, NULL, "
            "NULL, '2026-09-24 12:10:43.876623', '2026-09-24 12:10:43.876623')",
            [(i, f"key-{i}", f"hash-{i}", f"sk-{i}") for i in range(1, 6)],
        )
        conn.commit()
    finally:
        conn.close()

    # Smaller than the row count so the final partial batch is exercised.
    monkeypatch.setattr(bootstrap, "IMPORT_BATCH_SIZE", 2)

    engine = create_sqlite_async_engine(str(tmp_path / "astrbot.db"))
    try:
        copied = await import_legacy_main_database(engine, legacy, MIGRATIONS)
        assert copied == 5

        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            keys = (
                (await session.execute(select(ApiKey).order_by(col(ApiKey.id))))
                .scalars()
                .all()
            )
        assert [key.id for key in keys] == [1, 2, 3, 4, 5]
    finally:
        await dispose_async_engine(engine, None)


async def test_populated_store_without_ledger_refuses_startup(tmp_path):
    import_all_models()
    db_path = tmp_path / "astrbot.db"

    # Simulate a populated store that predates the runner: current tables and
    # a user row, but no ``main`` ledger row.
    seed_engine = create_sqlite_async_engine(str(db_path))
    try:
        async with seed_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            await conn.exec_driver_sql(
                "INSERT INTO platform_sessions "
                "(session_id, platform_id, creator, created_at, updated_at) VALUES "
                "('s1', 'webchat', 'owner', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
            )
    finally:
        await dispose_async_engine(seed_engine, None)

    db = SQLiteDatabase(str(db_path))
    try:
        with pytest.raises(MigrationError, match="no 'main' migration ledger"):
            await db.initialize()
    finally:
        await db.close()
