import os
import sys

import pytest
from click.testing import CliRunner

from astrbot.cli.commands import cmd_run
from astrbot.cli.utils import basic as cli_basic


def test_run_reset_password_sets_startup_env(monkeypatch, tmp_path):
    (tmp_path / ".astrbot").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(cmd_run.DASHBOARD_RESET_PASSWORD_ENV, raising=False)
    original_env = {
        "ASTRBOT_CLI": os.environ.get("ASTRBOT_CLI"),
        "ASTRBOT_ROOT": os.environ.get("ASTRBOT_ROOT"),
        cmd_run.DASHBOARD_RESET_PASSWORD_ENV: os.environ.get(
            cmd_run.DASHBOARD_RESET_PASSWORD_ENV
        ),
    }
    original_sys_path = list(sys.path)

    called = False

    async def fake_run_astrbot(astrbot_root):
        nonlocal called
        called = True
        assert astrbot_root == tmp_path
        assert os.environ[cmd_run.DASHBOARD_RESET_PASSWORD_ENV] == "1"

    monkeypatch.setattr(cmd_run, "run_astrbot", fake_run_astrbot)

    try:
        result = CliRunner().invoke(cmd_run.run, ["--reset-password"])
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.path[:] = original_sys_path

    assert result.exit_code == 0, result.output
    assert called is True


@pytest.mark.asyncio
async def test_cli_check_dashboard_skips_download_when_local_webui_matches(
    monkeypatch,
    tmp_path,
):
    from astrbot.core.config.default import VERSION

    async def fake_get_dashboard_version():
        return f"v{VERSION}"

    monkeypatch.setattr(
        "astrbot.core.utils.io.get_dashboard_version",
        fake_get_dashboard_version,
    )
    download_calls = 0

    async def fake_download_dashboard(**kwargs):
        nonlocal download_calls
        download_calls += 1
        _ = kwargs

    monkeypatch.setattr(
        "astrbot.core.utils.io.download_dashboard",
        fake_download_dashboard,
    )

    await cli_basic.check_dashboard(tmp_path / "data")

    assert download_calls == 0
