import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from starlette.datastructures import UploadFile

COPY_BLOCK_SIZE = 1024 * 1024


class UploadLimitError(ValueError):
    """The upload exceeded the optional byte budget."""

    def __init__(self, max_bytes: int | None = None) -> None:
        if max_bytes is None:
            super().__init__("Upload exceeds configured byte limit")
        else:
            super().__init__(
                f"Upload exceeds configured byte limit ({max_bytes} bytes)"
            )
        self.max_bytes = max_bytes


class UploadPathError(ValueError):
    """The destination is outside the allowed upload root."""


def _confine_upload_path(destination: str | Path, root: str | Path) -> str:
    base_path = os.path.normpath(str(root))
    fullpath = os.path.normpath(os.path.join(base_path, str(destination)))
    if not fullpath.startswith(base_path):
        raise UploadPathError("Upload destination escapes configured root")
    if fullpath != base_path and not fullpath.startswith(base_path + os.sep):
        raise UploadPathError("Upload destination escapes configured root")
    return fullpath


async def save_upload_to_path(
    upload_file: UploadFile,
    destination: str | Path,
    *,
    root: str | Path,
    max_bytes: int | None = None,
) -> int:
    """Copy an upload to disk without exceeding an optional byte budget.

    The payload lands in a uniquely named sibling temp file and is
    atomically renamed to ``destination`` only after the complete stream
    succeeds, so a failed or cancelled save never destroys a pre-existing
    destination.

    Args:
        upload_file: Starlette upload exposing async ``read(size)``.
        destination: Destination file path, relative to ``root`` or absolute
            under ``root``.
        root: Allowed destination root.
        max_bytes: Optional hard limit. When the upload exceeds it, the
            partial temp file is removed and UploadLimitError is raised.

    Returns:
        Number of bytes written.

    Raises:
        UploadLimitError: The upload exceeded ``max_bytes``.
        UploadPathError: The destination is outside ``root``.
    """
    fullpath = _confine_upload_path(destination, root)
    path = Path(fullpath)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    written = 0
    await upload_file.seek(0)
    try:
        with temp_path.open("wb") as output:
            while True:
                chunk = await upload_file.read(COPY_BLOCK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise UploadLimitError(max_bytes)
                output.write(chunk)
        await asyncio.to_thread(os.replace, temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return written


class UploadFileAdapter:
    """Give a Starlette UploadFile the streaming ``save()`` contract."""

    def __init__(self, upload_file: UploadFile) -> None:
        self._upload_file = upload_file
        self.filename = upload_file.filename
        self.content_type = upload_file.content_type
        self.size = getattr(upload_file, "size", None)

    async def save(
        self,
        destination: str | Path,
        *,
        max_bytes: int | None = None,
        root: str | Path | None = None,
    ) -> int:
        dest = Path(destination)
        confined_root = root if root is not None else dest.parent
        return await save_upload_to_path(
            self._upload_file,
            dest,
            root=confined_root,
            max_bytes=max_bytes,
        )

    async def read(self, size: int = -1) -> bytes:
        return await self._upload_file.read(size)

    async def seek(self, offset: int) -> None:
        await self._upload_file.seek(offset)

    def __getattr__(self, key: str) -> Any:
        return getattr(self._upload_file, key)
