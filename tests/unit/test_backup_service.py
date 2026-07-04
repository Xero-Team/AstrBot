import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from astrbot.dashboard.services.backup_service import BackupService


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
    service.upload_sessions = {}
    service._cleanup_task = None
    service._background_tasks = set()
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
