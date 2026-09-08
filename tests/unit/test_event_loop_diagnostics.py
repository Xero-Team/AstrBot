import asyncio
import threading

import pytest

from astrbot.core.utils import event_loop_diagnostics as diagnostics


def test_watchdog_dump_redacts_tokens_and_urls_but_keeps_paths():
    dumped = diagnostics._redact_watchdog_dump(
        'File "/home/user/astrbot/core/foo.py", line 3, in send\n'
        '    headers = {"Authorization": "Bearer sk-abcdefghijklmnopqrstuvwxyz"}\n'
        "    url = 'https://example.invalid/v1/chat'\n"
    )

    assert "foo.py" in dumped
    assert "/home/user/astrbot/core/foo.py" in dumped
    assert "Bearer [REDACTED]" in dumped
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in dumped
    assert "https://example.invalid" not in dumped
    assert "[REDACTED_URL]" in dumped


def test_load_event_loop_diagnostic_settings_defaults():
    """Default settings enable lag monitoring and the stack dump watchdog."""
    settings = diagnostics.load_event_loop_diagnostic_settings()

    assert settings.lag_monitor_enabled is True
    assert settings.lag_monitor_interval == diagnostics.DEFAULT_LAG_MONITOR_INTERVAL
    assert settings.lag_monitor_threshold == diagnostics.DEFAULT_LAG_MONITOR_THRESHOLD
    assert settings.watchdog_enabled is True
    assert settings.watchdog_interval == diagnostics.DEFAULT_WATCHDOG_INTERVAL
    assert settings.watchdog_timeout == diagnostics.DEFAULT_WATCHDOG_TIMEOUT
    assert settings.watchdog_log_max_bytes == diagnostics.DEFAULT_WATCHDOG_LOG_MAX_BYTES


def test_create_event_loop_diagnostic_jobs_defaults():
    """Default diagnostics should describe both jobs without creating tasks."""
    jobs = diagnostics.create_event_loop_diagnostic_jobs()
    try:
        assert [name for name, _job in jobs] == [
            "event_loop_lag_monitor",
            "event_loop_watchdog",
        ]
        assert all(asyncio.iscoroutine(job) for _name, job in jobs)
    finally:
        for _name, job in jobs:
            job.close()


@pytest.mark.asyncio
async def test_event_loop_watchdog_stops_worker_thread():
    """The event loop watchdog should stop its worker thread on shutdown."""
    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(dump_after=10, interval=0.01)
    )
    await asyncio.sleep(0.02)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert not any(
        thread.name == "event_loop_watchdog" for thread in threading.enumerate()
    )


@pytest.mark.asyncio
async def test_event_loop_watchdog_writes_rotating_log(tmp_path, monkeypatch):
    """The watchdog should write to and rotate its log file."""
    log_path = tmp_path / "logs" / "event_loop_watchdog.log"
    log_path.parent.mkdir()
    log_path.write_text("x" * 8, encoding="utf-8")
    dumped = threading.Event()
    original_open = diagnostics._open_watchdog_log_file

    def open_log(path, max_bytes):
        handle = original_open(path, max_bytes)
        dumped.set()
        return handle

    monkeypatch.setattr(diagnostics, "_open_watchdog_log_file", open_log)

    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(
            dump_after=0.02,
            interval=0.005,
            dump_path=log_path,
            max_bytes=4,
        )
    )
    try:
        for _ in range(200):
            if any(
                thread.name == "event_loop_watchdog" for thread in threading.enumerate()
            ):
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("event loop watchdog thread did not start")

        # Block the loop until the worker opens the dump file. Do not assert
        # captured stack frames: dump_traceback races the stall, so Windows
        # may show Thread.join and macOS selectors.select instead of this
        # module.
        assert dumped.wait(timeout=1.0)
        await asyncio.sleep(0.05)

        log_content = log_path.read_text(encoding="utf-8")
        assert "Event loop stalled for" in log_content
        assert (
            log_path.with_name("event_loop_watchdog.log.1").read_text(encoding="utf-8")
            == "x" * 8
        )
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_event_loop_watchdog_survives_dump_failure(tmp_path, monkeypatch):
    """The watchdog should keep running after stack dump failures."""
    log_path = tmp_path / "event_loop_watchdog.log"
    dumped = threading.Event()
    attempts = 0

    def flaky_open(path, max_bytes):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("boom")
        dumped.set()
        return path.open("a", encoding="utf-8")

    monkeypatch.setattr(diagnostics, "_open_watchdog_log_file", flaky_open)

    task = asyncio.create_task(
        diagnostics.event_loop_watchdog(
            dump_after=0.02,
            interval=0.005,
            dump_path=log_path,
        )
    )
    try:
        for _ in range(200):
            if any(
                thread.name == "event_loop_watchdog" for thread in threading.enumerate()
            ):
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("event loop watchdog thread did not start")

        # Keep the event loop stalled until the worker retries after the
        # first dump failure. A short time.sleep() can expire on macOS
        # before the second attempt.
        assert dumped.wait(timeout=1.0)
        assert attempts >= 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
