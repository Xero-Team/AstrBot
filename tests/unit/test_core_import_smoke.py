import os
import subprocess
import sys
from pathlib import Path


def test_importing_core_does_not_create_runtime_services(tmp_path: Path) -> None:
    """The package boundary must stay inert in a fresh interpreter."""
    root = tmp_path / "runtime-root"
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(root),
    }
    code = """
import pathlib
import sys
import astrbot.core
root = pathlib.Path(__import__('os').environ['ASTRBOT_ROOT'])
assert not root.exists()
for module in (
    'astrbot.core.db.sqlite',
    'astrbot.core.config.astrbot_config',
    'astrbot.core.utils.t2i.renderer',
    'astrbot.core.utils.shared_preferences',
):
    assert module not in sys.modules, module
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
