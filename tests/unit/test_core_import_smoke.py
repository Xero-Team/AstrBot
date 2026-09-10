import os
import subprocess
import sys
from pathlib import Path


def test_btw_sdk_enable_check_does_not_construct_runtime(tmp_path: Path) -> None:
    root = tmp_path / "runtime-root"
    environment = {**os.environ, "ASTRBOT_ROOT": str(root)}
    code = """
import os
import pathlib
import sys
from astrbot.api import btw_work_loop_enabled
from astrbot.api import btw_work_latest_status
from astrbot.core.agent.btw import runtime_registry
assert callable(btw_work_latest_status)
assert runtime_registry._managers == {}
assert btw_work_loop_enabled({'btw': {'enabled': True, 'work_loop': {'enabled': True}}})
assert not btw_work_loop_enabled(None)
assert 'astrbot.core.agent.btw.work_loop' not in sys.modules
assert 'astrbot.core.pipeline.scheduler' not in sys.modules
assert not pathlib.Path(os.environ['ASTRBOT_ROOT']).exists()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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


def test_core_imports_do_not_load_concrete_model_sdks(tmp_path: Path) -> None:
    """Core boundaries must not eagerly pull provider SDKs into a process."""
    root = tmp_path / "runtime-root"
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(root),
    }
    code = """
import sys
import astrbot.core
import astrbot.core.runtime_services

sdk_modules = ('openai', 'anthropic', 'google.genai')
for module in sdk_modules:
    assert module not in sys.modules, module
assert not any(
    name.startswith('google.genai.') for name in sys.modules
), 'google.genai submodule loaded'
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_runtime_services_import_does_not_configure_logging(tmp_path: Path) -> None:
    """The inert runtime boundary must not install application log handlers."""
    root = tmp_path / "runtime-root"
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(root),
    }
    code = """
import logging

from astrbot.core.log import LogManager

assert LogManager._configured is False
assert not logging.getLogger("astrbot").handlers

import astrbot.core.runtime_services

assert LogManager._configured is False
assert not logging.getLogger("astrbot").handlers
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_importing_runtime_services_does_not_configure_logging(tmp_path: Path) -> None:
    """Runtime service declarations must not install logging handlers at import time."""
    root = tmp_path / "runtime-root"
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(root),
    }
    code = """
import logging

from astrbot.core.log import LogManager

assert LogManager._configured is False
assert not any(
    getattr(handler, LogManager._LOGGER_HANDLER_FLAG, False)
    for handler in logging.getLogger().handlers
)

import astrbot.core.runtime_services

assert LogManager._configured is False
assert not any(
    getattr(handler, LogManager._LOGGER_HANDLER_FLAG, False)
    for handler in logging.getLogger().handlers
)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
