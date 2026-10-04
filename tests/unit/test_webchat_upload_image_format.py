from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage

from astrbot.dashboard.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_webchat_upload_uses_detected_image_type(tmp_path):
    image_buffer = BytesIO()
    PILImage.new("RGB", (2, 2), (255, 0, 0)).save(image_buffer, format="JPEG")

    class FakeUploadFile:
        filename = "pasted.png"
        content_type = "image/png"

        def __init__(self):
            self._payload = image_buffer.getvalue()
            self._offset = 0

        async def seek(self, offset):
            self._offset = offset

        async def read(self, size=-1):
            if size < 0:
                size = len(self._payload) - self._offset
            chunk = self._payload[self._offset : self._offset + size]
            self._offset += len(chunk)
            return chunk

    class FakeDatabase:
        def __init__(self):
            self.inserted = None

        async def insert_attachment(self, path, type, mime_type):
            self.inserted = {
                "path": path,
                "type": type,
                "mime_type": mime_type,
            }
            return SimpleNamespace(attachment_id="attachment-1", path=path)

    fake_db = FakeDatabase()
    service = ChatService.__new__(ChatService)
    service.db = fake_db
    service.attachments_dir = str(tmp_path)

    result = await service.save_uploaded_file(FakeUploadFile())

    assert result["filename"] == "pasted.jpg"
    assert fake_db.inserted["mime_type"] == "image/jpeg"
    assert fake_db.inserted["type"] == "image"
    assert result["stored_filename"].endswith("_pasted.jpg")
    assert (tmp_path / result["stored_filename"]).exists()
    assert not list(tmp_path.glob("*.png"))
