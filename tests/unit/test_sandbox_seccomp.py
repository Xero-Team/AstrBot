"""Host-independent seccomp BPF construction and checked installation."""

from __future__ import annotations

import errno
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from astrbot.core.computer.process_sandbox import seccomp


def test_filter_contains_arch_checks_and_expected_denials() -> None:
    program = seccomp.build_socket_filter(architecture=seccomp.AUDIT_ARCH_X86_64)
    values = [instruction.k for instruction in program.filters]
    assert seccomp.AUDIT_ARCH_X86_64 in values
    assert seccomp.X32_SYSCALL_BIT in values
    assert 41 in values
    assert 53 in values
    assert 425 in values
    assert seccomp.SECCOMP_RET_ALLOW in values
    assert any((value & 0xFFFF0000) == seccomp.SECCOMP_RET_ERRNO for value in values)
    assert program.pack().startswith(len(program.filters).to_bytes(2, "little"))


def test_filter_can_be_built_for_aarch64() -> None:
    program = seccomp.build_socket_filter(architecture=seccomp.AUDIT_ARCH_AARCH64)
    values = [instruction.k for instruction in program.filters]
    assert 198 in values
    assert 199 in values


def test_unsupported_architecture_fails_closed(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="does not support architecture"):
        seccomp.build_socket_filter(architecture=0xDEADBEEF)
    monkeypatch.setattr(seccomp.platform, "machine", lambda: "sparc")
    with pytest.raises(RuntimeError, match="does not support"):
        seccomp.current_audit_arch()
    with pytest.raises(RuntimeError):
        seccomp.install_socket_filter("deny")


def test_allow_all_does_not_install_a_filter() -> None:
    seccomp.install_socket_filter("allow_all")


def test_unknown_filter_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        seccomp.install_socket_filter("maybe")


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Seccomp installation requires Linux.",
)
def test_installed_filter_denies_unix_and_allows_inet() -> None:
    code = textwrap.dedent(
        """
        import socket
        import sys

        from astrbot.core.computer.process_sandbox.seccomp import install_socket_filter

        install_socket_filter("deny")
        for factory in (
            lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
            lambda: socket.socketpair(socket.AF_UNIX),
        ):
            try:
                factory()
            except OSError as exc:
                if exc.errno != 13:
                    raise AssertionError(exc.errno)
            else:
                raise AssertionError("Unix socket creation was not denied")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            pass
        print("filter-verified")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"filter-verified"
    assert errno.EACCES == 13
    assert os.name != "nt"
