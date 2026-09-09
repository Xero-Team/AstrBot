from pathlib import Path

from sqlalchemy.pool import NullPool

from astrbot.core.db import create_sqlite_async_engine, sqlite_async_url
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase


def test_sqlite_async_url_uses_forward_slashes() -> None:
    assert sqlite_async_url(r"C:\Temp\test_api_key.db") == (
        "sqlite+aiosqlite:///C:/Temp/test_api_key.db"
    )
    assert sqlite_async_url("/tmp/test.db") == "sqlite+aiosqlite:////tmp/test.db"


def test_sqlite_async_engine_uses_null_pool(tmp_path: Path) -> None:
    engine = create_sqlite_async_engine(str(tmp_path / "engine.db"))
    try:
        assert isinstance(engine.sync_engine.pool, NullPool)
    finally:
        engine.sync_engine.dispose()


def test_sqlite_database_uses_posix_url_and_null_pool(tmp_path: Path) -> None:
    db_path = tmp_path / "main.db"
    db = SQLiteDatabase(str(db_path))
    assert "\\" not in db.DATABASE_URL
    assert isinstance(db.engine.sync_engine.pool, NullPool)


def test_kb_sqlite_database_uses_posix_url_and_null_pool(tmp_path: Path) -> None:
    db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    assert "\\" not in db.DATABASE_URL
    assert isinstance(db.engine.sync_engine.pool, NullPool)


def test_document_storage_uses_posix_url(tmp_path: Path) -> None:
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    assert storage.DATABASE_URL == sqlite_async_url(str(tmp_path / "doc.db"))
    assert "\\" not in storage.DATABASE_URL
