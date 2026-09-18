import os
from pathlib import Path

from starlette.datastructures import UploadFile


class UploadLimitError(ValueError):
    """The upload exceeded the optional byte budget."""


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
    """Copy an upload to disk without exceeding an optional byte budget."""
    fullpath = _confine_upload_path(destination, root)
    written = 0
    await upload_file.seek(0)
    try:
        with open(fullpath, "wb") as output:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if max_bytes is not None and written > max_bytes:
                    raise UploadLimitError("Upload exceeds configured byte limit")
                output.write(chunk)
    except BaseException:
        try:
            os.unlink(fullpath)
        except FileNotFoundError:
            pass
        raise
    return written
