"""Create and migrate the main SQLite schema from registered SQLModel tables."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import text

from astrbot.core.db.migrations.main import MIGRATIONS as MAIN_MIGRATIONS
from astrbot.core.db.migrations.runner import run_migrations
from astrbot.core.db.po.registry import import_all_models

_SQLITE_RUNTIME_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=30000",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=20000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=134217728",
    "PRAGMA optimize",
)


def _install_runtime_pragmas(engine: AsyncEngine) -> None:
    sync_engine = engine.sync_engine
    if getattr(sync_engine, "_astrbot_pragmas_installed", False):
        return

    @event.listens_for(sync_engine, "connect")
    def _apply(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for pragma in _SQLITE_RUNTIME_PRAGMAS:
                cursor.execute(pragma)
        finally:
            cursor.close()

    sync_engine._astrbot_pragmas_installed = True  # type: ignore[attr-defined]


async def apply_runtime_pragmas(engine: AsyncEngine) -> None:
    """Apply connection-scoped SQLite PRAGMAs to every future connection."""
    _install_runtime_pragmas(engine)
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA optimize"))
        await conn.commit()


async def initialize_sqlite_schema(engine: AsyncEngine) -> None:
    """Register models, run pending migrations, and apply PRAGMAs.

    A fresh file runs the baseline step, which creates the current schema. An
    existing file replays only the steps it has not seen. Upgrading from the
    legacy ``data_v4.db`` is handled by the one-time import before this call.

    Args:
        engine: Async SQLAlchemy engine bound to the main database file.
    """
    import_all_models()
    await run_migrations(engine, "main", MAIN_MIGRATIONS)
    await apply_runtime_pragmas(engine)
