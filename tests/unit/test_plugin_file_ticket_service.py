import hashlib
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from astrbot.core.star.dashboard_extension import (
    DashboardExtensionRegistry,
    DashboardFile,
    DashboardFileAction,
    DashboardJsonAction,
    validate_dashboard_manifest,
)
from astrbot.core.star.star import StarMetadata
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.auth_service import DashboardSessionPrincipal
from astrbot.dashboard.services.plugin_file_ticket_service import (
    PluginFileTicketService,
    RawFileError,
    content_disposition_header,
    sanitize_download_filename,
)


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Result(BaseModel):
    ok: bool


async def _handler(_payload, _context):
    return Result(ok=True)


async def _snapshot(tmp_path: Path):
    module = tmp_path / "pages/settings/app.js"
    module.parent.mkdir(parents=True)
    module.write_text("export default 1;", encoding="utf-8")
    manifest_path = tmp_path / "pages/settings/assets.v1.json"
    content = module.read_bytes()
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "files": [
                    {
                        "path": "pages/settings/app.js",
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size": len(content),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = validate_dashboard_manifest(
        {
            "name": "astrbot_plugin_palette",
            "requires": {"dashboard_extension": 1},
            "dashboard": {
                "extension_id": "io.github.example.palette",
                "pages": [
                    {
                        "id": "settings",
                        "title": "Settings",
                        "module": "pages/settings/app.js",
                        "assets_manifest": "pages/settings/assets.v1.json",
                        "actions": ["config.read"],
                    }
                ],
            },
        },
        tmp_path,
    )
    owner = object()
    metadata = StarMetadata(
        name="astrbot_plugin_palette",
        root_dir_name="astrbot_plugin_palette",
        star_cls=owner,  # type: ignore[arg-type]
        dashboard=manifest,
        dashboard_root=tmp_path.resolve(),
    )
    registry = DashboardExtensionRegistry()
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registry.registrar_for(owner).register_json(  # type: ignore[arg-type]
        DashboardJsonAction(
            name="config.read",
            input_model=EmptyRequest,
            output_model=Result,
        ),
        _handler,
    )
    snapshot = await registry.commit_registration(owner)  # type: ignore[arg-type]
    assert snapshot is not None
    return registry, metadata, snapshot


def _principal() -> DashboardSessionPrincipal:
    return DashboardSessionPrincipal(username="astrbot", sid="sid-one", jti="jti")


@pytest.mark.asyncio
async def test_attachment_ticket_is_handle_cookie_bound_and_single_use(tmp_path: Path):
    registry, _metadata, snapshot = await _snapshot(tmp_path)
    output = tmp_path / "output.bin"
    output.write_bytes(b"download")
    service = PluginFileTicketService(registry, "file-ticket-test-secret")
    action = DashboardFileAction(
        name="file.download",
        input_model=EmptyRequest,
        disposition="attachment",
        allowed_content_types=frozenset({"application/octet-stream"}),
    )
    created = await service.create_ticket(
        snapshot,
        action.name,
        action,
        DashboardFile(Path("output.bin"), filename="report.bin"),
        _principal(),
    )
    handle = str(created.data["ticket_url"]).rsplit("/", 1)[1]

    with pytest.raises(RawFileError) as missing:
        await service.redeem(handle, None)
    assert missing.value.status_code == 401
    with pytest.raises(RawFileError) as mismatch:
        await service.redeem(handle, "wrong")
    assert mismatch.value.status_code == 404

    redeemed = await service.redeem(handle, created.cookie_secret)
    assert redeemed.path == output.resolve()
    assert redeemed.file_handle.read() == b"download"
    redeemed.file_handle.close()
    assert redeemed.clear_cookie is True
    with pytest.raises(RawFileError) as replay:
        await service.redeem(handle, created.cookie_secret)
    assert replay.value.status_code == 404
    await service.shutdown()


@pytest.mark.asyncio
async def test_inline_ticket_allows_three_reads_then_expires(tmp_path: Path):
    registry, _metadata, snapshot = await _snapshot(tmp_path)
    (tmp_path / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\npreview")
    service = PluginFileTicketService(registry, "file-ticket-test-secret")
    action = DashboardFileAction(
        name="file.preview",
        input_model=EmptyRequest,
        disposition="inline",
        allowed_content_types=frozenset({"image/png"}),
    )
    created = await service.create_ticket(
        snapshot,
        action.name,
        action,
        DashboardFile(Path("preview.png")),
        _principal(),
    )
    handle = str(created.data["ticket_url"]).rsplit("/", 1)[1]
    for _index in range(3):
        redeemed = await service.redeem(handle, created.cookie_secret)
        assert redeemed.file_handle.read() == b"\x89PNG\r\n\x1a\npreview"
        redeemed.file_handle.close()
        assert redeemed.clear_cookie is False
    with pytest.raises(RawFileError):
        await service.redeem(handle, created.cookie_secret)
    await service.shutdown()


@pytest.mark.asyncio
async def test_ticket_rechecks_limits_media_and_file_state(tmp_path: Path):
    registry, _metadata, snapshot = await _snapshot(tmp_path)
    (tmp_path / "output.txt").write_text("too large", encoding="utf-8")
    service = PluginFileTicketService(registry, "file-ticket-test-secret")
    too_small = DashboardFileAction(
        name="file.small",
        input_model=EmptyRequest,
        max_file_bytes=1,
        allowed_content_types=frozenset({"text/plain"}),
    )
    with pytest.raises(ApiError) as size_error:
        await service.create_ticket(
            snapshot,
            too_small.name,
            too_small,
            DashboardFile(Path("output.txt")),
            _principal(),
        )
    assert size_error.value.status_code == 413

    wrong_media = DashboardFileAction(
        name="file.media",
        input_model=EmptyRequest,
        allowed_content_types=frozenset({"image/png"}),
    )
    with pytest.raises(ApiError) as media_error:
        await service.create_ticket(
            snapshot,
            wrong_media.name,
            wrong_media,
            DashboardFile(Path("output.txt")),
            _principal(),
        )
    assert media_error.value.status_code == 415
    await service.shutdown()


@pytest.mark.asyncio
async def test_ticket_revoked_by_logout_and_registry_transition(tmp_path: Path):
    registry, metadata, snapshot = await _snapshot(tmp_path)
    (tmp_path / "output.bin").write_bytes(b"data")
    service = PluginFileTicketService(registry, "file-ticket-test-secret")
    action = DashboardFileAction(
        name="file.read",
        input_model=EmptyRequest,
        allowed_content_types=frozenset({"application/octet-stream"}),
    )
    first = await service.create_ticket(
        snapshot,
        action.name,
        action,
        DashboardFile(Path("output.bin")),
        _principal(),
    )
    await service.revoke_by_auth_session_id("sid-one")
    with pytest.raises(RawFileError):
        await service.redeem(
            str(first.data["ticket_url"]).rsplit("/", 1)[1],
            first.cookie_secret,
        )
    second = await service.create_ticket(
        snapshot,
        action.name,
        action,
        DashboardFile(Path("output.bin")),
        _principal(),
    )
    await registry.deactivate(metadata, reason="disable")
    with pytest.raises(RawFileError):
        await service.redeem(
            str(second.data["ticket_url"]).rsplit("/", 1)[1],
            second.cookie_secret,
        )
    await service.shutdown()


def test_content_disposition_sanitizes_header_injection():
    assert sanitize_download_filename('../bad\r\n".txt') == '_bad_".txt'
    header = content_disposition_header("attachment", '../bad\r\n".txt')
    assert "\r" not in header and "\n" not in header
    assert "filename*=UTF-8''" in header


@pytest.mark.asyncio
async def test_inline_document_is_forced_to_attachment(tmp_path: Path):
    registry, _metadata, snapshot = await _snapshot(tmp_path)
    (tmp_path / "page.html").write_text("<h1>preview</h1>", encoding="utf-8")
    service = PluginFileTicketService(registry, "file-ticket-test-secret")
    action = DashboardFileAction(
        name="file.preview",
        input_model=EmptyRequest,
        disposition="inline",
        allowed_content_types=frozenset({"text/html"}),
    )
    created = await service.create_ticket(
        snapshot,
        action.name,
        action,
        DashboardFile(Path("page.html")),
        _principal(),
    )

    assert created.data["disposition"] == "attachment"
    handle = str(created.data["ticket_url"]).rsplit("/", 1)[1]
    redeemed = await service.redeem(handle, created.cookie_secret)
    assert redeemed.disposition == "attachment"
    redeemed.file_handle.close()
    await service.shutdown()
