"""Linux seccomp filter construction for sandbox socket denial.

The filter is installed in the workload branch immediately before ``exec``.
The unfiltered bridge is forked before this point, so it keeps the ability to
open Unix sockets for the lifetime of the sandbox.
"""

from __future__ import annotations

import ctypes
import errno
import platform
import struct
import sys
from dataclasses import dataclass

PR_SET_NO_NEW_PRIVS = 38
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2

SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_KILL_PROCESS = 0x80000000

BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_JGE = 0x30
BPF_K = 0x00
BPF_RET = 0x06

AUDIT_ARCH_X86_64 = 0xC000003E
AUDIT_ARCH_AARCH64 = 0xC00000B7

AF_UNIX = 1
AF_VSOCK = 40
X32_SYSCALL_BIT = 0x40000000

_SYSCALLS: dict[int, dict[str, int]] = {
    AUDIT_ARCH_X86_64: {
        "socket": 41,
        "socketpair": 53,
        "io_uring_setup": 425,
    },
    AUDIT_ARCH_AARCH64: {
        "socket": 198,
        "socketpair": 199,
        "io_uring_setup": 425,
    },
}
_CURRENT_ARCH: dict[str, int] = {
    "x86_64": AUDIT_ARCH_X86_64,
    "amd64": AUDIT_ARCH_X86_64,
    "aarch64": AUDIT_ARCH_AARCH64,
    "arm64": AUDIT_ARCH_AARCH64,
}


@dataclass(frozen=True, slots=True)
class SockFilter:
    """One classic BPF instruction."""

    code: int
    jt: int
    jf: int
    k: int

    def pack(self) -> bytes:
        """Return the native little-endian kernel representation."""
        return struct.pack("HBBI", self.code, self.jt, self.jf, self.k)


@dataclass(frozen=True, slots=True)
class SockFprog:
    """A BPF program header followed by instructions."""

    filters: tuple[SockFilter, ...]

    def pack(self) -> bytes:
        """Return the ``sock_fprog`` bytes accepted by ``prctl``."""
        return struct.pack("H", len(self.filters)) + b"".join(
            instruction.pack() for instruction in self.filters
        )


def _deny_errno() -> SockFilter:
    return SockFilter(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO | errno.EACCES)


def _allow() -> SockFilter:
    return SockFilter(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ALLOW)


def _load(offset: int) -> SockFilter:
    return SockFilter(BPF_LD | BPF_W | BPF_ABS, 0, 0, offset)


def _jump(code: int, value: int, *, jt: int, jf: int) -> SockFilter:
    return SockFilter(BPF_JMP | code | BPF_K, jt, jf, value)


def build_socket_filter(
    *,
    architecture: int | None = None,
    syscall_table: dict[str, int] | None = None,
) -> SockFprog:
    """Build a filter denying Unix sockets, socketpairs and io_uring.

    Args:
        architecture: ``AUDIT_ARCH_*`` value; defaults to the running platform.
        syscall_table: Optional per-architecture syscall numbers for tests.

    Returns:
        Validated filter program.

    Raises:
        RuntimeError: If the platform or architecture is unsupported.
    """
    arch = architecture if architecture is not None else current_audit_arch()
    numbers = syscall_table or _SYSCALLS.get(arch)
    if numbers is None:
        raise RuntimeError(
            f"Local sandbox socket filtering does not support architecture {arch:#x}."
        )
    arg0_offset = 16 if sys.byteorder == "little" else 20
    filters = [
        _load(4),
        _jump(BPF_JEQ, arch, jt=1, jf=0),
        _deny_errno(),
        _load(0),
        _jump(BPF_JGE, X32_SYSCALL_BIT, jt=0, jf=1),
        _deny_errno(),
        _jump(BPF_JEQ, numbers["socket"], jt=0, jf=5),
        _load(arg0_offset),
        _jump(BPF_JEQ, AF_UNIX, jt=2, jf=0),
        _jump(BPF_JEQ, AF_VSOCK, jt=1, jf=0),
        _allow(),
        _deny_errno(),
        _jump(BPF_JEQ, numbers["socketpair"], jt=0, jf=4),
        _load(arg0_offset),
        _jump(BPF_JEQ, AF_UNIX, jt=1, jf=0),
        _allow(),
        _deny_errno(),
        _jump(BPF_JEQ, numbers["io_uring_setup"], jt=0, jf=1),
        _deny_errno(),
        _allow(),
    ]
    return SockFprog(tuple(filters))


def current_audit_arch() -> int:
    """Return the audit architecture for the running interpreter.

    Raises:
        RuntimeError: If the host architecture is not supported.
    """
    machine = platform.machine().lower()
    arch = _CURRENT_ARCH.get(machine)
    if arch is None:
        raise RuntimeError(
            f"Local sandbox socket filtering does not support {machine!r}."
        )
    return arch


def install_socket_filter(mode: str) -> None:
    """Install the socket deny filter on the current process.

    Args:
        mode: ``deny`` installs the filter; ``allow_all`` is a no-op.

    Raises:
        ValueError: If ``mode`` is unknown.
        RuntimeError: If the platform or architecture is unsupported.
        OSError: If ``prctl`` rejects no-new-privs or the filter.
    """
    if mode == "allow_all":
        return
    if mode != "deny":
        raise ValueError(f"Unsupported socket filter mode: {mode}")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Local sandbox socket filtering requires Linux.")
    program = build_socket_filter()

    class _CtypesFilter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint),
        ]

    class _CtypesFprog(ctypes.Structure):
        _fields_ = [
            ("len", ctypes.c_ushort),
            ("filter", ctypes.POINTER(_CtypesFilter)),
        ]

    filters = (_CtypesFilter * len(program.filters))(
        *(
            _CtypesFilter(item.code, item.jt, item.jf, item.k)
            for item in program.filters
        )
    )
    fprog = _CtypesFprog(len(program.filters), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os_error_message(error))
    if (
        prctl(
            PR_SET_SECCOMP,
            SECCOMP_MODE_FILTER,
            ctypes.addressof(fprog),
            0,
            0,
        )
        != 0
    ):
        error = ctypes.get_errno()
        raise OSError(error, os_error_message(error))


def os_error_message(error: int) -> str:
    """Return a bounded message for a checked ``prctl`` failure."""
    try:
        import os

        return os.strerror(error)
    except ValueError, OverflowError:
        return f"prctl failed with errno {error}"


__all__ = (
    "AUDIT_ARCH_AARCH64",
    "AUDIT_ARCH_X86_64",
    "SECCOMP_RET_ALLOW",
    "SECCOMP_RET_ERRNO",
    "SockFprog",
    "SockFilter",
    "build_socket_filter",
    "current_audit_arch",
    "install_socket_filter",
)
