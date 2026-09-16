import os
from pathlib import Path

import pytest

from astrbot.core.computer import local_file_security
from astrbot.core.computer.local_file_security import (
    open_file_in_allowed_roots,
    read_fd_at,
)
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
    if info["sandbox"]["status"] in {"unsupported", "missing"}:
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
    fd = open_file_in_allowed_roots(str(target), (allowed,), access="read")
    try:
        assert os.read(fd, 16) == b"safe"
    finally:
        os.close(fd)


def test_open_file_in_allowed_roots_rejects_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(PermissionError, match="outside restricted roots"):
        open_file_in_allowed_roots(str(outside), (allowed,), access="read")


def test_open_file_in_allowed_roots_rejects_directory(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    nested = allowed / "dir"
    nested.mkdir()
    with pytest.raises(IsADirectoryError):
        open_file_in_allowed_roots(str(nested), (allowed,), access="read")


def test_open_file_without_dir_fd_reads_regular_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        local_file_security,
        "_descriptor_relative_access_available",
        lambda: False,
    )
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("safe", encoding="utf-8")
    fd = open_file_in_allowed_roots(str(target), (allowed,), access="read")
    try:
        assert read_fd_at(fd, 16, 0) == b"safe"
    finally:
        os.close(fd)


def test_open_file_without_dir_fd_rejects_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        local_file_security,
        "_descriptor_relative_access_available",
        lambda: False,
    )
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(PermissionError, match="outside restricted roots"):
        open_file_in_allowed_roots(str(outside), (allowed,), access="read")


def test_open_file_without_dir_fd_creates_parents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        local_file_security,
        "_descriptor_relative_access_available",
        lambda: False,
    )
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "nested" / "note.txt"
    fd = open_file_in_allowed_roots(
        str(target),
        (allowed,),
        access="write",
        create_parents=True,
    )
    try:
        os.write(fd, b"created")
    finally:
        os.close(fd)
    assert target.read_bytes() == b"created"


def test_read_fd_at_reads_offset(tmp_path: Path) -> None:
    target = tmp_path / "note.txt"
    target.write_bytes(b"abcdef")
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        assert read_fd_at(fd, 3, 2) == b"cde"
        assert os.lseek(fd, 0, os.SEEK_CUR) == 0
    finally:
        os.close(fd)


def test_sandbox_prepare_command_rejects_empty_argv(tmp_path: Path) -> None:
    info = detect_local_runtime_info()
    if info["sandbox"]["status"] in {"unsupported", "missing"}:
        pytest.skip("No Local process sandbox backend is available.")
    sandbox = create_process_sandbox()
    with pytest.raises(ValueError, match="sandbox command"):
        sandbox._prepare_command([], SandboxSpec(workspace=tmp_path))
