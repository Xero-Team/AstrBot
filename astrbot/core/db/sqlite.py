import asyncio
import typing as T
from contextlib import asynccontextmanager
from pathlib import Path
from weakref import WeakSet

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel

from astrbot.core.db import (
    create_sqlite_async_engine,
    dispose_async_engine,
    sqlite_async_url,
    track_aiosqlite_workers,
)
from astrbot.core.db.migrations.bootstrap import (
    LEGACY_IMPORT_MARKER_STORE,
    import_legacy_main_database,
)
from astrbot.core.db.migrations.main import MIGRATIONS as MAIN_MIGRATIONS
from astrbot.core.db.migrations.runner import LEDGER_TABLE
from astrbot.core.db.po.registry import import_all_models
from astrbot.core.db.schema import apply_runtime_pragmas, initialize_sqlite_schema
from astrbot.core.db.stores.aliases import UmoAliasStoreMixin
from astrbot.core.db.stores.api_keys import ApiKeyStoreMixin
from astrbot.core.db.stores.attachments import AttachmentStoreMixin
from astrbot.core.db.stores.commands import CommandStoreMixin
from astrbot.core.db.stores.conversations import ConversationStoreMixin
from astrbot.core.db.stores.cron import CronStoreMixin
from astrbot.core.db.stores.knowledge_base import KnowledgeBaseTaskStoreMixin
from astrbot.core.db.stores.memory import MemoryStoreMixin
from astrbot.core.db.stores.message_history import MessageHistoryStoreMixin
from astrbot.core.db.stores.preferences import PreferenceStoreMixin
from astrbot.core.db.stores.projects import ChatProjectStoreMixin
from astrbot.core.db.stores.prompts import PromptStoreMixin
from astrbot.core.db.stores.session_bridge import SessionBridgeStoreMixin
from astrbot.core.db.stores.sessions import PlatformSessionStoreMixin
from astrbot.core.db.stores.statistics import StatisticsStoreMixin
from astrbot.core.db.stores.webchat import WebChatThreadStoreMixin


class SQLiteDatabase(
    KnowledgeBaseTaskStoreMixin,
    StatisticsStoreMixin,
    MemoryStoreMixin,
    ConversationStoreMixin,
    MessageHistoryStoreMixin,
    WebChatThreadStoreMixin,
    AttachmentStoreMixin,
    ApiKeyStoreMixin,
    PromptStoreMixin,
    PreferenceStoreMixin,
    CommandStoreMixin,
    CronStoreMixin,
    PlatformSessionStoreMixin,
    SessionBridgeStoreMixin,
    UmoAliasStoreMixin,
    ChatProjectStoreMixin,
):
    def __init__(self, db_path: str, legacy_db_path: str | None = None) -> None:
        """Create the main store.

        Args:
            db_path: Path to the current ``astrbot.db`` file.
            legacy_db_path: Optional path to a pre-rename ``data_v4.db``. When it
                exists and the current store is empty, its rows are imported
                once at startup. Callers that pass ``None`` (tests and secondary
                stores) never touch another database.
        """
        self.db_path = db_path
        self.legacy_db_path = Path(legacy_db_path) if legacy_db_path else None
        self.DATABASE_URL = sqlite_async_url(db_path)
        self.engine = create_sqlite_async_engine(db_path)
        self._aiosqlite_workers = track_aiosqlite_workers(self.engine)
        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._active_sessions: WeakSet[AsyncSession] = WeakSet()
        self._init_lock = asyncio.Lock()
        self.inited = False

    async def _table_names(self) -> set[str]:
        async with self.engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
            return {row[0] for row in result.fetchall()}

    async def _legacy_import_done(self) -> bool:
        if LEDGER_TABLE not in await self._table_names():
            return False
        async with self.engine.connect() as conn:
            row = (
                await conn.exec_driver_sql(
                    "SELECT 1 FROM _schema_migrations WHERE store = ? LIMIT 1",
                    (LEGACY_IMPORT_MARKER_STORE,),
                )
            ).first()
        return row is not None

    async def _has_user_rows(self) -> bool:
        import_all_models()
        existing = await self._table_names()
        async with self.engine.connect() as conn:
            for name, table in SQLModel.metadata.tables.items():
                if name not in existing:
                    continue
                found = await conn.execute(select(1).select_from(table).limit(1))
                if found.first() is not None:
                    return True
        return False

    async def _needs_legacy_import(self) -> bool:
        if self.legacy_db_path is None or not self.legacy_db_path.exists():
            return False
        if not (await self._table_names()) - {"sqlite_sequence"}:
            return True
        if await self._legacy_import_done():
            return False
        # No completion marker: either the database was created normally (and is
        # empty) or an earlier import crashed after the baseline step. Retry only
        # while no user rows exist, so a populated store is never overwritten.
        return not await self._has_user_rows()

    async def initialize(self) -> None:
        """Initialize the database, importing a legacy file when present."""
        async with self._init_lock:
            if self.inited:
                return
            legacy_path = self.legacy_db_path
            if legacy_path is not None and await self._needs_legacy_import():
                await import_legacy_main_database(
                    self.engine, legacy_path, MAIN_MIGRATIONS
                )
                await apply_runtime_pragmas(self.engine)
            else:
                await initialize_sqlite_schema(self.engine)
            self.inited = True

    @asynccontextmanager
    async def get_db(self) -> T.AsyncGenerator[AsyncSession]:
        """Yield a tracked database session."""
        if not self.inited:
            await self.initialize()
        session = self.AsyncSessionLocal()
        self._active_sessions.add(session)
        try:
            yield session
        finally:
            try:
                await session.close()
            finally:
                self._active_sessions.discard(session)

    async def close(self) -> None:
        """Close tracked sessions and dispose the database engine."""
        for session in list(self._active_sessions):
            try:
                await session.close()
            finally:
                self._active_sessions.discard(session)
        await dispose_async_engine(self.engine, self._aiosqlite_workers)
        self.inited = False
