"""Migration sequence for the main SQLite store (``data/astrbot.db``)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlmodel import SQLModel

from astrbot.core.db.migrations.runner import Migration
from astrbot.core.db.po.registry import import_all_models


async def _initial_schema(conn: AsyncConnection) -> None:
    """Create the current schema on a fresh store.

    ``create_all`` is idempotent, so this is also the baseline for a store that
    already has the current tables. The reshape from a legacy ``data_v4.db`` is
    handled by the one-time import, not by a step here.
    """
    import_all_models()
    await conn.run_sync(SQLModel.metadata.create_all)


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "create current schema", _initial_schema),
)
