from pathlib import Path

import pytest

from astrbot.core.computer.local_file_security import open_file_in_allowed_roots
from astrbot.core.computer.process_sandbox import (
    SandboxLimits,
    SandboxSpec,
    create_process_sandbox,
    detect_local_runtime_info,
)


def test_sandbox_limits_reject_non_positive_values() -> None:
    with pytest.raises(ValueError, match="cpu_seconds"):
        SandboxLimits(cpu_seconds=0)


def test_detect_local_runtime_info_reports_platform() -> None:
    info = detect_local_runtime_info()
    assert info["os"]
    assert "sandbox" in info
    assert info["sandbox"]["status"] in {
        "detected",
        "missing",
        "unavailable",
        "unsupported",
    }


def test_create_process_sandbox_matches_runtime_probe() -> None:
    info = detect_local_runtime_info()
    if info["sandbox"]["status"] == "unsupported":
        with pytest.raises(RuntimeError):
            create_process_sandbox()
        return
    sandbox = create_process_sandbox()
    assert sandbox is not None


def test_open_file_in_allowed_roots_reads_regular_file(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("safe", encoding="utf-8")
    try:
        fd = open_file_in_allowed_roots(str(target), (allowed,), access="read")
    except RuntimeError:
        pytest.skip("Race-resistant file access is unavailable on this platform.")
    try:
        import os

        assert os.read(fd, 16) == b"safe"
    finally:
        os.close(fd)


def test_open_file_in_allowed_roots_rejects_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    try:
        with pytest.raises(PermissionError):
            open_file_in_allowed_roots(str(outside), (allowed,), access="read")
    except RuntimeError:
        pytest.skip("Race-resistant file access is unavailable on this platform.")


def test_sandbox_prepare_command_rejects_empty_argv(tmp_path: Path) -> None:
    info = detect_local_runtime_info()
    if info["sandbox"]["status"] in {"unsupported", "missing"}:
        pytest.skip("No Local process sandbox backend is available.")
    sandbox = create_process_sandbox()
    with pytest.raises(ValueError, match="sandbox command"):
        sandbox._prepare_command([], SandboxSpec(workspace=tmp_path))
