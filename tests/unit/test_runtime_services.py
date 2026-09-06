"""Tests for explicit runtime-service construction."""

import asyncio
import dataclasses
import os
import subprocess
import sys
import types
import typing
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.runtime_services as runtime_services
from astrbot.core.db.sqlite import SQLiteDatabase

REPO_ROOT = Path(__file__).resolve().parents[2]


def _annotation_type_name(annotation: object) -> str:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        if len(args) != 1:
            raise AssertionError(f"unsupported union annotation: {annotation!r}")
        annotation = args[0]
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str):
        raise AssertionError(f"unsupported annotation: {annotation!r}")
    return name


def _runtime_service_doc_tokens() -> list[str]:
    tokens: list[str] = []
    for field in dataclasses.fields(runtime_services.RuntimeServices):
        if field.name == "demo_mode":
            tokens.append("demo")
            continue
        tokens.append(_annotation_type_name(field.type))
    return tokens


def _section_after_heading(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.find(marker)
    assert start != -1, heading
    rest = markdown[start + len(marker) :]
    next_heading = rest.find("\n## ")
    if next_heading == -1:
        return rest
    return rest[:next_heading]


@pytest.mark.asyncio
async def test_factory_does_not_start_preferences_before_other_resources(
    monkeypatch, tmp_path
):
    """A failed factory call must not leak SharedPreferences' scheduler."""

    config = MagicMock()
    config.get.return_value = ""
    preferences_factory = MagicMock()
    db_instance = MagicMock()
    db_instance.close = AsyncMock()
    db_factory = MagicMock(return_value=db_instance)

    class BrokenToolImageCache:
        CACHE_DIR_NAME = "tool_images"

        def __init__(self, _cache_dir) -> None:
            raise OSError("cache directory is unavailable")

    monkeypatch.setattr(runtime_services, "AstrBotConfig", lambda: config)
    monkeypatch.setattr(runtime_services, "SQLiteDatabase", db_factory)
    monkeypatch.setattr(
        runtime_services.LogManager,
        "GetLogger",
        MagicMock(),
    )
    monkeypatch.setattr(
        runtime_services.LogManager,
        "configure_logger",
        MagicMock(),
    )
    monkeypatch.setattr(
        runtime_services.LogManager,
        "configure_trace_logger",
        MagicMock(),
    )
    monkeypatch.setattr(runtime_services, "ToolImageCache", BrokenToolImageCache)
    monkeypatch.setattr(runtime_services, "SharedPreferences", preferences_factory)
    monkeypatch.setattr(
        runtime_services, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    with pytest.raises(OSError, match="cache directory is unavailable"):
        await runtime_services.create_runtime_services()

    preferences_factory.assert_not_called()
    db_instance.close.assert_awaited()


class _CapturingSQLiteDatabase(SQLiteDatabase):
    """Real SQLiteDatabase that records close() and pool replacement after dispose."""

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.close_called = False
        self.pool_at_init = self.engine.sync_engine.pool

    async def close(self) -> None:
        self.close_called = True
        await super().close()


@pytest.mark.asyncio
async def test_factory_disposes_sqlite_engine_when_tool_image_cache_fails(
    monkeypatch, tmp_path
):
    """A failed factory must dispose a real SQLite engine, not a mocked stand-in."""
    captured: dict[str, _CapturingSQLiteDatabase] = {}
    config = MagicMock()
    config.get.return_value = ""
    preferences_factory = MagicMock()

    class CapturingSQLiteDatabase(_CapturingSQLiteDatabase):
        def __init__(self, db_path: str) -> None:
            super().__init__(db_path)
            captured["db"] = self

    class BrokenToolImageCache:
        CACHE_DIR_NAME = "tool_images"

        def __init__(self, _cache_dir) -> None:
            raise OSError("cache directory is unavailable")

    monkeypatch.setattr(runtime_services, "AstrBotConfig", lambda: config)
    monkeypatch.setattr(runtime_services, "SQLiteDatabase", CapturingSQLiteDatabase)
    monkeypatch.setattr(runtime_services, "DB_PATH", str(tmp_path / "data_v4.db"))
    monkeypatch.setattr(runtime_services.LogManager, "GetLogger", MagicMock())
    monkeypatch.setattr(runtime_services.LogManager, "configure_logger", MagicMock())
    monkeypatch.setattr(
        runtime_services.LogManager,
        "configure_trace_logger",
        MagicMock(),
    )
    monkeypatch.setattr(runtime_services, "ToolImageCache", BrokenToolImageCache)
    monkeypatch.setattr(runtime_services, "SharedPreferences", preferences_factory)
    monkeypatch.setattr(
        runtime_services, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    with pytest.raises(OSError, match="cache directory is unavailable"):
        await runtime_services.create_runtime_services()

    preferences_factory.assert_not_called()
    db = captured["db"]
    assert db.close_called
    assert db.engine.sync_engine.pool is not db.pool_at_init


@pytest.mark.asyncio
async def test_factory_disposes_sqlite_engine_on_cancelled_error(monkeypatch, tmp_path):
    """Factory cleanup must still run when construction is cancelled."""
    captured: dict[str, _CapturingSQLiteDatabase] = {}
    config = MagicMock()
    config.get.return_value = ""

    class CapturingSQLiteDatabase(_CapturingSQLiteDatabase):
        def __init__(self, db_path: str) -> None:
            super().__init__(db_path)
            captured["db"] = self

    class CancelledToolImageCache:
        CACHE_DIR_NAME = "tool_images"

        def __init__(self, _cache_dir) -> None:
            raise asyncio.CancelledError

    monkeypatch.setattr(runtime_services, "AstrBotConfig", lambda: config)
    monkeypatch.setattr(runtime_services, "SQLiteDatabase", CapturingSQLiteDatabase)
    monkeypatch.setattr(runtime_services, "DB_PATH", str(tmp_path / "data_v4.db"))
    monkeypatch.setattr(runtime_services.LogManager, "GetLogger", MagicMock())
    monkeypatch.setattr(runtime_services.LogManager, "configure_logger", MagicMock())
    monkeypatch.setattr(
        runtime_services.LogManager,
        "configure_trace_logger",
        MagicMock(),
    )
    monkeypatch.setattr(runtime_services, "ToolImageCache", CancelledToolImageCache)
    monkeypatch.setattr(runtime_services, "SharedPreferences", MagicMock())
    monkeypatch.setattr(
        runtime_services, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    with pytest.raises(asyncio.CancelledError):
        await runtime_services.create_runtime_services()

    db = captured["db"]
    assert db.close_called
    assert db.engine.sync_engine.pool is not db.pool_at_init


def test_factory_initializes_astrbot_logger(tmp_path: Path) -> None:
    """The factory routes normal AstrBot logs to the process console."""
    root = tmp_path / "runtime-root"
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(root),
    }
    code = """
from astrbot import logger

import astrbot.core.runtime_services as runtime_services


class StopAfterLoggerSetup:
    CACHE_DIR_NAME = "tool_images"

    def __init__(self, _cache_dir) -> None:
        raise RuntimeError("stop after logger setup")


runtime_services.AstrBotConfig = lambda: {
    "log_level": "INFO",
    "log_file_enable": False,
    "trace_log_enable": False,
}
runtime_services.SQLiteDatabase = lambda _path: object()
runtime_services.WebChatQueueManager = lambda: object()
runtime_services.ComputerRuntime = lambda: object()
runtime_services.ToolImageCache = StopAfterLoggerSetup

import asyncio

try:
    asyncio.run(runtime_services.create_runtime_services())
except RuntimeError as exc:
    assert str(exc) == "stop after logger setup"
else:
    raise AssertionError("factory unexpectedly completed")

logger.info("runtime-service-log-is-visible")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "runtime-service-log-is-visible" in result.stdout


def test_architecture_docs_list_runtime_service_types() -> None:
    """Bilingual ownership lists must name every RuntimeServices slot type."""
    tokens = _runtime_service_doc_tokens()
    pages = (
        ("zh", REPO_ROOT / "docs" / "zh" / "dev" / "architecture.md", "运行时所有权"),
        (
            "en",
            REPO_ROOT / "docs" / "en" / "dev" / "architecture.md",
            "Runtime Ownership",
        ),
    )
    for language, path, heading in pages:
        section = _section_after_heading(path.read_text(encoding="utf-8"), heading)
        missing = [token for token in tokens if token not in section]
        assert missing == [], (
            f"{language} architecture ownership list missing {missing}"
        )
