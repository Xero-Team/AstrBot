import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner
from filelock import Timeout

from astrbot.application import ApplicationOptions, run_application
from astrbot.cli.commands import cmd_init, cmd_run
from astrbot.runtime_instance_lock import (
    LOCK_FILENAME,
    runtime_instance_lock,
    runtime_instance_lock_path,
)

_HOLD_LOCK_SCRIPT = """
from filelock import FileLock
import sys
import time

with FileLock(sys.argv[1], timeout=5, fallback_to_soft=False):
    print("held", flush=True)
    time.sleep(60)
"""


@contextmanager
def hold_runtime_instance_lock(data_dir: Path) -> Iterator[None]:
    """Hold the instance lock in a child process until the context exits."""
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_instance_lock_path(data_dir)
    process = subprocess.Popen(
        [sys.executable, "-c", _HOLD_LOCK_SCRIPT, str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready = process.stdout.readline()
        if process.poll() is not None or "held" not in ready:
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(
                f"lock holder failed: stdout={ready!r} stderr={stderr!r}"
            )
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_second_process_times_out_on_the_same_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with hold_runtime_instance_lock(data_dir):
        with pytest.raises(Timeout):
            with runtime_instance_lock(data_dir, timeout=0.05):
                pass


def test_leftover_lock_file_is_still_acquirable(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    lock_path = runtime_instance_lock_path(data_dir)
    lock_path.write_text("stale", encoding="utf-8")

    with runtime_instance_lock(data_dir, timeout=0.05):
        assert lock_path.exists()


def test_lock_path_is_under_the_data_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    assert runtime_instance_lock_path(data_dir) == data_dir / LOCK_FILENAME


@pytest.mark.asyncio
async def test_run_application_exits_before_services_when_lock_held(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("astrbot.application.prepare_runtime_environment", lambda: None)
    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path", lambda: str(data_dir)
    )
    monkeypatch.setattr("astrbot.runtime_instance_lock.LOCK_TIMEOUT_SECONDS", 0.05)

    async def fake_resolve_dashboard_assets(webui_dir: str | None = None) -> str | None:
        raise AssertionError("dashboard resolution must not run while the lock is held")

    monkeypatch.setattr(
        "astrbot.application.resolve_dashboard_assets",
        fake_resolve_dashboard_assets,
    )
    monkeypatch.setattr(
        "astrbot.application.create_runtime_services",
        mock.Mock(
            side_effect=AssertionError(
                "runtime services must not start while the lock is held"
            )
        ),
    )

    with (
        hold_runtime_instance_lock(data_dir),
        caplog.at_level(logging.ERROR, logger="astrbot"),
        pytest.raises(SystemExit) as excinfo,
    ):
        await run_application(ApplicationOptions())

    assert excinfo.value.code == 1
    assert str(runtime_instance_lock_path(data_dir)) in caplog.text
    assert "already owns this data directory" in caplog.text


def test_cmd_run_source_does_not_construct_filelock() -> None:
    source = Path(cmd_run.__file__).read_text(encoding="utf-8")
    assert "FileLock" not in source
    assert "filelock" not in source


def test_cmd_run_fails_when_runtime_lock_held(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / ".astrbot").touch()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    monkeypatch.setattr(cmd_run, "_initialize_runtime_bootstrap", lambda: None)
    monkeypatch.setattr("astrbot.runtime_instance_lock.LOCK_TIMEOUT_SECONDS", 0.05)
    original_sys_path = list(sys.path)
    original_cli = os.environ.get("ASTRBOT_CLI")

    try:
        with (
            hold_runtime_instance_lock(data_dir),
            caplog.at_level(logging.ERROR, logger="astrbot"),
        ):
            result = CliRunner().invoke(cmd_run.run)
    finally:
        sys.path[:] = original_sys_path
        if original_cli is None:
            os.environ.pop("ASTRBOT_CLI", None)
        else:
            os.environ["ASTRBOT_CLI"] = original_cli

    assert result.exit_code == 1
    assert str(runtime_instance_lock_path(data_dir)) in caplog.text
    assert "already owns this data directory" in caplog.text


def test_cmd_init_fails_when_runtime_lock_held(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    monkeypatch.setattr(
        "astrbot.cli.utils.basic.get_astrbot_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr("astrbot.runtime_instance_lock.LOCK_TIMEOUT_SECONDS", 0.05)
    data_dir = tmp_path / "data"

    with hold_runtime_instance_lock(data_dir):
        result = CliRunner().invoke(cmd_init.init, ["--yes"])

    assert result.exit_code != 0
    assert "Cannot acquire lock file" in result.output
    assert not (tmp_path / ".astrbot").exists()
