import asyncio
import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.lark.server import LarkWebhookServer


class _FakeRequest:
    def __init__(
        self, body: bytes, event_data: dict, headers: dict | None = None
    ) -> None:
        self._body = body
        self._event_data = event_data
        self.headers = headers or {}

    async def get_data(self) -> bytes:
        return self._body

    @property
    async def json(self) -> dict:
        return self._event_data


@pytest.mark.asyncio
async def test_lark_webhook_rejects_missing_signature_headers_when_encrypt_key_enabled():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={},
        )
    )

    assert result == ({"error": "Missing signature headers"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_rejects_invalid_signature_when_encrypt_key_enabled():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": str(int(time.time())),
                "X-Lark-Request-Nonce": "2",
                "X-Lark-Signature": "bad-signature",
            },
        )
    )

    assert result == ({"error": "Invalid signature"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_accepts_verified_request(monkeypatch: pytest.MonkeyPatch):
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )
    callback = AsyncMock()
    server.set_callback(callback)
    monkeypatch.setattr(server, "verify_signature", lambda *args: True)

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": str(int(time.time())),
                "X-Lark-Request-Nonce": "2",
                "X-Lark-Signature": "good-signature",
            },
        )
    )

    assert result == {}
    await asyncio.gather(*list(server._callback_tasks), return_exceptions=True)
    callback.assert_awaited_once_with({"type": "event_callback"})


@pytest.mark.asyncio
async def test_lark_webhook_returns_before_callback_finishes(
    monkeypatch: pytest.MonkeyPatch,
):
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )
    callback_started = asyncio.Event()
    release_callback = asyncio.Event()
    callback_finished = asyncio.Event()

    async def callback(_event_data: dict) -> None:
        callback_started.set()
        await release_callback.wait()
        callback_finished.set()

    server.set_callback(callback)
    monkeypatch.setattr(server, "verify_signature", lambda *args: True)

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": str(int(time.time())),
                "X-Lark-Request-Nonce": "2",
                "X-Lark-Signature": "good-signature",
            },
        )
    )

    assert result == {}
    await asyncio.wait_for(callback_started.wait(), timeout=1.0)
    assert not callback_finished.is_set()
    release_callback.set()
    await asyncio.gather(*list(server._callback_tasks), return_exceptions=True)
    assert callback_finished.is_set()


def _signature(timestamp: str, nonce: str, encrypt_key: str, body: bytes) -> str:
    return hashlib.sha256(
        (timestamp + nonce + encrypt_key).encode("utf-8") + body
    ).hexdigest()


@pytest.mark.asyncio
async def test_lark_webhook_signature_accepts_and_rejects():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )
    body = b"{}"
    timestamp = str(int(time.time()))
    nonce = "nonce"
    valid_headers = {
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": _signature(timestamp, nonce, "encrypt-key", body),
    }

    accepted = await server.handle_callback(
        _FakeRequest(
            body=body, event_data={"type": "event_callback"}, headers=valid_headers
        )
    )
    assert accepted == {}

    rejected = await server.handle_callback(
        _FakeRequest(
            body=body,
            event_data={"type": "event_callback"},
            headers={**valid_headers, "X-Lark-Signature": "0" * 64},
        )
    )
    assert rejected == ({"error": "Invalid signature"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_rejects_stale_and_invalid_timestamps():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )
    body = b"{}"
    nonce = "nonce"

    stale_timestamp = str(int(time.time()) - 301)
    stale = await server.handle_callback(
        _FakeRequest(
            body=body,
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": stale_timestamp,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": _signature(
                    stale_timestamp, nonce, "encrypt-key", body
                ),
            },
        )
    )
    assert stale == ({"error": "Signature timestamp expired"}, 401)

    invalid = await server.handle_callback(
        _FakeRequest(
            body=body,
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": "not-a-number",
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": "0" * 64,
            },
        )
    )
    assert invalid == ({"error": "Invalid signature timestamp"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_fails_closed_without_authentication_config():
    server = LarkWebhookServer(
        {"app_id": "app-id", "app_secret": "secret"},
        event_queue=SimpleNamespace(),
    )

    challenge = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "url_verification", "challenge": "challenge"},
        )
    )
    assert challenge == ({"error": "Webhook authentication is not configured"}, 401)

    callback = AsyncMock()
    server.set_callback(callback)
    event = await server.handle_callback(
        _FakeRequest(body=b"{}", event_data={"type": "event_callback"})
    )
    assert event == ({"error": "Webhook authentication is not configured"}, 401)
    assert callback.await_count == 0


@pytest.mark.asyncio
async def test_lark_webhook_accepts_matching_verification_token():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_verification_token": "verification-token",
        },
        event_queue=SimpleNamespace(),
    )

    headers = {
        "X-Lark-Request-Timestamp": str(int(time.time())),
        "X-Lark-Request-Nonce": "token-nonce",
    }
    accepted = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={
                "type": "event_callback",
                "header": {"token": "verification-token"},
            },
            headers=headers,
        )
    )
    assert accepted == {}

    rejected = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={
                "type": "event_callback",
                "header": {"token": "wrong-token"},
            },
            headers=headers,
        )
    )
    assert rejected == ({"error": "Invalid verification token"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_treats_non_ascii_credentials_as_mismatch():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )

    rejected_signature = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": str(int(time.time())),
                "X-Lark-Request-Nonce": "nonce",
                "X-Lark-Signature": "签名",
            },
        )
    )
    assert rejected_signature == ({"error": "Invalid signature"}, 401)

    token_server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_verification_token": "verification-token",
        },
        event_queue=SimpleNamespace(),
    )
    rejected_token = await token_server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={
                "type": "event_callback",
                "header": {"token": "令牌"},
            },
            headers={
                "X-Lark-Request-Timestamp": str(int(time.time())),
                "X-Lark-Request-Nonce": "non-ascii-token-nonce",
            },
        )
    )
    assert rejected_token == ({"error": "Invalid verification token"}, 401)
