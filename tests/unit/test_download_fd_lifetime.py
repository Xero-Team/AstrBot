import asyncio
import os
from types import SimpleNamespace

import pytest

from astrbot.dashboard.api.data_files import _opened_file_response


def test_download_response_closes_fd_in_background(tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"payload")
    fd = os.open(path, os.O_RDONLY)
    opened = SimpleNamespace(
        fd=fd,
        content_type="application/octet-stream",
        entry={"name": "payload.bin", "size": path.stat().st_size},
    )

    response = _opened_file_response(
        opened,
        {
            "Content-Disposition": "attachment; filename=payload.bin",
            "Content-Length": str(path.stat().st_size),
        },
    )

    assert response.background is not None
    asyncio.run(response.background())
    with pytest.raises(OSError):
        os.fstat(fd)
