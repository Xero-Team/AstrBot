import platform
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config import VERSION
from astrbot.core.utils.metrics import MetricsRuntime


@pytest.mark.asyncio
async def test_metrics_runtime_shutdown_cancels_its_pending_flush_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A runtime stops its own periodic task rather than leaving it alive."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    monkeypatch.delenv("ASTRBOT_DISABLE_METRICS", raising=False)
    metrics = MetricsRuntime(
        {"disable_metrics": False},
        None,
        installation_id_path=tmp_path / ".installation_id",
    )
    metrics._upload_interval_seconds = 3600
    metrics._has_uploaded_once = True
    metrics._post_metrics = AsyncMock()

    await metrics.upload(msg_event_tick=1, adapter_name="test")
    flush_task = metrics._flush_task
    assert flush_task is not None
    assert not flush_task.done()

    await metrics.shutdown()

    assert flush_task.cancelled()
    assert metrics._flush_task is None
    assert metrics._pending_metrics == {}


@pytest.mark.asyncio
async def test_metrics_runtimes_keep_batches_tasks_and_shutdown_isolated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Two application runtimes cannot affect one another's telemetry state."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    monkeypatch.delenv("ASTRBOT_DISABLE_METRICS", raising=False)
    first_config = {"disable_metrics": False, "runtime": "first"}
    second_config = {"disable_metrics": False, "runtime": "second"}
    first = MetricsRuntime(
        first_config,
        None,
        installation_id_path=tmp_path / "first" / ".installation_id",
    )
    second = MetricsRuntime(
        second_config,
        None,
        installation_id_path=tmp_path / "second" / ".installation_id",
    )
    first._upload_interval_seconds = 3600
    second._upload_interval_seconds = 3600
    first._has_uploaded_once = True
    second._has_uploaded_once = True
    first._post_metrics = AsyncMock()
    second._post_metrics = AsyncMock()

    try:
        await first.upload(msg_event_tick=1, adapter_name="first")
        await second.upload(msg_event_tick=1, adapter_name="second")

        first_task = first._flush_task
        second_task = second._flush_task
        assert first_task is not None
        assert second_task is not None
        assert first_task is not second_task
        assert first._config is first_config
        assert second._config is second_config
        assert first._pending_metrics != second._pending_metrics

        await first.shutdown()

        assert first_task.cancelled()
        assert first._pending_metrics == {}
        assert first._flush_task is None
        assert second_task is second._flush_task
        assert not second_task.done()
        assert second._pending_metrics
        assert not second._is_disabled()
    finally:
        await first.shutdown()
        await second.shutdown()


@pytest.mark.asyncio
async def test_metrics_runtime_persists_platform_statistics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Platform telemetry continues to update the runtime's statistics store."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    monkeypatch.delenv("ASTRBOT_DISABLE_METRICS", raising=False)
    database = AsyncMock()
    metrics = MetricsRuntime(
        {"disable_metrics": False},
        database,
        installation_id_path=tmp_path / ".installation_id",
    )
    metrics._post_metrics = AsyncMock()

    try:
        await metrics.upload(
            msg_event_tick=1,
            adapter_name="telegram",
            adapter_type="telegram",
        )

        database.insert_platform_stats.assert_awaited_once_with(
            platform_id="telegram",
            platform_type="telegram",
        )
    finally:
        await metrics.shutdown()


def test_metrics_runtime_is_disabled_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "true")
    monkeypatch.delenv("ASTRBOT_DISABLE_METRICS", raising=False)
    metrics = MetricsRuntime(
        {"disable_metrics": False},
        None,
        installation_id_path=tmp_path / ".installation_id",
    )

    assert metrics._is_disabled()


def test_metrics_runtime_stores_installation_id_under_its_runtime_root(
    tmp_path: Path,
) -> None:
    """Installation identity follows the explicitly configured runtime path."""
    installation_id_path = tmp_path / "data" / ".installation_id"
    metrics = MetricsRuntime(
        {"disable_metrics": False},
        None,
        installation_id_path=installation_id_path,
    )

    installation_id = metrics.get_installation_id()

    assert installation_id_path.read_text(encoding="utf-8") == installation_id


@pytest.mark.asyncio
async def test_metrics_payload_includes_python_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Telemetry uploads include the running Python version next to os/v."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    monkeypatch.delenv("ASTRBOT_DISABLE_METRICS", raising=False)
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args
            return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args
            return None

        def post(self, _url, json=None, timeout=None, proxy=None):
            del timeout, proxy
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "astrbot.core.utils.proxy_route.create_aiohttp_session",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        "astrbot.core.utils.proxy_route.current_aiohttp_proxy",
        lambda: None,
    )
    metrics = MetricsRuntime(
        {"disable_metrics": False},
        None,
        installation_id_path=tmp_path / ".installation_id",
    )

    await metrics._post_metrics({"msg_event_tick": 1})

    payload = captured["json"]
    assert isinstance(payload, dict)
    metrics_data = payload["metrics_data"]
    assert isinstance(metrics_data, dict)
    assert metrics_data["v"] == VERSION
    assert metrics_data["python_version"] == platform.python_version()
