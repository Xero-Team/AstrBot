import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.dashboard.services.backup_service import (
    BackupService,
    BackupServiceError,
)


def _make_service(tmp_path: Path) -> BackupService:
    service = BackupService.__new__(BackupService)
    service.db = MagicMock()
    service.core_lifecycle = SimpleNamespace(kb_manager=None)
    service.config = {}
    service.backup_dir = str(tmp_path)
    service.data_dir = str(tmp_path)
    service.chunks_dir = str(tmp_path / ".chunks")
    service.backup_tasks = {}
    service.backup_progress = {}
    service.chunked_uploads = SimpleNamespace(
        ensure_cleanup_task_started=lambda: None,
    )
    service._background_tasks = set()
    service._active_data_task = None
    service._active_import_path = None
    return service


def test_export_backup_schedules_tracked_task(monkeypatch, tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    scheduled_tasks: list[asyncio.Task] = []
    scheduled_calls: list[str] = []

    async def fake_background_export_task(task_id: str) -> None:
        scheduled_calls.append(task_id)

    def fake_create_tracked_task(task_set, coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        task_set.add(task)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(service, "background_export_task", fake_background_export_task)
    monkeypatch.setattr(
        "astrbot.dashboard.services.backup_service.create_tracked_task",
        fake_create_tracked_task,
    )

    async def _run():
        result = service.export_backup()
        await asyncio.gather(*scheduled_tasks)
        return result

    result = asyncio.run(_run())

    assert result["task_id"] in service.backup_tasks
    assert service.backup_tasks[result["task_id"]]["status"] == "pending"
    assert scheduled_calls == [result["task_id"]]


def test_import_backup_schedules_tracked_task(monkeypatch, tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    scheduled_tasks: list[asyncio.Task] = []
    scheduled_calls: list[tuple[str, str]] = []
    backup_path = tmp_path / "demo.zip"
    backup_path.write_bytes(b"zip")

    async def fake_background_import_task(task_id: str, zip_path: str) -> None:
        scheduled_calls.append((task_id, zip_path))

    def fake_create_tracked_task(task_set, coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        task_set.add(task)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(service, "background_import_task", fake_background_import_task)
    monkeypatch.setattr(
        "astrbot.dashboard.services.backup_service.create_tracked_task",
        fake_create_tracked_task,
    )

    async def _run():
        result = service.import_backup({"filename": "demo.zip", "confirmed": True})
        await asyncio.gather(*scheduled_tasks)
        return result

    result = asyncio.run(_run())

    assert result["task_id"] in service.backup_tasks
    assert service.backup_tasks[result["task_id"]]["status"] == "pending"
    assert scheduled_calls == [(result["task_id"], str(backup_path))]


def test_delete_missing_backup_while_another_import_is_active(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    service._active_import_path = str(tmp_path / "active.zip")

    with pytest.raises(BackupServiceError, match="备份文件不存在"):
        service.delete_backup({"filename": "missing.zip"})


def test_active_import_backup_cannot_be_deleted_or_renamed(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    active_path = tmp_path / "active.zip"
    active_path.write_bytes(b"zip")
    service._active_import_path = str(active_path)

    with pytest.raises(BackupServiceError, match="正在导入"):
        service.delete_backup({"filename": "active.zip"})
    with pytest.raises(BackupServiceError, match="正在导入"):
        service.rename_backup({"filename": "active.zip", "new_name": "renamed.zip"})


def test_stale_active_import_path_does_not_block_other_backups(
    tmp_path: Path,
) -> None:
    service = _make_service(tmp_path)
    other_path = tmp_path / "other.zip"
    other_path.write_bytes(b"zip")
    service._active_import_path = str(tmp_path / "gone.zip")

    assert service.delete_backup({"filename": "other.zip"}) == (
        None,
        "删除备份成功",
    )

    other_path.write_bytes(b"zip")
    result = service.rename_backup({"filename": "other.zip", "new_name": "renamed.zip"})
    assert result == {"old_filename": "other.zip", "new_filename": "renamed.zip"}


def test_backup_mutations_reject_non_zip_names_and_chunk_directory(
    tmp_path: Path,
) -> None:
    service = _make_service(tmp_path)
    (tmp_path / ".chunks").mkdir()

    for filename in (".chunks", "C:foo.zip", "..", "nested/../../x.zip"):
        with pytest.raises(BackupServiceError):
            service.delete_backup({"filename": filename})
        with pytest.raises(BackupServiceError):
            service.prepare_download(filename=filename)

    assert (tmp_path / ".chunks").is_dir()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs extra privileges")
def test_backup_download_rejects_symlink_escape(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    outside = tmp_path.parent / "outside.zip"
    outside.write_bytes(b"zip")
    (tmp_path / "link.zip").symlink_to(outside)

    with pytest.raises(BackupServiceError):
        service.prepare_download(filename="link.zip")


def test_backup_task_history_is_bounded(tmp_path: Path) -> None:
    service = _make_service(tmp_path)

    for index in range(200):
        service._init_task(f"task-{index}", "export", status="completed")

    assert len(service.backup_tasks) == 128
    assert len(service.backup_progress) == 128
    assert "task-0" not in service.backup_tasks
    assert "task-199" in service.backup_tasks
