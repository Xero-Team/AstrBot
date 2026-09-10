from pathlib import Path

from starlette.datastructures import UploadFile


async def save_upload_to_path(
    upload_file: UploadFile,
    destination: str | Path,
    *,
    max_bytes: int | None = None,
) -> int:
    """Copy an upload to disk without exceeding an optional byte budget."""
    path = Path(destination)
    written = 0
    await upload_file.seek(0)
    with path.open("wb") as output:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if max_bytes is not None and written > max_bytes:
                raise ValueError("Upload exceeds configured byte limit")
            output.write(chunk)
    return written
