"""Diagnostic export route contract coverage."""

import asyncio
import io
import json
import os
import stat
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest

from astrbot.dashboard.api.app import create_dashboard_asgi_app
from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403
from tests.unit.dashboard.fastapi_v1_support import (
    DASHBOARD_JWT_COOKIE_NAME,
    JWT_SECRET,
    TEST_DASHBOARD_ACCOUNT_ID,
    _jwt_headers,
)


@pytest.mark.asyncio
async def test_v1_log_export_reports_blocked_console(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    """Export drop counters even while the console cannot write its warning."""
    from astrbot.core.log import LogManager
    from astrbot.core.utils.console_sink import BoundedConsoleSink

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    entered = threading.Event()
    release = threading.Event()

    class BlockedStream(io.StringIO):
        def write(self, text):
            entered.set()
            release.wait(10)
            return super().write(text)

    sink = BoundedConsoleSink(BlockedStream(), capacity=2)
    monkeypatch.setattr(LogManager, "_console_output", sink)
    try:
        sink.write("first\n")
        assert await asyncio.to_thread(entered.wait, 1)
        for index in range(3):
            sink.write(f"record {index}\n")
        response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
        assert response.status_code == 200
        assert not release.is_set()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            environment = json.loads(archive.read("environment.json"))
        assert environment["console_logging"] == {
            "capacity": 2,
            "queued_records": 2,
            "unfinished_records": 3,
            "dropped_records": 1,
            "closed": False,
            "writer_alive": True,
        }
    finally:
        release.set()
        await asyncio.to_thread(sink.close)


@pytest.mark.asyncio
async def test_v1_log_export_packs_log_files_and_memory_logs(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    """The archive covers data/logs, configured log files elsewhere and memory logs."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "event_loop_watchdog.log").write_text("watchdog", encoding="utf-8")
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    (external_dir / "custom.log").write_text("current", encoding="utf-8")
    (external_dir / "custom.1.log").write_text("rotated", encoding="utf-8")
    service = asgi_app.state.services.logs
    service.config["log"] = {
        "file_enable": True,
        "file_path": str(external_dir / "custom.log"),
    }
    service.log_broker.publish(
        {"level": "INFO", "time": 1.0, "data": "[INFO] hello", "category": "system"}
    )
    service.log_broker.publish(
        {
            "type": "trace",
            "level": "TRACE",
            "time": 2.0,
            "span_id": "span-1",
            "action": "start",
            "fields": {},
        }
    )

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "astrbot-diagnostics-" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [
            "config.json",
            "environment.json",
            "external/custom.1.log",
            "external/custom.log",
            "logs/astrbot.in-memory.log",
            "logs/event_loop_watchdog.log",
            "manifest.json",
            "plugins.json",
            "traces/history.in-memory.jsonl",
            "traces/history.jsonl",
        ]
        assert archive.read("external/custom.log") == b"current"
        assert archive.read("external/custom.1.log") == b"rotated"
        assert archive.read("logs/event_loop_watchdog.log") == b"watchdog"
        assert archive.read("logs/astrbot.in-memory.log").decode() == "[INFO] hello\n"
        traces = archive.read("traces/history.in-memory.jsonl").decode().splitlines()
        # Current LogBroker only retains ordinary logs; traces are persisted.
        assert traces == []
        manifest = json.loads(archive.read("manifest.json"))
    assert sorted(manifest["files"]) == [
        "external/custom.1.log",
        "external/custom.log",
        "logs/event_loop_watchdog.log",
    ]
    assert manifest["skipped"] == []
    assert (manifest["memory_logs"], manifest["memory_traces"]) == (1, 0)
    assert str(tmp_path) not in json.dumps(manifest)
    assert not any((tmp_path / "data" / "temp" / "log_exports").iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_diagnostic_export_time_range_filters_logs_and_persisted_traces(
    monkeypatch, tmp_path, asgi_app, asgi_client, redact
):
    from astrbot.core.utils.trace_store import TraceStore

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    service = asgi_app.state.services.logs
    base = int(time.time()) - 3600
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    selected = (
        f"[{datetime.fromtimestamp(base + 1).isoformat(sep=' ')}] token=private-range-value\n"
        "  selected traceback\n"
        f"[{datetime.fromtimestamp(base + 2).isoformat(sep=' ')}] last selected log\n"
    )
    (logs_dir / "astrbot.log").write_text(
        "undated preamble\n"
        f"[{datetime.fromtimestamp(base).isoformat(sep=' ')}] outside-before\n"
        + selected
        + f"[{datetime.fromtimestamp(base + 3).isoformat(sep=' ')}] outside-after\n"
        "  outside traceback\n",
        encoding="utf-8",
        newline="\n",
    )
    (logs_dir / "undated.log").write_text("unrelated undated log\n", encoding="utf-8")
    service.log_broker.publish({"time": base, "data": "outside-before"})
    service.log_broker.publish({"time": base + 1, "data": "selected memory log"})
    service.log_broker.publish({"time": base + 3, "data": "outside-after"})
    service.log_broker.log_cache.append(
        {"type": "trace", "time": base, "data": "outside"}
    )
    service.log_broker.log_cache.append(
        {"type": "trace", "time": base + 1, "data": "selected"}
    )
    path = logs_dir / "traces.db"
    service.config["trace"] = {"db_path": str(path)}
    store = TraceStore(path, {"trace_db_max_mb": 8})
    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.get_trace_store", lambda *_: store
    )
    try:
        for index in range(60):
            trace_id = f"{index + 1:032x}"
            stamp = str((base + index) * 1_000_000_000)
            summary = {
                "trace_id": trace_id,
                "root_span_id": "b" * 16,
                "start_time_unix_nano": stamp,
                "end_time_unix_nano": stamp,
                "updated_time_unix_nano": stamp,
                "state": "completed",
                "has_errors": False,
                "has_models": False,
                "has_plugins": False,
                "has_commands": False,
                "span_count": 0,
                "attributes": {},
            }
            assert store.append({"trace": summary, "time_unix_nano": stamp})
        assert store.flush()
        response = await asgi_client.get(
            "/api/v1/logs/export",
            headers=_jwt_headers(),
            params={
                "redact": str(redact).lower(),
                "start_time": base + 1,
                "end_time": base + 2,
            },
        )
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            disk_log = archive.read("logs/astrbot.log").decode()
            assert disk_log == (
                selected.replace("private-range-value", "[REDACTED]")
                if redact
                else selected
            )
            assert archive.read("logs/undated.log") == b""
            assert (
                archive.read("logs/astrbot.in-memory.log") == b"selected memory log\n"
            )
            assert (
                json.loads(archive.read("traces/history.in-memory.jsonl"))["data"]
                == "selected"
            )
            history = [
                json.loads(line)
                for line in archive.read("traces/history.jsonl").splitlines()
            ]
            assert [item["trace"]["trace_id"] for item in history] == [
                f"{3:032x}",
                f"{2:032x}",
            ]
            assert "config.json" in archive.namelist()
            assert "environment.json" in archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["time_range"]["start_time"] == base + 1
            assert manifest["time_range"]["end_time"] == base + 2
            assert manifest["memory_logs"] == 1
            assert manifest["memory_traces"] == 1
            assert manifest["trace_history"]["count"] == 2
            assert manifest["trace_history"]["truncated"] is False
        assert store.list_traces(start_time=base + 58)["total"] == 2
        assert store.list_traces(end_time=base + 2)["total"] == 3
    finally:
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"start_time": 20, "end_time": 10}, 400),
        ({"start_time": -1}, 422),
        ({"end_time": "invalid"}, 422),
    ],
)
async def test_diagnostic_export_rejects_invalid_time_ranges(
    asgi_client, params, status
):
    response = await asgi_client.get(
        "/api/v1/logs/export", headers=_jwt_headers(), params=params
    )
    assert response.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("webui_version", ["v9.8.7", None])
async def test_diagnostic_export_includes_active_webui_version(
    monkeypatch, tmp_path, fake_core_lifecycle, fake_db, webui_version
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    static_folder = tmp_path / "custom-webui"
    assets_folder = static_folder / "assets"
    assets_folder.mkdir(parents=True)
    if webui_version is not None:
        (assets_folder / "version").write_text(webui_version, encoding="utf-8")
    default_assets = tmp_path / "data" / "dist" / "assets"
    default_assets.mkdir(parents=True)
    (default_assets / "version").write_text("v0.0.1", encoding="utf-8")
    app = create_dashboard_asgi_app(
        runtime=fake_core_lifecycle,
        core_control=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
        static_folder=str(static_folder),
    )

    async def validate_dashboard_principal(principal) -> bool:
        return principal.account_id == TEST_DASHBOARD_ACCOUNT_ID

    app.state.services.auth.validate_dashboard_principal = validate_dashboard_principal
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        environment = json.loads(archive.read("environment.json"))
    assert environment["webui_version"] == webui_version


@pytest.mark.asyncio
async def test_v1_log_export_skips_files_that_are_not_regular(
    monkeypatch, tmp_path: Path, asgi_client: httpx.AsyncClient
):
    """A symlink in the log directory must not pull in a file from elsewhere."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "astrbot.log").write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("not a log", encoding="utf-8")
    link = logs_dir / "link.log"
    try:
        link.symlink_to(outside)
    except OSError:
        # No symlink privilege (e.g. Windows without developer mode): report a
        # regular file as a symlink instead, which takes the same code path.
        link.write_text("not a log", encoding="utf-8")
        real_lstat = Path.lstat

        def fake_lstat(self, *args, **kwargs):
            if self.name == "link.log":
                return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            return real_lstat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", fake_lstat)

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "logs/link.log" not in archive.namelist()
        assert archive.read("logs/astrbot.log") == b"ok"
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["skipped"] == [
        {"name": "logs/link.log", "reason": "not a regular file"}
    ]


@pytest.mark.asyncio
async def test_v1_log_export_reads_logs_under_a_symlinked_log_root(
    monkeypatch, tmp_path: Path, asgi_client: httpx.AsyncClient
):
    """A mounted log root stays exportable; only the file itself must not be a link."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    mounted_logs = tmp_path / "mounted-logs"
    mounted_logs.mkdir()
    (mounted_logs / "astrbot.log").write_text("mounted", encoding="utf-8")
    (tmp_path / "data").mkdir()
    try:
        (tmp_path / "data" / "logs").symlink_to(mounted_logs, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("logs/astrbot.log") == b"mounted"
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["files"] == ["logs/astrbot.log"]
    assert manifest["skipped"] == []


@pytest.mark.asyncio
async def test_v1_log_export_keeps_archive_names_unique(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    """Log files never take the names of the generated entries."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    data_dir = tmp_path / "data"
    (data_dir / "logs").mkdir(parents=True)
    (data_dir / "traces").mkdir()
    (data_dir / "logs" / "astrbot.in-memory.log").write_text(
        "file log", encoding="utf-8"
    )
    (data_dir / "traces" / "history.in-memory.jsonl").write_text(
        "file trace", encoding="utf-8"
    )
    service = asgi_app.state.services.logs
    service.config["log"] = {"file_path": "traces/history.in-memory.jsonl"}
    service.config["trace"] = {"db_path": "traces/missing.db"}

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert archive.read("logs/2/astrbot.in-memory.log") == b"file log"
        assert archive.read("traces/2/history.in-memory.jsonl") == b"file trace"
        manifest = json.loads(archive.read("manifest.json"))
    assert sorted(manifest["files"]) == [
        "logs/2/astrbot.in-memory.log",
        "traces/2/history.in-memory.jsonl",
    ]


@pytest.mark.asyncio
async def test_v1_log_export_refuses_when_disk_space_is_short(
    monkeypatch, tmp_path: Path, asgi_client: httpx.AsyncClient
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    logs_dir = tmp_path / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "astrbot.log").write_text("x" * 1024, encoding="utf-8")
    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=2048, used=2048, free=0),
    )

    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())

    assert response.status_code == 400
    assert "disk space" in response.json()["message"]
    assert not any((tmp_path / "data" / "temp" / "log_exports").iterdir())


@pytest.mark.asyncio
async def test_v1_log_export_runs_one_export_at_a_time(
    monkeypatch, tmp_path: Path, asgi_app, asgi_client: httpx.AsyncClient
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    lock = asgi_app.state.services.logs._export_lock
    lock.acquire()
    try:
        response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    finally:
        lock.release()

    assert response.status_code == 400
    assert "already running" in response.json()["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_v1_log_export_requires_authentication(asgi_client, redact):
    response = await asgi_client.get("/api/v1/logs/export", params={"redact": redact})

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
@pytest.mark.parametrize(
    "method", ["developer_header", "developer_bearer", "query", "expired"]
)
async def test_diagnostic_export_rejects_non_admin_auth(
    method, redact, fake_db, asgi_app, asgi_client
):
    from unittest.mock import Mock

    fake_db.add_api_key("diagnostic-developer-key", ["system", "config", "*"])
    export = Mock(
        side_effect=AssertionError("Export must not run before authentication")
    )
    asgi_app.state.services.logs.export_logs = export
    options = {
        "developer_header": {"headers": {"X-API-Key": "diagnostic-developer-key"}},
        "developer_bearer": {
            "headers": {"Authorization": "Bearer diagnostic-developer-key"}
        },
        "query": {"params": {"api_key": "diagnostic-developer-key"}},
        "expired": {
            "headers": {
                "Authorization": "Bearer "
                + jwt.encode(
                    {"username": "admin", "exp": 1}, JWT_SECRET, algorithm="HS256"
                )
            }
        },
    }
    options[method].setdefault("params", {})["redact"] = redact
    response = await asgi_client.get("/api/v1/logs/export", **options[method])
    # API keys and invalid Dashboard credentials are rejected before the
    # export runs; only a request with no credentials at all is a plain 401.
    expected = 401 if method == "query" else 403
    assert response.status_code == expected
    export.assert_not_called()


@pytest.mark.asyncio
async def test_diagnostic_export_requires_system_manage_authorization(
    asgi_app, asgi_client
):
    from unittest.mock import Mock

    export = Mock(
        side_effect=AssertionError("Export must not run without authorization")
    )
    asgi_app.state.services.logs.export_logs = export

    async def deny(_subject, _action, _resource, _context):
        return SimpleNamespace(allowed=False, requires_step_up=False)

    asgi_app.state.runtime.services.authorization.authorize = deny
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 403
    export.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("redact", [True, False])
async def test_diagnostic_export_respects_redaction_for_every_section(
    monkeypatch, tmp_path, asgi_app, asgi_client, redact
):
    from urllib.parse import quote

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    service = asgi_app.state.services.logs
    config = service.config
    config["trace"] = {"enable": False}
    secret = "private/configured+credential"
    plugin_secret = "private-plugin-credential"
    trace_secret = "previous-provider-credential"
    aes_secret = "private-aes-credential"
    config["platform"] = [{"encoding_aes_key": aes_secret}]
    config["diagnostic_network"] = {
        "public_endpoint": "http://8.8.8.8:8080/v1",
        "public_ipv6": "https://[2606:4700:4700::1111]:443/v1",
        "local_endpoint": "http://192.168.1.2:6185/health",
    }
    config["provider_sources"] = [
        {"key": [secret], "api_base": "https://example.com/v1"}
    ]
    config.setdefault("dashboard", {}).update(
        password="private-password",
        jwt_secret="private-jwt-secret",
        password_storage_upgraded=True,
        password_change_required=False,
    )
    config["max_tokens"] = 4096
    plugin = service.core.catalogs.plugins.get_by_name("astrbot_plugin_demo")
    plugin.config = {"api_key": plugin_secret}
    logs = tmp_path / "data/logs"
    logs.mkdir(parents=True)
    (logs / "astrbot.log").write_text(
        f"{aes_secret}\n{secret}\n{quote(secret, safe='')}\n{plugin_secret}\n{trace_secret}\nhttp://8.8.8.8:8080/v1 https://[2606:4700:4700::1111]:443/v1 http://192.168.1.2:6185/health\nAuthorization: Bearer unknown-header-token\nCookie: session=unknown; second=secret\n-----BEGIN PRIVATE KEY-----\nprivate-key-body\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    (logs / "astrbot.1.log").write_text(plugin_secret, encoding="utf-8")
    (logs / "binary.log").write_bytes(b"\x00binary-private-data")
    service.log_broker.publish(
        {"time": 1, "level": "INFO", "data": f"{secret} peer=8.8.8.8"}
    )
    service.log_broker.publish(
        {"type": "trace", "time": 2, "fields": {"api_key": secret, "enabled": True}}
    )
    (logs / "traces.db").touch()

    class Store:
        def list_traces(self, **_kwargs):
            return {"traces": [{"trace_id": "a" * 32}], "total": 1}

        def get_trace(self, _trace_id):
            return {
                "trace": {"trace_id": "a" * 32},
                "spans": [
                    {
                        "attributes": {
                            "api_key": trace_secret,
                            "message": plugin_secret,
                            "peer": "::ffff:8.8.8.8",
                            "ipv6": "2606:4700:4700:0:0:0:0:1111",
                        }
                    }
                ],
            }

    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.get_trace_store", lambda *_: Store()
    )
    response = await asgi_client.get(
        "/api/v1/logs/export",
        headers=_jwt_headers(),
        params={} if redact else {"redact": "false"},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert ("raw-" in response.headers["content-disposition"]) is (not redact)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        all_text = "\n".join(archive.read(name).decode() for name in archive.namelist())
        for private in (
            secret,
            quote(secret, safe=""),
            plugin_secret,
            trace_secret,
            aes_secret,
            "private-password",
            "private-jwt-secret",
            "unknown-header-token",
            "session=unknown",
            "second=secret",
            "private-key-body",
        ):
            assert (private not in all_text) is redact
        assert "binary-private-data" not in all_text
        if not redact:
            assert (
                archive.read("logs/astrbot.log") == (logs / "astrbot.log").read_bytes()
            )
        exported = json.loads(archive.read("config.json"))["profiles"]["default"]
        if redact:
            assert (
                exported["diagnostic_network"]["public_endpoint"]
                == "http://[PUBLIC_IP_1]:8080/v1"
            )
            assert (
                exported["diagnostic_network"]["public_ipv6"]
                == "https://[PUBLIC_IP_2]:443/v1"
            )
            assert b"peer=[PUBLIC_IP_1]" in archive.read("logs/astrbot.in-memory.log")
            trace = json.loads(archive.read("traces/history.jsonl"))["spans"][0][
                "attributes"
            ]
            assert trace["peer"] == "[PUBLIC_IP_1]"
            assert trace["ipv6"] == "[PUBLIC_IP_2]"
            assert "8.8.8.8" not in all_text
            assert "2606:4700:4700" not in all_text
        else:
            assert exported["diagnostic_network"] == config["diagnostic_network"]
            assert "::ffff:8.8.8.8" in all_text
        assert (
            exported["diagnostic_network"]["local_endpoint"]
            == "http://192.168.1.2:6185/health"
        )
        assert exported["dashboard"]["password_storage_upgraded"] is True
        assert exported["dashboard"]["password_change_required"] is False
        assert exported["max_tokens"] == 4096
        assert exported["provider_sources"][0]["key"] == [
            "[REDACTED]" if redact else secret
        ]
        assert json.loads(archive.read("plugins.json"))["plugins"][0]["enabled"] is True
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["trace_history"]["count"] == 1
        assert manifest["trace_enabled"] is False
        assert manifest["redacted"] is redact
        assert "logs/traces.db" not in archive.namelist()
        assert "logs/binary.log" not in archive.namelist()
        assert archive.read("traces/history.in-memory.jsonl") == b""


@pytest.mark.asyncio
async def test_diagnostic_export_without_trace_does_not_create_or_enable_it(
    monkeypatch, tmp_path, asgi_app, asgi_client
):
    from unittest.mock import Mock

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    asgi_app.state.services.logs.config["trace"] = {"enable": False}
    getter = Mock(side_effect=AssertionError("No database should be opened"))
    monkeypatch.setattr(
        "astrbot.dashboard.services.log_service.get_trace_store", getter
    )
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["trace_enabled"] is False
        assert manifest["trace_history"]["status"] == "disabled_no_history"
        assert archive.read("traces/history.jsonl") == b""
    getter.assert_not_called()
    assert not (tmp_path / "data/logs/traces.db").exists()
    assert asgi_app.state.services.logs.config["trace"]["enable"] is False


@pytest.mark.asyncio
async def test_diagnostic_export_authenticates_dashboard_cookie(
    monkeypatch, tmp_path, asgi_client
):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    token = _jwt_headers()["Authorization"].removeprefix("Bearer ")
    asgi_client.cookies.set(DASHBOARD_JWT_COOKIE_NAME, token)
    response = await asgi_client.get("/api/v1/logs/export")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_diagnostic_export_redaction_failure_is_closed_and_unlocks(
    monkeypatch, tmp_path, asgi_app, asgi_client
):
    from unittest.mock import Mock

    from astrbot.dashboard.services import log_service

    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    original = log_service.collect_diagnostics
    monkeypatch.setattr(
        log_service,
        "collect_diagnostics",
        Mock(side_effect=RuntimeError("private-value-in-error")),
    )
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 400
    assert "private-value-in-error" not in response.text
    assert not asgi_app.state.services.logs._export_lock.locked()
    assert not list((tmp_path / "data/temp/log_exports").glob("*.zip"))
    monkeypatch.setattr(log_service, "collect_diagnostics", original)
    response = await asgi_client.get("/api/v1/logs/export", headers=_jwt_headers())
    assert response.status_code == 200
