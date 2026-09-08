from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.weixin_oc import login_registration
from astrbot.core.platform.sources.weixin_oc.login_registration import (
    DEFAULT_WEIXIN_OC_BASE_URL,
    collect_local_bot_tokens,
    normalize_weixin_oc_base_url,
    poll_weixin_oc_login_once,
    weixin_oc_login_result,
)
from astrbot.core.platform.sources.weixin_oc.provisioning import (
    provision_weixin_oc_registration,
)

pytestmark = pytest.mark.platform


def test_normalize_weixin_oc_base_url_uses_default_and_strips_slash():
    assert normalize_weixin_oc_base_url("") == DEFAULT_WEIXIN_OC_BASE_URL
    assert (
        normalize_weixin_oc_base_url("https://ilinkai.weixin.qq.com/")
        == DEFAULT_WEIXIN_OC_BASE_URL
    )


def test_weixin_oc_login_result_maps_confirmed_payload():
    result = weixin_oc_login_result(
        {
            "status": "confirmed",
            "bot_token": "token",
            "ilink_bot_id": "bot-id",
            "baseurl": "https://ilink-c.weixin.qq.com/",
            "ilink_user_id": "user-id",
        },
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    )

    assert result == {
        "status": "created",
        "qr_status": "confirmed",
        "weixin_oc_token": "token",
        "weixin_oc_account_id": "bot-id",
        "weixin_oc_base_url": "https://ilink-c.weixin.qq.com",
        "weixin_oc_user_id": "user-id",
    }


def test_weixin_oc_login_result_maps_wait_and_expired_payloads():
    assert weixin_oc_login_result(
        {"status": "wait"},
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    ) == {"status": "pending", "qr_status": "wait"}

    assert weixin_oc_login_result(
        {"status": "expired"},
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    ) == {"status": "expired", "qr_status": "expired", "message": "二维码已过期"}


def test_weixin_oc_login_result_maps_verify_and_bind_payloads():
    assert weixin_oc_login_result(
        {"status": "need_verifycode"},
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    ) == {
        "status": "need_verifycode",
        "qr_status": "need_verifycode",
        "message": "请输入手机微信显示的数字",
    }
    assert (
        weixin_oc_login_result(
            {"status": "binded_redirect"},
            default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
            existing_token="token",
            existing_account_id="bot-id",
        )["status"]
        == "created"
    )
    assert (
        weixin_oc_login_result(
            {"status": "binded_redirect"},
            default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
        )["status"]
        == "error"
    )


def test_collect_local_bot_tokens_skips_blank():
    assert collect_local_bot_tokens({}) == []
    assert collect_local_bot_tokens({"weixin_oc_token": " token "}) == ["token"]


@pytest.mark.asyncio
async def test_poll_weixin_oc_login_once_follows_redirect_host(monkeypatch):
    login_registration._QR_POLL_STATES.clear()
    login_registration._remember_qr_poll_base_url(
        "qr-1",
        DEFAULT_WEIXIN_OC_BASE_URL,
    )
    client = AsyncMock()
    client.get_qrcode_status.side_effect = [
        {"status": "scaned_but_redirect", "redirect_host": "ilink-b.weixin.qq.com"},
        {
            "status": "confirmed",
            "bot_token": "token",
            "ilink_bot_id": "bot-id",
            "baseurl": "https://ilink-b.weixin.qq.com",
        },
    ]
    client.close = AsyncMock()
    monkeypatch.setattr(login_registration, "_client", lambda **kwargs: client)

    result = await poll_weixin_oc_login_once(
        platform_config={"id": "weixin-oc-test"},
        qrcode="qr-1",
    )

    assert result["status"] == "created"
    assert result["weixin_oc_base_url"] == "https://ilink-b.weixin.qq.com"
    assert client.get_qrcode_status.await_count == 2
    assert client.get_qrcode_status.await_args.kwargs["base_url"] == (
        "https://ilink-b.weixin.qq.com"
    )


@pytest.mark.asyncio
async def test_provision_poll_forwards_verify_code(monkeypatch):
    captured = {}

    async def fake_poll(**kwargs):
        captured.update(kwargs)
        return {"status": "need_verifycode", "qr_status": "need_verifycode"}

    monkeypatch.setattr(
        "astrbot.core.platform.sources.weixin_oc.provisioning.poll_weixin_oc_login_once",
        fake_poll,
    )
    result = await provision_weixin_oc_registration(
        action="poll",
        payload={"registration_code": "qr-1", "verify_code": "1234"},
        platform_config={"id": "weixin-oc-test"},
    )
    assert result["status"] == "need_verifycode"
    assert captured["verify_code"] == "1234"
    assert captured["qrcode"] == "qr-1"


@pytest.mark.asyncio
async def test_poll_weixin_oc_login_once_ignores_non_weixin_redirect_host(
    monkeypatch,
):
    login_registration._QR_POLL_STATES.clear()
    login_registration._remember_qr_poll_base_url(
        "qr-1",
        DEFAULT_WEIXIN_OC_BASE_URL,
    )
    client = AsyncMock()
    client.get_qrcode_status.return_value = {
        "status": "scaned_but_redirect",
        "redirect_host": "evil.example",
    }
    client.close = AsyncMock()
    monkeypatch.setattr(login_registration, "_client", lambda **kwargs: client)

    result = await poll_weixin_oc_login_once(
        platform_config={"id": "weixin-oc-test"},
        qrcode="qr-1",
    )

    assert result["status"] == "pending"
    assert client.get_qrcode_status.await_count == 1
    assert login_registration._qr_poll_base_url("qr-1") == DEFAULT_WEIXIN_OC_BASE_URL


def test_weixin_oc_login_result_rejects_non_weixin_confirmed_base_url():
    result = weixin_oc_login_result(
        {
            "status": "confirmed",
            "bot_token": "token",
            "baseurl": "https://evil.example/",
        },
        default_base_url=DEFAULT_WEIXIN_OC_BASE_URL,
    )
    assert result["weixin_oc_base_url"] == DEFAULT_WEIXIN_OC_BASE_URL
