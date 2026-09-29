"""Tests for the per-store SQLite migration runner."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from astrbot.core.db import create_sqlite_async_engine, dispose_async_engine
from astrbot.core.db.migrations import (
    LEDGER_TABLE,
    Migration,
    MigrationError,
    run_migrations,
)

pytestmark = pytest.mark.asyncio


async def _make_engine(tmp_path):
    engine = create_sqlite_async_engine(str(tmp_path / "test.db"))
    return engine


def _create_widgets(statement: str = "CREATE TABLE widgets (id INTEGER PRIMARY KEY)"):
    async def upgrade(conn) -> None:
        await conn.execute(text(statement))

    return upgrade


async def _ledger_rows(engine, store: str):
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    f"SELECT revision, checksum FROM {LEDGER_TABLE} "
                    "WHERE store = :store ORDER BY revision",
                ),
                {"store": store},
            )
        ).fetchall()


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        ).fetchall()
    return {row[0] for row in rows}


async def test_fresh_store_applies_every_step_once(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        steps = [
            Migration(1, "create widgets", _create_widgets()),
            Migration(
                2,
                "add name",
                _add_widget_name(),
            ),
        ]
        assert await run_migrations(engine, "main", steps) == 2
        rows = await _ledger_rows(engine, "main")
        assert [row[0] for row in rows] == [1, 2]
        assert "widgets" in await _table_names(engine)
        async with engine.connect() as conn:
            cols = {
                row[1]
                for row in (
                    await conn.execute(text("PRAGMA table_info(widgets)"))
                ).fetchall()
            }
        assert "name" in cols

        # Re-running is a no-op.
        assert await run_migrations(engine, "main", steps) == 0
        assert len(await _ledger_rows(engine, "main")) == 2
    finally:
        await dispose_async_engine(engine, None)


def _add_widget_name():
    async def upgrade(conn) -> None:
        await conn.execute(text("ALTER TABLE widgets ADD COLUMN name TEXT"))

    return upgrade


async def test_each_store_keeps_independent_state(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        assert await run_migrations(engine, "main", [Migration(1, "a", _noop())]) == 1
        # Same engine, different store: its own ledger, its own steps.
        assert await run_migrations(engine, "kb", [Migration(1, "b", _noop())]) == 1
        assert await run_migrations(engine, "kb", [Migration(1, "b", _noop())]) == 0
        assert len(await _ledger_rows(engine, "main")) == 1
        assert len(await _ledger_rows(engine, "kb")) == 1
    finally:
        await dispose_async_engine(engine, None)


def _noop():
    async def upgrade(conn) -> None:
        return None

    return upgrade


async def test_changed_applied_step_refuses_to_start(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        await run_migrations(
            engine, "main", [Migration(1, "create", _create_widgets())]
        )
        # Simulate an applied step whose source was edited afterwards.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"UPDATE {LEDGER_TABLE} SET checksum = 'deadbeef' WHERE store = 'main'"
                ),
            )
        with pytest.raises(MigrationError, match="changed after it was applied"):
            await run_migrations(
                engine,
                "main",
                [Migration(1, "create", _create_widgets())],
            )
    finally:
        await dispose_async_engine(engine, None)


async def test_store_ahead_of_code_refuses_to_start(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        await run_migrations(
            engine,
            "main",
            [
                Migration(1, "one", _noop()),
                Migration(2, "two", _noop()),
            ],
        )
        with pytest.raises(MigrationError, match="newer than this build"):
            await run_migrations(engine, "main", [Migration(1, "one", _noop())])
    finally:
        await dispose_async_engine(engine, None)


async def test_missing_applied_step_refuses_to_start(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        await run_migrations(
            engine,
            "main",
            [Migration(1, "one", _noop()), Migration(2, "two", _noop())],
        )
        with pytest.raises(MigrationError, match="is missing from this build"):
            await run_migrations(
                engine,
                "main",
                [Migration(2, "two", _noop())],
            )
    finally:
        await dispose_async_engine(engine, None)


async def test_failing_step_rolls_back_and_records_nothing(tmp_path):
    engine = await _make_engine(tmp_path)
    try:

        async def boom(conn) -> None:
            await conn.execute(text("CREATE TABLE boom (id INTEGER PRIMARY KEY)"))
            raise RuntimeError("migration failed")

        with pytest.raises(RuntimeError, match="migration failed"):
            await run_migrations(engine, "main", [Migration(1, "boom", boom)])

        assert "boom" not in await _table_names(engine)
        assert await _ledger_rows(engine, "main") == []
    finally:
        await dispose_async_engine(engine, None)


async def test_duplicate_revisions_are_rejected(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        with pytest.raises(MigrationError, match="duplicate migration revision"):
            await run_migrations(
                engine,
                "main",
                [Migration(1, "a", _noop()), Migration(1, "b", _noop())],
            )
    finally:
        await dispose_async_engine(engine, None)


async def test_non_contiguous_sequence_refuses_before_applying_any_step(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        # Revision 2 is missing. Applying 1 and 3 would record a gapped ledger,
        # so the first startup must refuse instead of bricking the next one.
        with pytest.raises(MigrationError, match="has a gap between revision"):
            await run_migrations(
                engine,
                "main",
                [
                    Migration(1, "one", _create_widgets()),
                    Migration(3, "three", _noop()),
                ],
            )
        assert await _ledger_rows(engine, "main") == []
        assert "widgets" not in await _table_names(engine)
    finally:
        await dispose_async_engine(engine, None)


async def test_gap_in_applied_revisions_refuses_to_start(tmp_path):
    engine = await _make_engine(tmp_path)
    try:
        await run_migrations(
            engine,
            "main",
            [Migration(1, "one", _noop()), Migration(2, "two", _noop())],
        )
        # Simulate a store whose middle ledger row was lost or removed.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"DELETE FROM {LEDGER_TABLE} WHERE store = 'main' AND revision = 1"
                ),
            )
        with pytest.raises(MigrationError, match="gap in its applied revisions"):
            await run_migrations(
                engine,
                "main",
                [Migration(1, "one", _noop()), Migration(2, "two", _noop())],
            )
    finally:
        await dispose_async_engine(engine, None)
