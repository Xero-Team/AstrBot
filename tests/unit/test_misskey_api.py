from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.misskey.misskey_api import MisskeyAPI


@pytest.mark.asyncio
async def test_download_file_bytes_always_verifies_tls():
    api = MisskeyAPI(
        "https://misskey.example",
        "token",
    )
    api._download_with_existing_session = AsyncMock(
        side_effect=RuntimeError("ssl failed")
    )
    api._download_with_temp_session = AsyncMock(return_value=b"file")

    assert await api._download_file_bytes("https://files.example/test.png") == b"file"

    api._download_with_existing_session.assert_awaited_once_with(
        "https://files.example/test.png",
        ssl_verify=True,
    )
    api._download_with_temp_session.assert_awaited_once_with(
        "https://files.example/test.png",
        ssl_verify=True,
    )


@pytest.mark.asyncio
async def test_download_file_bytes_skips_the_temp_session_on_success():
    api = MisskeyAPI(
        "https://misskey.example",
        "token",
    )
    api._download_with_existing_session = AsyncMock(return_value=b"file")
    api._download_with_temp_session = AsyncMock()

    assert await api._download_file_bytes("https://files.example/test.png") == b"file"

    api._download_with_temp_session.assert_not_awaited()
