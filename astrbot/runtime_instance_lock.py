"""Exclusive lock for one AstrBot process per runtime data directory."""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

try:
    import fcntl
except ImportError:
    fcntl = None

LOCK_FILENAME = "astrbot.lock"
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_POLL_INTERVAL_SECONDS = 0.05
_UNSUPPORTED_FLOCK_ERRNOS = {errno.ENOSYS, errno.EOPNOTSUPP}


class RuntimeInstanceLockHeld(Exception):
    """Raised when another process already owns the runtime data directory."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        super().__init__(
            f"Cannot acquire lock file at {self.lock_path}. "
            "Please check if another instance is running"
        )


def runtime_instance_lock_path(data_dir: Path) -> Path:
    """Return the lock file path under a runtime data directory.

    Args:
        data_dir: The runtime ``data/`` directory.

    Returns:
        The absolute or relative lock path ``<data_dir>/astrbot.lock``.
    """
    return data_dir / LOCK_FILENAME


def directory_lock_supported() -> bool:
    """Return whether this platform can flock the data directory.

    Returns:
        ``True`` when ``fcntl.flock`` is available.
    """
    return fcntl is not None and hasattr(fcntl, "flock")


def _acquire_data_dir_lock(data_dir: Path, timeout: float) -> int | None:
    """Flock ``data_dir`` so replacing ``astrbot.lock`` cannot admit another owner.

    Args:
        data_dir: The runtime ``data/`` directory.
        timeout: Seconds to wait for the directory lock.

    Returns:
        A held directory file descriptor, or ``None`` when flock is unavailable
        or unsupported on this filesystem.

    Raises:
        BlockingIOError: If another process holds the directory lock until
            ``timeout`` elapses.
        OSError: For flock errors other than timeout or missing kernel support.
    """
    if fcntl is None:
        return None
    flock = getattr(fcntl, "flock", None)
    lock_ex = getattr(fcntl, "LOCK_EX", None)
    lock_nb = getattr(fcntl, "LOCK_NB", None)
    if flock is None or lock_ex is None or lock_nb is None:
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(data_dir, flags)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                flock(fd, lock_ex | lock_nb)
                return fd
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if timeout <= 0 or remaining <= 0:
                    raise
                time.sleep(min(LOCK_POLL_INTERVAL_SECONDS, remaining))
            except OSError as exc:
                if exc.errno in _UNSUPPORTED_FLOCK_ERRNOS:
                    os.close(fd)
                    return None
                raise
    except Exception:
        os.close(fd)
        raise


def _release_data_dir_lock(dir_fd: int) -> None:
    flock = getattr(fcntl, "flock", None) if fcntl is not None else None
    lock_un = getattr(fcntl, "LOCK_UN", None) if fcntl is not None else None
    if flock is not None and lock_un is not None:
        try:
            flock(dir_fd, lock_un)
        except OSError:
            pass
    os.close(dir_fd)


@contextmanager
def runtime_instance_lock(
    data_dir: Path,
    *,
    timeout: float | None = None,
) -> Iterator[None]:
    """Hold the exclusive instance lock for ``data_dir``.

    The caller supplies the data directory. This helper does not read
    ``ASTRBOT_ROOT`` or the current working directory. Acquisition failure
    is raised as ``RuntimeInstanceLockHeld``; later ``filelock.Timeout``
    errors from the held section propagate unchanged.

    On POSIX, the helper also flocks ``data_dir`` itself so unlinking
    ``astrbot.lock`` cannot hand the singleton to a second process.

    Args:
        data_dir: The runtime ``data/`` directory to own.
        timeout: Seconds to wait for the lock. ``None`` uses
            ``LOCK_TIMEOUT_SECONDS``.

    Yields:
        Nothing. The lock is held for the duration of the context.

    Raises:
        RuntimeInstanceLockHeld: If the lock cannot be acquired before
            ``timeout``.
    """
    if timeout is None:
        timeout = LOCK_TIMEOUT_SECONDS
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_instance_lock_path(data_dir)
    lock = FileLock(
        lock_path,
        timeout=timeout,
        fallback_to_soft=False,
        preserve_lock_file=True,
    )
    acquired = False
    dir_fd: int | None = None
    try:
        try:
            lock.acquire()
        except Timeout as exc:
            raise RuntimeInstanceLockHeld(lock_path) from exc
        acquired = True
        try:
            dir_fd = _acquire_data_dir_lock(data_dir, timeout=timeout)
        except BlockingIOError as exc:
            raise RuntimeInstanceLockHeld(lock_path) from exc
        yield
    finally:
        if dir_fd is not None:
            _release_data_dir_lock(dir_fd)
        if acquired:
            lock.release()
