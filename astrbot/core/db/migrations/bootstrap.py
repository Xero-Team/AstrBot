"""One-time import of a legacy ``data_v4.db`` into the reshaped store.

The store was renamed to ``astrbot.db`` and its tables reshaped (surrogate
``id`` keys, foreign keys, reordered columns). Rather than write per-table
rebuild SQL, the upgrade creates the current schema and copies legacy rows in,
mapping the few renamed columns and dropping columns that no longer exist. The
legacy file is left on disk as a backup.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import Column
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

from astrbot.core.db.migrations.runner import Migration, run_migrations
from astrbot.core.db.po.registry import import_all_models

logger = logging.getLogger("astrbot")

# Legacy column names that changed during the reshape, per table.
LEGACY_COLUMN_RENAMES: dict[str, dict[str, str]] = {
    "api_keys": {"inner_id": "id"},
    "attachments": {"inner_attachment_id": "id"},
    "chatui_projects": {"inner_id": "id"},
    "conversations": {"inner_conversation_id": "id"},
    "platform_sessions": {"inner_id": "id"},
}


def _legacy_table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _map_row(
    table: str,
    row: sqlite3.Row,
    columns: dict[str, Column[Any]],
) -> dict | None:
    renames = LEGACY_COLUMN_RENAMES.get(table, {})
    mapped: dict = {}
    for key in row.keys():
        new_key = renames.get(key, key)
        if new_key in columns:
            mapped[new_key] = row[key]
    # Columns added by the reshape have no legacy value. Fill NOT NULL columns
    # that carry a Python-side default (for example the timestamp columns added
    # to session_project_relations) so the copy does not fail on old rows.
    for name, column in columns.items():
        if name in mapped or column.nullable or column.server_default is not None:
            continue
        default = column.default
        arg = getattr(default, "arg", None)
        if arg is None:
            continue
        # SQLAlchemy calls callable defaults with a DefaultExecutionContext; the
        # SQLModel factories ignore it, so ``None`` is a safe stand-in here.
        mapped[name] = arg(None) if callable(arg) else arg
    return mapped or None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _insert_statement(table_name: str, columns: list[str]) -> str:
    column_list = ", ".join(_quote(column) for column in columns)
    placeholders = ", ".join(f":{column}" for column in columns)
    return f"INSERT INTO {_quote(table_name)} ({column_list}) VALUES ({placeholders})"


async def import_legacy_main_database(
    dest_engine: AsyncEngine,
    legacy_path: Path,
    migrations: tuple[Migration, ...],
) -> int:
    """Copy a legacy main database into the current store.

    Rows are inserted with driver-level parameters so the values keep their
    on-disk SQLite representation: legacy ``DateTime`` columns hold ISO text and
    ``JSON`` columns hold JSON text, which is exactly what the current columns
    expect. Going through SQLAlchemy bind processors instead would reject the
    already-serialized text.

    Args:
        dest_engine: Engine bound to the new ``astrbot.db``.
        legacy_path: Path to the legacy ``data_v4.db``.
        migrations: The main store's migration sequence (for its baseline).

    Returns:
        The number of rows copied across all tables.
    """
    import_all_models()
    await run_migrations(dest_engine, "main", migrations)

    source = sqlite3.connect(f"file:{legacy_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    copied = 0
    try:
        existing = _legacy_table_names(source)
        pending: list[tuple[str, list[dict]]] = []
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing:
                continue
            target_columns = {column.name: column for column in table.columns}
            mapped_rows = []
            for row in source.execute(f"SELECT * FROM {_quote(table.name)}"):
                mapped = _map_row(table.name, row, target_columns)
                if mapped is not None:
                    mapped_rows.append(mapped)
            if mapped_rows:
                pending.append((table.name, mapped_rows))

        async with dest_engine.connect() as conn:
            # Legacy data predates the foreign keys; import it as-is. The PRAGMA
            # must run outside a transaction, so set it before BEGIN.
            await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            await conn.exec_driver_sql("BEGIN")
            try:
                for table_name, mapped_rows in pending:
                    statement = _insert_statement(table_name, list(mapped_rows[0]))
                    await conn.exec_driver_sql(statement, mapped_rows)
                    copied += len(mapped_rows)
                    logger.info(
                        "imported %s rows from legacy %s",
                        len(mapped_rows),
                        table_name,
                    )
            except BaseException:
                await conn.exec_driver_sql("ROLLBACK")
                raise
            else:
                await conn.exec_driver_sql("COMMIT")
    finally:
        source.close()
    return copied


__all__ = ["LEGACY_COLUMN_RENAMES", "import_legacy_main_database"]
