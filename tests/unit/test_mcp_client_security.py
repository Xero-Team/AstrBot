import socket

import httpx
import pytest

from astrbot.core.agent.mcp_client import (
    _create_mcp_http_client_without_redirects,
    _validate_remote_url,
)


def test_validate_remote_url_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="private or local IP addresses"):
        _validate_remote_url("http://localhost:8000/mcp")


def test_validate_remote_url_rejects_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 80))
        ],
    )

    with pytest.raises(ValueError, match="private or local IP addresses"):
        _validate_remote_url("https://public.example/mcp")


@pytest.mark.asyncio
async def test_create_mcp_http_client_without_redirects_disables_redirects() -> None:
    client = _create_mcp_http_client_without_redirects(
        headers={"X-Test": "1"},
        timeout=httpx.Timeout(5.0),
    )
    try:
        assert client.follow_redirects is False
        assert client.headers["X-Test"] == "1"
    finally:
        await client.aclose()
