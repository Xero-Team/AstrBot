"""Schema equivalence between ``create_all`` and the migration sequence."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect

from astrbot.core.db import create_sqlite_async_engine, dispose_async_engine
from astrbot.core.db.migrations.main import MIGRATIONS
from astrbot.core.db.migrations.runner import LEDGER_TABLE, run_migrations
from astrbot.core.db.po.registry import import_all_models

pytestmark = pytest.mark.asyncio


def _normalized_schema(sync_conn) -> dict[str, dict]:
    inspector = sa_inspect(sync_conn)
    schema: dict[str, dict] = {}
    for table in inspector.get_table_names():
        if table.startswith("sqlite_") or table == LEDGER_TABLE:
            continue
        columns = {
            column["name"]: (
                str(column["type"]),
                bool(column["nullable"]),
                bool(column.get("primary_key")),
                column.get("server_default"),
            )
            for column in inspector.get_columns(table)
        }
        indexes = {
            (
                index["name"],
                tuple(index["column_names"]),
                bool(index.get("unique")),
            )
            for index in inspector.get_indexes(table)
        }
        uniques = {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints(table)
        }
        foreign_keys = {
            (
                foreign_key.get("name"),
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                (foreign_key.get("options") or {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(table)
        }
        schema[table] = {
            "columns": columns,
            "indexes": indexes,
            "uniques": uniques,
            "foreign_keys": foreign_keys,
        }
    return schema


async def test_create_all_matches_migration_schema(tmp_path):
    import_all_models()

    create_engine = create_sqlite_async_engine(str(tmp_path / "create-all.db"))
    migration_engine = create_sqlite_async_engine(str(tmp_path / "migrated.db"))
    try:
        from sqlmodel import SQLModel

        async with create_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await run_migrations(migration_engine, "main", MIGRATIONS)

        async with create_engine.connect() as conn:
            created = await conn.run_sync(_normalized_schema)
        async with migration_engine.connect() as conn:
            migrated = await conn.run_sync(_normalized_schema)

        assert migrated == created
    finally:
        await dispose_async_engine(create_engine, None)
        await dispose_async_engine(migration_engine, None)
