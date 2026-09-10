"""Tests for the host-side runtime image command checker."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[2] / "scripts" / "check_container_runtime.py"
    spec = importlib.util.spec_from_file_location("check_container_runtime", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_features_matches_dockerfile_profiles() -> None:
    module = _module()

    assert module.normalize_features("minimal") == frozenset()
    assert module.normalize_features("full") == module.FULL_FEATURES
    assert module.normalize_features("browser,node") == {"browser", "node"}

    with pytest.raises(ValueError, match="unknown runtime feature"):
        module.normalize_features("browser,unknown")


def test_runtime_checker_includes_uvx_and_selected_feature_commands() -> None:
    module = _module()

    checks = module.checks_for_features(module.normalize_features("browser,node"))
    commands = [command for _, command in checks]

    assert "uvx --version" in commands
    assert any("subprocess.run(['uvx', '--version']" in command for command in commands)
    assert any("playwright --version" in command for command in commands)
    assert any("codex --version" in command for command in commands)
