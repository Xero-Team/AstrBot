"""Race-resistant file opening for restricted Local computer tools."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import Literal, NoReturn


def _descriptor_relative_access_available() -> bool:
    return not (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or os.open not in os.supports_dir_fd
        or os.mkdir not in os.supports_dir_fd
    )


def _is_path_link(path: Path) -> bool:
    return path.is_symlink() or (os.name == "nt" and path.is_junction())


def _match_allowed_root(
    candidate: Path,
    allowed_roots: tuple[Path, ...],
    path: str,
) -> tuple[Path, tuple[str, ...]]:
    if not candidate.is_absolute():
        raise PermissionError(f"Restricted file path must be absolute: {path}.")

    root_matches: list[tuple[Path, Path]] = []
    for root in allowed_roots:
        try:
            root_matches.append((root, candidate.relative_to(root)))
        except ValueError:
            continue
    if not root_matches:
        raise PermissionError(
            f"Access denied: path is outside restricted roots: {path}."
        )

    root, relative_path = max(root_matches, key=lambda item: len(item[0].parts))
    parts = relative_path.parts
    if not parts:
        raise IsADirectoryError(path)
    if any(part in {"", ".", ".."} for part in parts):
        raise PermissionError(f"Access denied: unsafe restricted path: {path}.")
    return root, parts


def _access_file_flags(access: Literal["read", "write", "edit"]) -> int:
    if access == "read":
        return os.O_RDONLY
    if access == "write":
        return os.O_WRONLY
    if access == "edit":
        return os.O_RDWR
    raise ValueError(f"Unsupported restricted file access mode: {access}.")


def _validate_opened_file(file_fd: int, path: str) -> int:
    try:
        file_stat = os.fstat(file_fd)
    except OSError:
        os.close(file_fd)
        raise
    if not stat.S_ISREG(file_stat.st_mode):
        os.close(file_fd)
        if stat.S_ISDIR(file_stat.st_mode):
            raise IsADirectoryError(path)
        raise PermissionError(
            f"Access denied: restricted path is not a regular file: {path}."
        )
    if file_stat.st_nlink > 1:
        os.close(file_fd)
        raise PermissionError(
            "Access denied: file has multiple hard links and may alias content "
            f"outside allowed directories. Link count: {file_stat.st_nlink}. "
            f"Blocked path: {path}."
        )
    return file_fd


def read_fd_at(file_descriptor: int, size: int, offset: int) -> bytes:
    """Read bytes at an offset without requiring Unix ``os.pread``."""
    if hasattr(os, "pread"):
        return os.pread(file_descriptor, size, offset)
    current = os.lseek(file_descriptor, 0, os.SEEK_CUR)
    try:
        os.lseek(file_descriptor, offset, os.SEEK_SET)
        return os.read(file_descriptor, size)
    finally:
        os.lseek(file_descriptor, current, os.SEEK_SET)


def _raise_if_link(path: Path, original: str, *, root: bool = False) -> None:
    if not _is_path_link(path):
        return
    if root:
        raise PermissionError(
            f"Access denied: restricted root changed or is a symbolic link: {path}."
        )
    raise PermissionError(
        "Access denied: restricted path changed or contains a "
        f"symbolic link: {original}."
    )


def _ensure_compat_directory(path: Path, original: str, *, create: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if not create:
            raise
        try:
            path.mkdir(mode=0o755)
        except FileExistsError:
            pass
        info = path.lstat()
    _raise_if_link(path, original)
    if not stat.S_ISDIR(info.st_mode):
        raise PermissionError(
            "Access denied: restricted path changed or contains a "
            f"symbolic link: {original}."
        )


def _open_file_without_dir_fd(
    path: str,
    root: Path,
    parts: tuple[str, ...],
    *,
    access: Literal["read", "write", "edit"],
    create_parents: bool,
) -> int:
    current = root
    _raise_if_link(current, path, root=True)
    if not current.is_dir():
        raise PermissionError(
            f"Access denied: restricted root changed or is a symbolic link: {root}."
        )
    for component in parts[:-1]:
        current = current / component
        _ensure_compat_directory(current, path, create=create_parents)

    final_path = current / parts[-1]
    file_flags = _access_file_flags(access)
    file_flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        info = final_path.lstat()
    except FileNotFoundError:
        if not create_parents:
            raise
        try:
            file_fd = os.open(
                final_path,
                file_flags | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            _raise_if_link(final_path, path)
            file_fd = os.open(final_path, file_flags)
        return _validate_opened_file(file_fd, path)

    _raise_if_link(final_path, path)
    if not stat.S_ISREG(info.st_mode):
        if stat.S_ISDIR(info.st_mode):
            raise IsADirectoryError(path)
        raise PermissionError(
            f"Access denied: restricted path is not a regular file: {path}."
        )
    return _validate_opened_file(os.open(final_path, file_flags), path)


def _raise_if_link_oserror(exc: OSError, path: str) -> NoReturn:
    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
        raise PermissionError(
            "Access denied: restricted path changed or contains a "
            f"symbolic link: {path}."
        ) from exc
    raise exc


def _open_nofollow_directory(
    name: str,
    directory_fd: int,
    directory_flags: int,
    *,
    path: str,
    create: bool,
) -> int:
    try:
        return os.open(name, directory_flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, mode=0o755, dir_fd=directory_fd)
        except FileExistsError:
            pass  # Lost the create race; reopen the existing directory.
        try:
            return os.open(name, directory_flags, dir_fd=directory_fd)
        except OSError as exc:
            _raise_if_link_oserror(exc, path)
    except OSError as exc:
        _raise_if_link_oserror(exc, path)


def _open_nofollow_file(
    name: str,
    directory_fd: int,
    file_flags: int,
    *,
    path: str,
    create: bool,
) -> int:
    try:
        return os.open(name, file_flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            return os.open(
                name,
                file_flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
        except FileExistsError:
            try:
                return os.open(name, file_flags, dir_fd=directory_fd)
            except OSError as exc:
                _raise_if_link_oserror(exc, path)
    except OSError as exc:
        _raise_if_link_oserror(exc, path)


def open_file_in_allowed_roots(
    path: str,
    allowed_roots: tuple[Path, ...],
    *,
    access: Literal["read", "write", "edit"],
    create_parents: bool = False,
) -> int:
    """Open a regular file without following attacker-controlled path links.

    Args:
        path: Absolute normalized file path selected by the caller.
        allowed_roots: Trusted directories that may contain the file.
        access: Whether the descriptor is used for reading, writing, or editing.
        create_parents: Whether missing parent directories and the final file may
            be created.

    Returns:
        An open file descriptor owned by the caller.

    Raises:
        FileNotFoundError: If a required path component does not exist.
        IsADirectoryError: If the final path is a directory.
        PermissionError: If the path leaves the allowed roots, contains a symbolic
            link, is not a regular file, or aliases a multiply linked file.
        ValueError: If an unsupported access mode is requested.
    """
    root, parts = _match_allowed_root(Path(path), allowed_roots, path)
    if not _descriptor_relative_access_available():
        return _open_file_without_dir_fd(
            path,
            root,
            parts,
            access=access,
            create_parents=create_parents,
        )

    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_fd = os.open(root, directory_flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PermissionError(
                f"Access denied: restricted root changed or is a symbolic link: {root}."
            ) from exc
        raise

    try:
        for component in parts[:-1]:
            next_directory_fd = _open_nofollow_directory(
                component,
                directory_fd,
                directory_flags,
                path=path,
                create=create_parents,
            )
            os.close(directory_fd)
            directory_fd = next_directory_fd

        file_flags = _access_file_flags(access)
        file_flags |= (
            os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        file_fd = _open_nofollow_file(
            parts[-1],
            directory_fd,
            file_flags,
            path=path,
            create=create_parents,
        )
        return _validate_opened_file(file_fd, path)
    finally:
        os.close(directory_fd)
