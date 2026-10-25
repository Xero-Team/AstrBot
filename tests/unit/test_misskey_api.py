from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.misskey import misskey_api
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

    assert (
        await api._download_file_bytes("https://misskey.example/files/test.png")
        == b"file"
    )

    api._download_with_existing_session.assert_awaited_once_with(
        "https://misskey.example/files/test.png",
        ssl_verify=True,
    )
    api._download_with_temp_session.assert_awaited_once_with(
        "https://misskey.example/files/test.png"
    )


@pytest.mark.asyncio
async def test_download_file_bytes_skips_the_temp_session_on_success():
    api = MisskeyAPI(
        "https://misskey.example",
        "token",
    )
    api._download_with_existing_session = AsyncMock(return_value=b"file")
    api._download_with_temp_session = AsyncMock()

    assert (
        await api._download_file_bytes("https://misskey.example/files/test.png")
        == b"file"
    )

    api._download_with_temp_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_file_bytes_never_sends_credentials_to_another_host():
    api = MisskeyAPI(
        "https://misskey.example",
        "token",
    )
    api._download_with_existing_session = AsyncMock(return_value=b"leaked")
    api._download_with_temp_session = AsyncMock(return_value=b"file")

    assert await api._download_file_bytes("https://files.example/test.png") == b"file"

    api._download_with_existing_session.assert_not_awaited()
    api._download_with_temp_session.assert_awaited_once_with(
        "https://files.example/test.png"
    )


@pytest.mark.asyncio
async def test_temp_session_uses_outbound_policy(monkeypatch: pytest.MonkeyPatch):
    api = MisskeyAPI("https://misskey.example", "token", max_download_bytes=4096)
    captured = {}

    async def fake_download(url: str, path: Path, policy) -> None:
        captured["url"] = url
        captured["policy"] = policy
        path.write_bytes(b"file")

    monkeypatch.setattr(misskey_api, "download_to_path", fake_download)

    assert (
        await api._download_with_temp_session("https://files.example/test.png")
        == b"file"
    )

    policy = captured["policy"]
    assert policy.allowed_schemes == frozenset({"http", "https"})
    assert policy.allow_private_network is False
    assert policy.max_redirects == 0
    assert policy.max_response_bytes == 4096
