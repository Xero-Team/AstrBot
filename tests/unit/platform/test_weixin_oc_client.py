from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot import __version__
from astrbot.core.platform.sources.weixin_oc.weixin_oc_client import (
    ILINK_APP_ID,
    WeixinOCClient,
    build_base_info,
)

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
        full_url="https://cdn.example/download-full",
    )

    assert content == b"media"
    session.get.assert_called_once()
    assert session.get.call_args.args[0] == "https://cdn.example/download-full"


@pytest.mark.asyncio
async def test_upload_to_cdn_retries_server_error_then_succeeds(tmp_path):
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
        "https://cdn.example/upload",
        "",
        "filekey",
        "0" * 32,
        media_path,
    )

    assert download_param == "download-param"
    assert session.post.call_count == 2
