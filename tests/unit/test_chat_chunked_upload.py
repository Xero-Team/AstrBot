from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.dashboard.services.chat_service import (
    MAX_UPLOAD_FILE_SIZE_BYTES,
    ChatService,
    ChatServiceError,
)
from astrbot.dashboard.services.chunked_upload_service import ChunkedUploadService
from astrbot.dashboard.upload_utils import UploadLimitError

CHUNK_SIZE = 1024 * 1024


class _StubChunk:
    def __init__(self, data: bytes):
        self._data = data

    async def save(self, destination, *, max_bytes=None):
        if max_bytes is not None and len(self._data) > max_bytes:
            raise UploadLimitError(max_bytes)
        Path(destination).write_bytes(self._data)
        return len(self._data)


@pytest.fixture
def service(tmp_path):
    db = SimpleNamespace(inserted=None)

    async def insert_attachment(path, type, mime_type):
        db.inserted = {"path": path, "type": type, "mime_type": mime_type}
        return SimpleNamespace(attachment_id="att-1", path=path)

    db.insert_attachment = insert_attachment
    svc = ChatService.__new__(ChatService)
    svc.db = db
    svc.attachments_dir = str(tmp_path / "attachments")
    Path(svc.attachments_dir).mkdir(parents=True, exist_ok=True)
    svc.chunked_uploads = ChunkedUploadService(tmp_path / "webchat" / ".chunks")
    yield svc
    task = svc.chunked_uploads._cleanup_task
    if task is not None and not task.done():
        task.cancel()


class TestChatChunkedUpload:
    def test_upload_init_validates_input(self, service):
        session = service.upload_init(
            {"filename": "report.pdf", "total_size": CHUNK_SIZE * 2 + 100},
            owner="alice",
        )
        assert session["chunk_size"] == CHUNK_SIZE
        assert session["total_chunks"] == 3
        assert session["upload_id"]

        with pytest.raises(ChatServiceError, match="Missing key: filename"):
            service.upload_init({"total_size": 100}, owner="alice")
        with pytest.raises(ChatServiceError, match="Invalid file size"):
            service.upload_init({"filename": "a.txt", "total_size": 0}, owner="alice")
        with pytest.raises(ChatServiceError, match="File too large"):
            service.upload_init(
                {"filename": "a.bin", "total_size": MAX_UPLOAD_FILE_SIZE_BYTES + 1},
                owner="alice",
            )

    @pytest.mark.asyncio
    async def test_full_flow_merges_and_creates_attachment(self, service):
        part0 = b"x" * CHUNK_SIZE
        part1 = b"y" * 100
        session = service.upload_init(
            {
                "filename": "notes.txt",
                "total_size": len(part0) + len(part1),
                "content_type": "text/plain",
            },
            owner="alice",
        )
        upload_id = session["upload_id"]

        await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="1",
            chunk_file=_StubChunk(part1),
            owner="alice",
        )
        await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubChunk(part0),
            owner="alice",
        )

        result = await service.upload_complete({"upload_id": upload_id}, owner="alice")

        assert result["attachment_id"] == "att-1"
        assert result["type"] == "file"
        assert service.db.inserted["mime_type"] == "text/plain"
        merged = Path(service.db.inserted["path"])
        assert merged.read_bytes() == part0 + part1
        assert not service.chunked_uploads.sessions
        assert not list(service.chunked_uploads.chunks_root.iterdir())

    @pytest.mark.asyncio
    async def test_sessions_bound_to_owner(self, service):
        session = service.upload_init(
            {"filename": "a.txt", "total_size": 100}, owner="alice"
        )
        upload_id = session["upload_id"]

        with pytest.raises(ChatServiceError, match="not found or expired"):
            await service.upload_chunk(
                upload_id=upload_id,
                chunk_index_str="0",
                chunk_file=_StubChunk(b"x" * 100),
                owner="mallory",
            )
        with pytest.raises(ChatServiceError, match="not found or expired"):
            service.upload_status({"upload_id": upload_id}, owner="mallory")
        with pytest.raises(ChatServiceError, match="not found or expired"):
            await service.upload_complete({"upload_id": upload_id}, owner="mallory")
        with pytest.raises(ChatServiceError, match="not found or expired"):
            await service.upload_abort({"upload_id": upload_id}, owner="mallory")

        result = await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubChunk(b"x" * 100),
            owner="alice",
        )
        assert result["received"] == 1

    @pytest.mark.asyncio
    async def test_status_reports_progress_without_extending_lifetime(self, service):
        session = service.upload_init(
            {"filename": "a.txt", "total_size": CHUNK_SIZE * 2}, owner="alice"
        )
        upload_id = session["upload_id"]
        await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="1",
            chunk_file=_StubChunk(b"x" * CHUNK_SIZE),
            owner="alice",
        )

        inner = service.chunked_uploads.get_session(upload_id, owner="alice")
        inner.last_activity -= 100
        status = service.upload_status({"upload_id": upload_id}, owner="alice")

        assert status["received_chunks"] == [1]
        assert status["total_chunks"] == 2
        assert status["expires_in"] <= 3600 - 100 + 1
        assert (
            service.chunked_uploads.get_session(upload_id, owner="alice").last_activity
            == inner.last_activity
        )

    @pytest.mark.asyncio
    async def test_complete_rejects_missing_chunks(self, service):
        session = service.upload_init(
            {"filename": "a.txt", "total_size": CHUNK_SIZE + 1}, owner="alice"
        )
        upload_id = session["upload_id"]
        await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubChunk(b"x" * CHUNK_SIZE),
            owner="alice",
        )

        with pytest.raises(ChatServiceError, match="Chunks incomplete"):
            await service.upload_complete({"upload_id": upload_id}, owner="alice")

    @pytest.mark.asyncio
    async def test_abort_cleans_up_session(self, service):
        session = service.upload_init(
            {"filename": "a.txt", "total_size": 100}, owner="alice"
        )
        upload_id = session["upload_id"]
        await service.upload_chunk(
            upload_id=upload_id,
            chunk_index_str="0",
            chunk_file=_StubChunk(b"x" * 100),
            owner="alice",
        )

        await service.upload_abort({"upload_id": upload_id}, owner="alice")

        with pytest.raises(ChatServiceError, match="not found or expired"):
            service.upload_status({"upload_id": upload_id}, owner="alice")
        assert not list(service.chunked_uploads.chunks_root.iterdir())
        await service.upload_abort({"upload_id": upload_id}, owner="alice")
