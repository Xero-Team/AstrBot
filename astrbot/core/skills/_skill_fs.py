from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath

MAX_SKILL_FILE_BYTES = 64 * 1024
MAX_SKILL_SNAPSHOT_FILES = 32
MAX_SKILL_SNAPSHOT_BYTES = 256 * 1024
TRUNCATION_NOTE = (
    "\n\n[truncated at 64 KiB; pass a relative path to read a referenced file]"
)


def read_nofollow_capped(root: Path, relative_path: str) -> str:
    """Read one regular file under ``root`` without following symlinks."""
    parts = PurePosixPath(relative_path).parts
    fd = open_nofollow_under(root, parts)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular file")
        if not opened_path_is_under(fd, root, root / relative_path):
            raise OSError("opened path escaped snapshot root")
        data = read_fd_capped(fd)
    finally:
        os.close(fd)
    return decode_skill_bytes(data)


def list_regular_skill_files(root: Path) -> tuple[str, ...]:
    """Return POSIX-relative regular files under ``root``, skipping symlinks."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name for name in dirnames if not (current / name).is_symlink()
        )
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink() or not path.is_file():
                continue
            files.append(path.relative_to(root).as_posix())
    files.sort(key=lambda item: (item != "SKILL.md", item))
    return tuple(files)


def open_nofollow_under(root: Path, parts: tuple[str, ...]) -> int:
    if not parts:
        raise OSError("empty path")
    if os.name != "nt":
        try:
            return _open_nofollow_dirfd(root, parts)
        except NotImplementedError:
            pass
    return _open_nofollow_portable(root, parts)


def read_fd_capped(fd: int) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_SKILL_FILE_BYTES + 1
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def decode_skill_bytes(data: bytes) -> str:
    truncated = len(data) > MAX_SKILL_FILE_BYTES
    payload = data[:MAX_SKILL_FILE_BYTES]
    text = payload.decode("utf-8", errors="replace")
    if truncated:
        return f"{text}{TRUNCATION_NOTE}"
    return text


def opened_path_is_under(fd: int, root: Path, fallback: Path) -> bool:
    resolved_root = os.path.realpath(root)
    opened = path_from_fd(fd)
    if opened:
        return _is_under_root(opened, resolved_root)
    if fallback.is_symlink():
        return False
    try:
        opened_stat = os.fstat(fd)
        fallback_stat = os.stat(fallback, follow_symlinks=False)
        root_stat = os.stat(resolved_root, follow_symlinks=False)
    except OSError:
        return False
    if not _same_file(opened_stat, fallback_stat):
        return False
    if not _is_under_root(os.path.realpath(fallback), resolved_root):
        return False
    return opened_stat.st_dev == root_stat.st_dev


def path_from_fd(fd: int) -> str | None:
    if os.name == "nt":
        return None
    proc_path = Path(f"/proc/self/fd/{fd}")
    if proc_path.exists():
        try:
            return os.path.realpath(proc_path)
        except OSError:
            return None
    return None


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_ino == right.st_ino and left.st_dev == right.st_dev


def _open_nofollow_dirfd(root: Path, parts: tuple[str, ...]) -> int:
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not directory:
        raise NotImplementedError("O_DIRECTORY unavailable")
    root_flags = os.O_RDONLY | cloexec | directory
    dir_flags = os.O_RDONLY | cloexec | directory | nofollow
    file_flags = os.O_RDONLY | cloexec | nofollow
    dirfd = os.open(root, root_flags)
    try:
        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            flags = file_flags if is_last else dir_flags
            next_fd = os.open(part, flags, dir_fd=dirfd)
            os.close(dirfd)
            dirfd = next_fd
        return dirfd
    except OSError:
        os.close(dirfd)
        raise


def _open_nofollow_portable(root: Path, parts: tuple[str, ...]) -> int:
    current = root
    if current.is_symlink() or not current.is_dir():
        raise OSError("skill root is not a real directory")
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            raise OSError("symlink rejected")
        is_last = index == len(parts) - 1
        if is_last:
            if not current.is_file():
                raise OSError("not a regular file")
            cloexec = getattr(os, "O_CLOEXEC", 0)
            return os.open(current, os.O_RDONLY | cloexec)
        if not current.is_dir():
            raise OSError("not a directory")
    raise OSError("empty path")


def _is_under_root(path: str, resolved_root: str) -> bool:
    prefix = resolved_root if resolved_root.endswith(os.sep) else resolved_root + os.sep
    return path == resolved_root or path.startswith(prefix)
