import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.utils.metrics import MetricsRuntime


@pytest.mark.asyncio
async def test_metrics_runtime_persists_platform_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Platform statistics are written to the local store."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    database = AsyncMock()
    metrics = MetricsRuntime(database)

    await metrics.record_platform_event(
        platform_id="telegram",
        platform_type="telegram",
    )

    database.insert_platform_stats.assert_awaited_once_with(
        platform_id="telegram",
        platform_type="telegram",
    )


@pytest.mark.asyncio
async def test_metrics_runtime_defaults_platform_type_to_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    database = AsyncMock()
    metrics = MetricsRuntime(database)

    await metrics.record_platform_event(platform_id="adapter")

    database.insert_platform_stats.assert_awaited_once_with(
        platform_id="adapter",
        platform_type="unknown",
    )


@pytest.mark.asyncio
async def test_metrics_runtime_without_database_is_a_noop() -> None:
    metrics = MetricsRuntime(None)

    await metrics.record_platform_event(platform_id="adapter")


@pytest.mark.asyncio
async def test_metrics_runtime_is_silent_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "true")
    database = AsyncMock()
    metrics = MetricsRuntime(database)

    await metrics.record_platform_event(platform_id="adapter")

    database.insert_platform_stats.assert_not_awaited()


@pytest.mark.asyncio
async def test_metrics_runtime_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    database = AsyncMock()
    database.insert_platform_stats.side_effect = asyncio.CancelledError
    metrics = MetricsRuntime(database)

    with pytest.raises(asyncio.CancelledError):
        await metrics.record_platform_event(platform_id="adapter")


@pytest.mark.asyncio
async def test_metrics_runtime_never_creates_an_http_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Statistics stay local and never open an outbound HTTP session."""
    from astrbot.core.utils import proxy_route

    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")

    def fail_on_network():
        raise AssertionError("statistics must not create an HTTP session")

    monkeypatch.setattr(proxy_route, "create_aiohttp_session", fail_on_network)
    database = AsyncMock()
    metrics = MetricsRuntime(database)

    await metrics.record_platform_event(platform_id="adapter")

    database.insert_platform_stats.assert_awaited_once()
