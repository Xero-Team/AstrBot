from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from astrbot import __version__
from astrbot.core.platform.sources.weixin_oc.weixin_oc_client import (
    ILINK_APP_ID,
    WeixinOCClient,
    build_base_info,
    is_allowed_weixin_https_url,
    resolve_weixin_https_base_url,
)

WEIXIN_CDN_UPLOAD = "https://novac2c.cdn.weixin.qq.com/c2c/upload"
WEIXIN_CDN_DOWNLOAD = "https://novac2c.cdn.weixin.qq.com/c2c/download-full"

pytestmark = pytest.mark.platform


def _client() -> WeixinOCClient:
    return WeixinOCClient(
        adapter_id="weixin-oc-test",
        base_url="https://ilinkai.weixin.qq.com",
        cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
        api_timeout_ms=15_000,
        token="bot-token",
    )


def test_build_base_info_includes_version_and_bot_agent():
    info = build_base_info()
    assert info["channel_version"] == __version__
    assert info["bot_agent"] == f"AstrBot/{__version__}"


def test_authenticated_headers_include_ilink_app_fields():
    client = _client()
    headers = client._build_base_headers(token_required=True)
    assert headers["iLink-App-Id"] == ILINK_APP_ID
    assert headers["iLink-App-ClientVersion"] == client.client_version
    assert headers["Authorization"] == "Bearer bot-token"
    assert headers["AuthorizationType"] == "ilink_bot_token"


def test_qr_status_headers_omit_authorization():
    client = _client()
    headers = client._build_base_headers(
        token_required=False,
        include_auth_headers=False,
    )
    assert headers == {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": client.client_version,
    }


@pytest.mark.asyncio
async def test_download_cdn_bytes_prefers_full_url():
    client = _client()
    response = AsyncMock()
    response.status = 200
    response.read = AsyncMock(return_value=b"media")
    response.__aenter__.return_value = response
    response.__aexit__.return_value = False
    session = MagicMock()
    session.closed = False
    session.get.return_value = response
    client._http_session = session

    content = await client.download_cdn_bytes(
        "enc-query",
        full_url=WEIXIN_CDN_DOWNLOAD,
    )

    assert content == b"media"
    session.get.assert_called_once()
    assert session.get.call_args.args[0] == WEIXIN_CDN_DOWNLOAD
    assert session.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.asyncio
async def test_upload_to_cdn_retries_server_error_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "astrbot.core.platform.sources.weixin_oc.weixin_oc_client.asyncio.sleep",
        AsyncMock(),
    )
    client = _client()
    media_path = tmp_path / "image.bin"
    media_path.write_bytes(b"hello-image")

    fail_response = AsyncMock()
    fail_response.status = 500
    fail_response.text = AsyncMock(return_value="busy")
    fail_response.headers = {}
    fail_response.__aenter__.return_value = fail_response
    fail_response.__aexit__.return_value = False

    ok_response = AsyncMock()
    ok_response.status = 200
    ok_response.text = AsyncMock(return_value="")
    ok_response.headers = {"x-encrypted-param": "download-param"}
    ok_response.__aenter__.return_value = ok_response
    ok_response.__aexit__.return_value = False

    session = MagicMock()
    session.closed = False
    session.post.side_effect = [fail_response, ok_response]
    client._http_session = session

    download_param = await client.upload_to_cdn(
        WEIXIN_CDN_UPLOAD,
        "",
        "filekey",
        "0" * 32,
        media_path,
    )

    assert download_param == "download-param"
    assert session.post.call_count == 2


def test_weixin_https_url_allowlist():
    assert is_allowed_weixin_https_url(WEIXIN_CDN_UPLOAD) is True
    assert is_allowed_weixin_https_url("https://evil.example/x") is False
    assert is_allowed_weixin_https_url("http://ilinkai.weixin.qq.com") is False
    assert resolve_weixin_https_base_url("ilink-b.weixin.qq.com") == (
        "https://ilink-b.weixin.qq.com"
    )
    assert resolve_weixin_https_base_url("https://evil.example") is None
    assert resolve_weixin_https_base_url("http://ilinkai.weixin.qq.com") is None


@pytest.mark.asyncio
async def test_download_cdn_bytes_falls_back_when_full_url_is_not_weixin():
    client = _client()
    response = AsyncMock()
    response.status = 200
    response.read = AsyncMock(return_value=b"media")
    response.__aenter__.return_value = response
    response.__aexit__.return_value = False
    session = MagicMock()
    session.closed = False
    session.get.return_value = response
    client._http_session = session

    content = await client.download_cdn_bytes(
        "enc-query",
        full_url="https://evil.example/steal",
    )

    assert content == b"media"
    requested = session.get.call_args.args[0]
    assert requested.startswith("https://novac2c.cdn.weixin.qq.com/c2c/download")
    assert "evil.example" not in requested


@pytest.mark.asyncio
async def test_upload_to_cdn_does_not_retry_client_error_4xx(tmp_path):
    client = _client()
    media_path = tmp_path / "image.bin"
    media_path.write_bytes(b"hello-image")

    fail_response = AsyncMock()
    fail_response.status = 400
    fail_response.text = AsyncMock(return_value="bad")
    fail_response.headers = {}
    fail_response.__aenter__.return_value = fail_response
    fail_response.__aexit__.return_value = False

    session = MagicMock()
    session.closed = False
    session.post.return_value = fail_response
    client._http_session = session

    with pytest.raises(RuntimeError, match="400"):
        await client.upload_to_cdn(
            WEIXIN_CDN_UPLOAD,
            "",
            "filekey",
            "0" * 32,
            media_path,
        )

    assert session.post.call_count == 1


@pytest.mark.asyncio
async def test_upload_to_cdn_retries_transport_error(tmp_path, monkeypatch):
    client = _client()
    media_path = tmp_path / "image.bin"
    media_path.write_bytes(b"hello-image")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.weixin_oc.weixin_oc_client.asyncio.sleep",
        AsyncMock(),
    )

    ok_response = AsyncMock()
    ok_response.status = 200
    ok_response.text = AsyncMock(return_value="")
    ok_response.headers = {"x-encrypted-param": "download-param"}
    ok_response.__aenter__.return_value = ok_response
    ok_response.__aexit__.return_value = False

    session = MagicMock()
    session.closed = False
    session.post.side_effect = [aiohttp.ClientConnectionError("down"), ok_response]
    client._http_session = session

    download_param = await client.upload_to_cdn(
        WEIXIN_CDN_UPLOAD,
        "",
        "filekey",
        "0" * 32,
        media_path,
    )

    assert download_param == "download-param"
    assert session.post.call_count == 2
