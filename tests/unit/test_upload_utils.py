import pytest
from starlette.datastructures import UploadFile

from astrbot.dashboard.upload_utils import (
    COPY_BLOCK_SIZE,
    UploadLimitError,
    save_upload_to_path,
)


class FakeUpload:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def seek(self, pos: int) -> int:
        self._pos = pos
        return self._pos

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._pos
        block = self._data[self._pos : self._pos + size]
        self._pos += len(block)
        return block


@pytest.mark.asyncio
async def test_save_upload_to_path_writes_all_bytes(tmp_path):
    data = b"x" * (COPY_BLOCK_SIZE * 2 + 123)
    dest = tmp_path / "out.bin"

    written = await save_upload_to_path(FakeUpload(data), dest, root=tmp_path)

    assert written == len(data)
    assert dest.read_bytes() == data


@pytest.mark.asyncio
async def test_save_upload_to_path_respects_max_bytes(tmp_path):
    data = b"x" * (COPY_BLOCK_SIZE + 1)
    dest = tmp_path / "out.bin"

    with pytest.raises(UploadLimitError):
        await save_upload_to_path(
            FakeUpload(data), dest, root=tmp_path, max_bytes=COPY_BLOCK_SIZE
        )

    assert not dest.exists()


@pytest.mark.asyncio
async def test_save_upload_to_path_preserves_existing_dest_on_failure(tmp_path):
    dest = tmp_path / "out.bin"
    dest.write_bytes(b"original")

    with pytest.raises(UploadLimitError):
        await save_upload_to_path(
            FakeUpload(b"x" * (COPY_BLOCK_SIZE + 1)),
            dest,
            root=tmp_path,
            max_bytes=COPY_BLOCK_SIZE,
        )

    assert dest.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.asyncio
async def test_save_upload_to_path_allows_exact_limit(tmp_path):
    data = b"x" * COPY_BLOCK_SIZE
    dest = tmp_path / "out.bin"

    written = await save_upload_to_path(
        FakeUpload(data), dest, root=tmp_path, max_bytes=COPY_BLOCK_SIZE
    )

    assert written == COPY_BLOCK_SIZE
    assert dest.read_bytes() == data


@pytest.mark.asyncio
async def test_save_upload_to_path_accepts_starlette_upload(tmp_path):
    from io import BytesIO

    upload = UploadFile(file=BytesIO(b"upload-bytes"), filename="demo.txt")
    dest = tmp_path / "demo.txt"
    await save_upload_to_path(upload, dest, root=tmp_path)
    assert dest.read_bytes() == b"upload-bytes"
