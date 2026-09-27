"""Migration sequence for the knowledge-base metadata store (``kb.db``)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from astrbot.core.db.migrations.runner import Migration
from astrbot.core.knowledge_base.models import BaseKBModel


async def _initial_schema(conn: AsyncConnection) -> None:
    """Create the current knowledge-base schema on a fresh store."""
    await conn.run_sync(BaseKBModel.metadata.create_all)


async def _add_kb_media_updated_at(conn: AsyncConnection) -> None:
    """Add ``kb_media.updated_at`` to a store created before the reshape.

    ``create_all`` does not alter existing tables, so an old ``kb.db`` keeps its
    original ``kb_media`` columns. The step is conditional because a fresh store
    already has the column from the baseline.
    """
    result = await conn.exec_driver_sql("PRAGMA table_info(kb_media)")
    columns = {row[1] for row in result.fetchall()}
    if "updated_at" in columns:
        return
    await conn.exec_driver_sql(
        "ALTER TABLE kb_media ADD COLUMN updated_at DATETIME",
    )
    await conn.exec_driver_sql(
        "UPDATE kb_media SET updated_at = created_at WHERE updated_at IS NULL",
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "create current schema", _initial_schema),
    Migration(2, "add kb_media.updated_at", _add_kb_media_updated_at),
)
