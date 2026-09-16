import asyncio
import typing as T
from contextlib import asynccontextmanager
from weakref import WeakSet

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from astrbot.core.db import (
    create_sqlite_async_engine,
    dispose_async_engine,
    sqlite_async_url,
    track_aiosqlite_workers,
)
from astrbot.core.db.schema import initialize_sqlite_schema
from astrbot.core.db.stores.aliases import UmoAliasStoreMixin
from astrbot.core.db.stores.api_keys import ApiKeyStoreMixin
from astrbot.core.db.stores.attachments import AttachmentStoreMixin
from astrbot.core.db.stores.commands import CommandStoreMixin
from astrbot.core.db.stores.conversations import ConversationStoreMixin
from astrbot.core.db.stores.cron import CronStoreMixin
from astrbot.core.db.stores.knowledge_base import KnowledgeBaseTaskStoreMixin
from astrbot.core.db.stores.memory import MemoryStoreMixin
from astrbot.core.db.stores.message_history import MessageHistoryStoreMixin
from astrbot.core.db.stores.persona_runtime import PersonaRuntimeStoreMixin
from astrbot.core.db.stores.personas import PersonaStoreMixin
from astrbot.core.db.stores.preferences import PreferenceStoreMixin
from astrbot.core.db.stores.projects import ChatProjectStoreMixin
from astrbot.core.db.stores.session_bridge import SessionBridgeStoreMixin
from astrbot.core.db.stores.sessions import PlatformSessionStoreMixin
from astrbot.core.db.stores.statistics import StatisticsStoreMixin
from astrbot.core.db.stores.webchat import WebChatThreadStoreMixin


class SQLiteDatabase(
    KnowledgeBaseTaskStoreMixin,
    StatisticsStoreMixin,
    PersonaRuntimeStoreMixin,
    MemoryStoreMixin,
    ConversationStoreMixin,
    MessageHistoryStoreMixin,
    WebChatThreadStoreMixin,
    AttachmentStoreMixin,
    ApiKeyStoreMixin,
    PersonaStoreMixin,
    PreferenceStoreMixin,
    CommandStoreMixin,
    CronStoreMixin,
    PlatformSessionStoreMixin,
    SessionBridgeStoreMixin,
    UmoAliasStoreMixin,
    ChatProjectStoreMixin,
):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
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

    async def initialize(self) -> None:
        """Initialize the database by creating tables if they do not exist."""
        async with self._init_lock:
            if self.inited:
                return
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
