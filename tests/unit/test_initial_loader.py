import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.initial_loader as initial_loader


def _lifecycle(*, start) -> SimpleNamespace:
    return SimpleNamespace(
        initialize=AsyncMock(),
        start=start,
        stop=AsyncMock(),
        reboot_requested=False,
        process_rebooter=SimpleNamespace(reboot=MagicMock()),
        runtime=SimpleNamespace(dashboard_shutdown_event=asyncio.Event()),
    )


def _loader(monkeypatch, lifecycle, dashboard_run):
    monkeypatch.setattr(
        initial_loader,
        "AstrBotCoreLifecycle",
        lambda *_args: lifecycle,
    )

    class DashboardFactory:
        @classmethod
        async def create(cls, *_args, **_kwargs):
            return SimpleNamespace(run=dashboard_run)

    monkeypatch.setattr(initial_loader, "AstrBotDashboard", DashboardFactory)
    return initial_loader.InitialLoader(
        services=SimpleNamespace(db=MagicMock()),
        log_broker=MagicMock(),
    )


@pytest.mark.asyncio
async def test_initial_loader_propagates_initialize_failure_after_cleanup(monkeypatch):
    lifecycle = _lifecycle(start=AsyncMock())
    lifecycle.initialize.side_effect = RuntimeError("database failed")
    loader = _loader(monkeypatch, lifecycle, lambda: None)

    with pytest.raises(RuntimeError, match="database failed"):
        await loader.start()

    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_dashboard_failure_cancels_core_and_stops_lifecycle(monkeypatch):
    core_cancelled = asyncio.Event()

    async def core_start() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            core_cancelled.set()

    async def dashboard_run() -> None:
        raise RuntimeError("dashboard failed")

    lifecycle = _lifecycle(start=core_start)
    loader = _loader(monkeypatch, lifecycle, dashboard_run)

    with pytest.raises(RuntimeError, match="dashboard failed"):
        await loader.start()

    assert core_cancelled.is_set()
    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_core_failure_cancels_dashboard_and_stops_lifecycle(monkeypatch):
    dashboard_cancelled = asyncio.Event()

    async def core_start() -> None:
        raise RuntimeError("core failed")

    async def dashboard_run() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            dashboard_cancelled.set()

    lifecycle = _lifecycle(start=core_start)
    loader = _loader(monkeypatch, lifecycle, dashboard_run)

    with pytest.raises(RuntimeError, match="core failed"):
        await loader.start()

    assert dashboard_cancelled.is_set()
    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_runtime_return_stops_lifecycle_once(monkeypatch):
    lifecycle = _lifecycle(start=AsyncMock())
    loader = _loader(monkeypatch, lifecycle, lambda: None)

    await loader.start()

    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_core_return_cancels_dashboard_and_stops_lifecycle(monkeypatch):
    """A completed Core cannot leave the Dashboard serving on its own."""
    dashboard_cancelled = asyncio.Event()

    async def dashboard_run() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            dashboard_cancelled.set()

    lifecycle = _lifecycle(start=AsyncMock())
    loader = _loader(monkeypatch, lifecycle, dashboard_run)

    await loader.start()

    assert dashboard_cancelled.is_set()
    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_cancellation_stops_lifecycle_once(monkeypatch):
    async def core_start() -> None:
        await asyncio.Event().wait()

    lifecycle = _lifecycle(start=core_start)
    loader = _loader(monkeypatch, lifecycle, lambda: None)
    task = asyncio.create_task(loader.start())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_core_self_cancellation_cancels_dashboard_and_stops_lifecycle(
    monkeypatch,
):
    """A cancelled Core task must not leave Dashboard supervision blocked."""
    dashboard_cancelled = asyncio.Event()

    async def core_start() -> None:
        raise asyncio.CancelledError

    async def dashboard_run() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            dashboard_cancelled.set()

    lifecycle = _lifecycle(start=core_start)
    loader = _loader(monkeypatch, lifecycle, dashboard_run)

    with pytest.raises(asyncio.CancelledError):
        await loader.start()

    assert dashboard_cancelled.is_set()
    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_lifecycle_event_bus_failure_cancels_dashboard(monkeypatch):
    """A real start() must end when dispatch fails despite default diagnostics."""
    from astrbot.core.agent.follow_up import FollowUpCoordinator
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
    from astrbot.core.runtime_catalogs import RuntimeCatalogs
    from astrbot.core.webchat.queue_manager import WebChatQueueManager
    from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator

    config = MagicMock()
    config.get = MagicMock(return_value="")
    webchat_queue_manager = WebChatQueueManager()
    services = SimpleNamespace(
        config=config,
        db=MagicMock(),
        preferences=MagicMock(),
        html_renderer=MagicMock(),
        file_token_service=MagicMock(),
        pip_installer=MagicMock(),
        catalogs=RuntimeCatalogs(),
        webchat_queue_manager=webchat_queue_manager,
        webchat_run_coordinator=WebChatRunCoordinator(webchat_queue_manager),
        follow_up_coordinator=FollowUpCoordinator(),
        llm_metadata_catalog=MagicMock(),
        metrics=MagicMock(),
        computer_runtime=MagicMock(),
        tool_image_cache=MagicMock(),
        demo_mode=False,
    )
    lifecycle = AstrBotCoreLifecycle(MagicMock(), services)
    dashboard_cancelled = asyncio.Event()
    stop_calls = 0
    real_stop = lifecycle.stop

    async def initialize() -> None:
        lifecycle._initialized = True
        lifecycle.dashboard_shutdown_event = asyncio.Event()
        lifecycle._runtime = SimpleNamespace(
            dashboard_shutdown_event=lifecycle.dashboard_shutdown_event,
        )
        lifecycle.event_bus = MagicMock()
        lifecycle.event_bus.shutdown = AsyncMock()

        async def fail_dispatch() -> None:
            raise RuntimeError("event bus failed")

        lifecycle.event_bus.dispatch = fail_dispatch
        lifecycle.execution_context = MagicMock()
        lifecycle.execution_context._register_tasks = []
        lifecycle.cron_manager = None
        lifecycle.temp_dir_cleaner = None

    async def tracking_stop() -> None:
        nonlocal stop_calls
        stop_calls += 1
        await real_stop()

    async def dashboard_run() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            dashboard_cancelled.set()

    lifecycle.initialize = initialize
    lifecycle.stop = tracking_stop
    loader = _loader(monkeypatch, lifecycle, dashboard_run)

    with pytest.raises(RuntimeError, match="event bus failed"):
        await loader.start()

    assert dashboard_cancelled.is_set()
    assert stop_calls == 1


@pytest.mark.asyncio
async def test_initial_loader_reboots_after_stop_when_requested(monkeypatch):
    call_order: list[str] = []
    reboot = MagicMock()

    def reboot_impl(delay: int = 3) -> None:
        call_order.append(f"reboot:{delay}")

    reboot.side_effect = reboot_impl

    lifecycle = _lifecycle(start=AsyncMock())
    lifecycle.reboot_requested = True
    lifecycle.process_rebooter = SimpleNamespace(reboot=reboot)
    original_stop = lifecycle.stop

    async def tracking_stop() -> None:
        call_order.append("stop")
        await original_stop()

    lifecycle.stop = tracking_stop
    loader = _loader(monkeypatch, lifecycle, lambda: None)

    await loader.start()

    assert call_order == ["stop", "reboot:0"]
    reboot.assert_called_once_with(delay=0)
    original_stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_initial_loader_does_not_reboot_without_request(monkeypatch):
    lifecycle = _lifecycle(start=AsyncMock())
    reboot = MagicMock()
    lifecycle.process_rebooter = SimpleNamespace(reboot=reboot)
    loader = _loader(monkeypatch, lifecycle, lambda: None)

    await loader.start()

    reboot.assert_not_called()
    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_flushes_dashboard_then_stops_then_reboots(monkeypatch):
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

    call_order: list[str] = []
    reboot = MagicMock()
    dashboard_started = asyncio.Event()
    shutdown_event = asyncio.Event()

    def reboot_impl(delay: int = 3) -> None:
        call_order.append(f"reboot:{delay}")

    reboot.side_effect = reboot_impl

    config = MagicMock()
    config.get = MagicMock(return_value="")
    lifecycle = AstrBotCoreLifecycle(
        MagicMock(),
        SimpleNamespace(config=config, db=MagicMock()),
    )

    async def initialize() -> None:
        lifecycle._initialized = True
        lifecycle.dashboard_shutdown_event = shutdown_event
        lifecycle.process_rebooter = SimpleNamespace(reboot=reboot)
        lifecycle._runtime = SimpleNamespace(dashboard_shutdown_event=shutdown_event)

    async def core_start() -> None:
        await asyncio.Event().wait()

    original_stop = lifecycle.stop

    async def tracking_stop() -> None:
        call_order.append("stop")
        await original_stop()

    async def dashboard_run() -> None:
        dashboard_started.set()
        await shutdown_event.wait()
        call_order.append("response_flushed")

    lifecycle.initialize = initialize
    lifecycle.start = core_start
    lifecycle.stop = tracking_stop
    loader = _loader(monkeypatch, lifecycle, dashboard_run)
    start_task = asyncio.create_task(loader.start())
    await dashboard_started.wait()
    await lifecycle.restart()
    await start_task

    assert call_order == ["response_flushed", "stop", "reboot:0"]
    reboot.assert_called_once_with(delay=0)


@pytest.mark.asyncio
async def test_missing_rebooter_does_not_hide_runtime_failure(monkeypatch):
    lifecycle = _lifecycle(start=AsyncMock(side_effect=RuntimeError("core failed")))
    lifecycle.reboot_requested = True
    lifecycle.process_rebooter = None
    loader = _loader(monkeypatch, lifecycle, lambda: None)

    with pytest.raises(RuntimeError, match="core failed"):
        await loader.start()

    lifecycle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_rebooter_skips_process_replace(monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(
        initial_loader.logger,
        "error",
        lambda message, *args: errors.append(message % args if args else message),
    )
    lifecycle = _lifecycle(start=AsyncMock())
    lifecycle.reboot_requested = True
    lifecycle.process_rebooter = None
    loader = _loader(monkeypatch, lifecycle, lambda: None)

    await loader.start()

    lifecycle.stop.assert_awaited_once()
    assert errors == [
        "Restart was requested without a process rebooter; skipping process replace"
    ]
