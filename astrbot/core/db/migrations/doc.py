"""Migration sequence for a knowledge-base document store (``doc.db``)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from astrbot.core.db.migrations.runner import Migration


async def _initial_schema(conn: AsyncConnection) -> None:
    """Create the current document schema on a fresh store."""
    # Imported lazily to avoid a cycle with document_storage, which imports
    # this module for its migration sequence.
    from astrbot.core.db.vec_db.document_storage import BaseDocModel

    await conn.run_sync(BaseDocModel.metadata.create_all)
    await conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_doc_id_unique "
        "ON documents(doc_id)",
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "create current schema", _initial_schema),
)
