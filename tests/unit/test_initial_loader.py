import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.initial_loader as initial_loader


@pytest.mark.asyncio
async def test_initial_loader_cleans_lifecycle_after_initialize_failure(monkeypatch):
    lifecycle = SimpleNamespace(
        initialize=AsyncMock(side_effect=RuntimeError("database failed")),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(
        initial_loader,
        "AstrBotCoreLifecycle",
        lambda *_args: lifecycle,
    )
    logger = MagicMock()
    monkeypatch.setattr(initial_loader, "logger", logger)
    loader = initial_loader.InitialLoader(
        services=SimpleNamespace(),
        log_broker=MagicMock(),
    )

    await loader.start()

    lifecycle.stop.assert_awaited_once()
    logger.critical.assert_called()


@pytest.mark.asyncio
async def test_initial_loader_propagates_runtime_cancellation_after_cleanup(
    monkeypatch,
):
    async def cancelled_start() -> None:
        raise asyncio.CancelledError

    lifecycle = SimpleNamespace(
        initialize=AsyncMock(),
        start=cancelled_start,
        stop=AsyncMock(),
        dashboard_shutdown_event=asyncio.Event(),
    )
    monkeypatch.setattr(
        initial_loader,
        "AstrBotCoreLifecycle",
        lambda *_args: lifecycle,
    )
    monkeypatch.setattr(
        initial_loader,
        "AstrBotDashboard",
        lambda *_args: SimpleNamespace(run=lambda: None),
    )
    loader = initial_loader.InitialLoader(
        services=SimpleNamespace(db=MagicMock()),
        log_broker=MagicMock(),
    )

    with pytest.raises(asyncio.CancelledError):
        await loader.start()

    lifecycle.stop.assert_awaited_once()
