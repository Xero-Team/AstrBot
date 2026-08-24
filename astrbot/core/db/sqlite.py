from astrbot.core.db import BaseDatabase
from astrbot.core.db.schema import initialize_sqlite_schema
from astrbot.core.db.stores.aliases import UmoAliasStoreMixin
from astrbot.core.db.stores.api_keys import ApiKeyStoreMixin
from astrbot.core.db.stores.attachments import AttachmentStoreMixin
from astrbot.core.db.stores.commands import CommandStoreMixin
from astrbot.core.db.stores.conversations import ConversationStoreMixin
from astrbot.core.db.stores.cron import CronStoreMixin
from astrbot.core.db.stores.memory import MemoryStoreMixin
from astrbot.core.db.stores.message_history import MessageHistoryStoreMixin
from astrbot.core.db.stores.persona_runtime import PersonaRuntimeStoreMixin
from astrbot.core.db.stores.personas import PersonaStoreMixin
from astrbot.core.db.stores.preferences import PreferenceStoreMixin
from astrbot.core.db.stores.projects import ChatProjectStoreMixin
from astrbot.core.db.stores.sessions import PlatformSessionStoreMixin
from astrbot.core.db.stores.statistics import StatisticsStoreMixin
from astrbot.core.db.stores.webchat import WebChatThreadStoreMixin


class SQLiteDatabase(
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
    UmoAliasStoreMixin,
    ChatProjectStoreMixin,
    BaseDatabase,
):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        super().__init__()

    async def initialize(self) -> None:
        """Initialize the database by creating tables if they do not exist."""
        async with self._init_lock:
            if self.inited:
                return
            await initialize_sqlite_schema(self.engine)
            self.inited = True
