import asyncio
import logging
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.backup._importer_files import (
    extract_directory_files,
    import_attachments,
)
from astrbot.core.backup._importer_kb import import_kb_metadata_tables
from astrbot.core.backup.constants import KB_METADATA_MODELS
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import (
    AstrBotImporter,
    DatabaseClearError,
    ImportResult,
)
from astrbot.core.config.default import VERSION
from astrbot.dashboard.api import backups as backups_api
from astrbot.dashboard.services.backup_service import BackupService

_SENSITIVE_ERROR = (
    "api_key=api-key-top-secret "
    "Bearer bearer-secret-token "
    "password=dashboard-password "
    "https://internal.example/private/config "
    "C:\\private\\config\\secret.txt "
    "/srv/astrbot/private/config.json"
)
_SENSITIVE_VALUES = (
    "api-key-top-secret",
    "bearer-secret-token",
    "dashboard-password",
    "https://internal.example/private/config",
    "C:\\private\\config\\secret.txt",
    "/srv/astrbot/private/config.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        rendered = str(text)
        for value in _SENSITIVE_VALUES:
            assert value not in rendered


def _backup_service(tmp_path: Path) -> BackupService:
    service = BackupService.__new__(BackupService)
    service.db = MagicMock()
    service.knowledge_base_manager = None
    service.data_dir = str(tmp_path)
    service.backup_dir = str(tmp_path)
    return service


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


def test_import_result_redacts_untrusted_messages_before_storing_or_logging(
    caplog,
) -> None:
    result = ImportResult()

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        result.add_warning(_SENSITIVE_ERROR)
        result.add_error(_SENSITIVE_ERROR)

    _assert_no_sensitive_values(result.warnings, result.errors, caplog.text)


def test_importer_stage_failure_uses_generic_warning_and_redacted_log(caplog) -> None:
    importer = AstrBotImporter(main_db=MagicMock())
    archive = MagicMock()
    archive.namelist.return_value = ["config/cmd_config.json"]
    archive.read.side_effect = RuntimeError(_SENSITIVE_ERROR)
    result = ImportResult()

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        importer._import_config_stage(archive, result)

    assert result.warnings == ["导入配置文件失败"]
    _assert_no_sensitive_values(result.to_dict(), caplog.text)


def test_attachment_import_helper_redacts_unknown_failure(
    caplog, tmp_path: Path
) -> None:
    archive = MagicMock()
    archive.namelist.return_value = ["files/attachments/attachment.bin"]
    archive.open.side_effect = RuntimeError(_SENSITIVE_ERROR)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        assert import_attachments(archive, [], str(tmp_path / "cmd_config.json")) == 0

    _assert_no_sensitive_values(caplog.text)


def test_directory_file_import_helper_hides_unknown_failure(
    caplog, tmp_path: Path
) -> None:
    archive = MagicMock()
    archive.getinfo.return_value.is_dir.return_value = False
    archive.open.side_effect = RuntimeError(_SENSITIVE_ERROR)
    warnings: list[str] = []

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        assert (
            extract_directory_files(
                archive,
                ["directories/plugins/plugin.py"],
                "directories/plugins/",
                tmp_path,
                warnings.append,
            )
            == 0
        )

    assert warnings == ["导入文件失败"]
    _assert_no_sensitive_values(warnings, caplog.text)


@pytest.mark.asyncio
async def test_kb_metadata_import_helper_redacts_unknown_failure(caplog) -> None:
    table_name = next(iter(KB_METADATA_MODELS))
    session = MagicMock()
    session.begin.return_value = _AsyncContext(None)
    kb_manager = SimpleNamespace(
        kb_db=SimpleNamespace(get_db=lambda: _AsyncContext(session)),
    )

    def fail_to_convert(*_args: object) -> dict:
        raise RuntimeError(_SENSITIVE_ERROR)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await import_kb_metadata_tables(
            kb_manager,
            {table_name: [{}]},
            {},
            fail_to_convert,
        )

    _assert_no_sensitive_values(caplog.text)


def test_platform_stats_warning_hides_untrusted_backup_values(caplog) -> None:
    importer = AstrBotImporter(main_db=MagicMock())
    rows = [
        {
            "timestamp": "2025-01-01T00:00:00+00:00",
            "platform_id": "api_key=api-key-top-secret",
            "platform_type": "https://internal.example/private/config",
            "count": _SENSITIVE_ERROR,
        }
    ]

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        importer._merge_platform_stats_rows(rows)

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_backup_precheck_unknown_failure_is_generic_through_service_and_api(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    """A failed pre-check is normal data, but its internal cause is not."""
    backup_path = tmp_path / "backup.zip"
    backup_path.write_bytes(b"placeholder")
    service = _backup_service(tmp_path)

    def fail_to_open_backup(*_args, **_kwargs):
        raise RuntimeError(_SENSITIVE_ERROR)

    monkeypatch.setattr(
        "astrbot.core.backup.importer.zipfile.ZipFile",
        fail_to_open_backup,
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        service_result = service.check_backup({"filename": backup_path.name})
        api_result = await backups_api.check_backup(
            filename=backup_path.name,
            _auth=object(),
            service=service,
        )

    assert service_result["error"] == "Backup pre-check failed"
    assert api_result == {
        "status": "ok",
        "message": None,
        "data": service_result,
    }
    _assert_no_sensitive_values(service_result, api_result, caplog.text)


@pytest.mark.asyncio
async def test_backup_precheck_known_invalid_zip_error_remains_specific(
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "invalid.zip"
    backup_path.write_bytes(b"not a ZIP archive")
    service = _backup_service(tmp_path)

    response = await backups_api.check_backup(
        filename=backup_path.name,
        _auth=object(),
        service=service,
    )

    assert response["status"] == "ok"
    assert response["data"]["error"] == "无效的 ZIP 文件"


@pytest.mark.asyncio
async def test_importer_unknown_exception_is_generic_and_log_is_redacted(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    backup_path = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup_path, "w"):
        pass
    importer = AstrBotImporter(main_db=MagicMock())
    monkeypatch.setattr(
        importer,
        "_prepare_manifest_for_import",
        MagicMock(side_effect=RuntimeError(_SENSITIVE_ERROR)),
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        result = await importer.import_all(str(backup_path))

    assert result.errors == ["Backup import failed"]
    _assert_no_sensitive_values(result.to_dict(), caplog.text)


@pytest.mark.asyncio
async def test_importer_database_clear_failure_hides_internal_cause(
    tmp_path: Path,
    caplog,
) -> None:
    backup_path = tmp_path / "backup.zip"
    with zipfile.ZipFile(backup_path, "w") as archive:
        archive.writestr("manifest.json", f'{{"astrbot_version": "{VERSION}"}}')
        archive.writestr("databases/main_db.json", "{}")
    importer = AstrBotImporter(main_db=MagicMock())
    importer._clear_main_db = AsyncMock(
        side_effect=DatabaseClearError(_SENSITIVE_ERROR)
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        result = await importer.import_all(str(backup_path), mode="replace")

    assert result.errors == ["清空主数据库失败"]
    _assert_no_sensitive_values(result.to_dict(), caplog.text)


@pytest.mark.asyncio
async def test_exporter_unknown_exception_log_is_redacted(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    exporter = AstrBotExporter(main_db=MagicMock())
    monkeypatch.setattr(
        exporter,
        "_export_main_database_stage",
        AsyncMock(side_effect=RuntimeError(_SENSITIVE_ERROR)),
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError):
            await exporter.export_all(output_dir=str(tmp_path))

    _assert_no_sensitive_values(caplog.text)
    assert not list(tmp_path.glob("astrbot_backup_*.zip"))


@pytest.mark.asyncio
async def test_exporter_best_effort_failure_log_is_redacted(
    monkeypatch, caplog
) -> None:
    exporter = AstrBotExporter(main_db=MagicMock())
    archive = MagicMock()
    archive.write.side_effect = RuntimeError(_SENSITIVE_ERROR)
    monkeypatch.setattr(
        "astrbot.core.backup.exporter.os.path.exists",
        lambda _path: True,
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await exporter._export_attachments(
            archive,
            [{"path": "attachment.txt", "attachment_id": "attachment"}],
        )

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_exporter_cancellation_cleans_partial_archive(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exporter = AstrBotExporter(main_db=MagicMock())
    monkeypatch.setattr(
        exporter,
        "_export_main_database_stage",
        AsyncMock(side_effect=asyncio.CancelledError),
    )

    with pytest.raises(asyncio.CancelledError):
        await exporter.export_all(output_dir=str(tmp_path))

    assert not list(tmp_path.glob("astrbot_backup_*.zip"))
