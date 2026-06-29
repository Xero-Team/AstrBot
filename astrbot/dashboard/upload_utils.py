from pathlib import Path

from starlette.datastructures import UploadFile


async def save_upload_to_path(upload_file: UploadFile, destination: str | Path) -> None:
    path = Path(destination)
    await upload_file.seek(0)
    with path.open("wb") as output:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
