from pathlib import Path

import pytest

from astrbot.core.utils.storage_cleaner import StorageCleaner


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_storage_cleaner_status_includes_logs_and_cache(tmp_path):
    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    logs_dir = data_dir / "logs"

    _write_bytes(temp_dir / "audio" / "temp.wav", 128)
    _write_bytes(data_dir / "plugins.json", 64)
    _write_bytes(data_dir / "sandbox_skills_cache.json", 32)
    _write_bytes(logs_dir / "astrbot.log", 256)
    _write_bytes(logs_dir / "astrbot.2026-03-22.log", 128)

    cleaner = StorageCleaner(
        {
            "log": {"file_enable": True, "file_path": "logs/astrbot.log"},
            "trace": {"log_enable": False},
        },
        data_dir=data_dir,
        temp_dir=temp_dir,
    )

    status = cleaner.get_status()

    assert status["logs"]["size_bytes"] == 384
    assert status["logs"]["file_count"] == 2
    assert status["cache"]["size_bytes"] == 224
    assert status["cache"]["file_count"] == 3
    assert status["total_bytes"] == 608


def test_storage_cleaner_cleanup_truncates_active_log_and_removes_cache(tmp_path):
    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    logs_dir = data_dir / "logs"
    active_log = logs_dir / "astrbot.log"
    rotated_log = logs_dir / "astrbot.2026-03-22.log"
    trace_log = logs_dir / "astrbot.trace.log"
    temp_file = temp_dir / "nested" / "voice.wav"
    registry_cache = data_dir / "plugins_custom_abc.json"

    _write_bytes(active_log, 300)
    _write_bytes(rotated_log, 150)
    _write_bytes(trace_log, 90)
    _write_bytes(temp_file, 120)
    _write_bytes(registry_cache, 80)

    cleaner = StorageCleaner(
        {
            "log": {"file_enable": True, "file_path": "logs/astrbot.log"},
        },
        data_dir=data_dir,
        temp_dir=temp_dir,
    )

    result = cleaner.cleanup("all")

    assert result["removed_bytes"] == 740
    assert result["processed_files"] == 5
    assert result["deleted_files"] == 4
    assert result["truncated_files"] == 1
    assert result["failed_files"] == 0
    assert active_log.exists()
    assert active_log.stat().st_size == 0
    assert not trace_log.exists()
    assert not rotated_log.exists()
    assert not temp_file.exists()
    assert not registry_cache.exists()
    assert temp_dir.exists()
    assert not (temp_dir / "nested").exists()
    assert result["status"]["logs"]["size_bytes"] == 0
    assert result["status"]["cache"]["size_bytes"] == 0


def test_storage_cleaner_protects_custom_database_under_symlinked_logs_root(tmp_path):
    data_dir = tmp_path / "data"
    mounted_logs = tmp_path / "mounted-logs"
    data_dir.mkdir()
    _write_bytes(mounted_logs / "astrbot.log", 64)
    custom_db = mounted_logs / "custom-trace-store"
    custom_db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 64)
    try:
        (data_dir / "logs").symlink_to(mounted_logs, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    cleaner = StorageCleaner(
        {"log": {"file_enable": True, "file_path": "logs/astrbot.log"}},
        data_dir=data_dir,
        temp_dir=data_dir / "temp",
    )

    collected = cleaner.collect_log_files()

    assert data_dir / "logs" / "astrbot.log" in collected
    assert all(path.name != "custom-trace-store" for path in collected)
    cleaner.cleanup("logs")
    assert custom_db.read_bytes().startswith(b"SQLite format 3\x00")


def test_storage_cleaner_does_not_truncate_symlinked_active_log(tmp_path):
    data_dir = tmp_path / "data"
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True)
    database = data_dir / "astrbot.db"
    database.write_bytes(b"SQLite format 3\x00database")
    active_log = logs_dir / "astrbot.log"
    try:
        active_log.symlink_to(database)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    cleaner = StorageCleaner(
        {"log": {"file_enable": True, "file_path": "logs/astrbot.log"}},
        data_dir=data_dir,
        temp_dir=data_dir / "temp",
    )

    cleaner.cleanup("logs")

    assert not active_log.exists()
    assert database.read_bytes().startswith(b"SQLite format 3\x00")
