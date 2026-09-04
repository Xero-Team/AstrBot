"""Exclusive lock for one AstrBot process per runtime data directory."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

LOCK_FILENAME = "astrbot.lock"
LOCK_TIMEOUT_SECONDS = 5.0


def runtime_instance_lock_path(data_dir: Path) -> Path:
    """Return the lock file path under a runtime data directory.

    Args:
        data_dir: The runtime ``data/`` directory.

    Returns:
        The absolute or relative lock path ``<data_dir>/astrbot.lock``.
    """
    return data_dir / LOCK_FILENAME


@contextmanager
def runtime_instance_lock(
    data_dir: Path,
    *,
    timeout: float | None = None,
) -> Iterator[None]:
    """Hold the exclusive instance lock for ``data_dir``.

    The caller supplies the data directory. This helper does not read
    ``ASTRBOT_ROOT`` or the current working directory.

    Args:
        data_dir: The runtime ``data/`` directory to own.
        timeout: Seconds to wait for the lock. ``None`` uses
            ``LOCK_TIMEOUT_SECONDS``.

    Yields:
        Nothing. The lock is held for the duration of the context.

    Raises:
        filelock.Timeout: If the lock cannot be acquired before ``timeout``.
    """
    if timeout is None:
        timeout = LOCK_TIMEOUT_SECONDS
    data_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(
        runtime_instance_lock_path(data_dir),
        timeout=timeout,
        fallback_to_soft=False,
    ):
        yield
