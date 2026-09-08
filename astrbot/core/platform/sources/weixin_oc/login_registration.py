from dataclasses import dataclass
from typing import Any

from .weixin_oc_client import (
    ILINK_FIXED_BASE_URL,
    WeixinOCClient,
    resolve_weixin_https_base_url,
)

DEFAULT_WEIXIN_OC_BASE_URL = ILINK_FIXED_BASE_URL
DEFAULT_WEIXIN_OC_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_WEIXIN_OC_BOT_TYPE = "3"
DEFAULT_WEIXIN_OC_QR_POLL_INTERVAL = 1
DEFAULT_WEIXIN_OC_LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_WEIXIN_OC_API_TIMEOUT_MS = 15_000
_QR_POLL_STATES: dict[str, str] = {}


@dataclass
class WeixinOCLoginRegistration:
    qrcode: str
    qrcode_img_content: str
    interval: int


def normalize_weixin_oc_base_url(base_url: str | None) -> str:
    return (base_url or DEFAULT_WEIXIN_OC_BASE_URL).strip().rstrip("/")


def collect_local_bot_tokens(platform_config: dict[str, Any]) -> list[str]:
    token = _string_field(platform_config, "weixin_oc_token")
    return [token] if token else []


def _string_field(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _int_config(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except TypeError, ValueError:
        parsed = default
    return max(parsed, minimum)


def _remember_qr_poll_base_url(qrcode: str, base_url: str) -> None:
    if qrcode and base_url:
        _QR_POLL_STATES[qrcode] = normalize_weixin_oc_base_url(base_url)


def _qr_poll_base_url(qrcode: str) -> str:
    return _QR_POLL_STATES.get(qrcode) or DEFAULT_WEIXIN_OC_BASE_URL


def _forget_qr_poll_base_url(qrcode: str) -> None:
    _QR_POLL_STATES.pop(qrcode, None)


def weixin_oc_login_result(
    data: dict[str, Any],
    *,
    default_base_url: str,
    existing_token: str = "",
    existing_account_id: str = "",
) -> dict[str, Any]:
    raw_status = _string_field(data, "status") or "wait"
    if raw_status == "confirmed":
        bot_token = _string_field(data, "bot_token")
        if not bot_token:
            return {"status": "error", "message": "登录成功但未返回 token"}
        raw_base_url = _string_field(data, "baseurl") or default_base_url
        base_url = resolve_weixin_https_base_url(
            raw_base_url
        ) or normalize_weixin_oc_base_url(default_base_url)
        return {
            "status": "created",
            "qr_status": raw_status,
            "weixin_oc_token": bot_token,
            "weixin_oc_account_id": _string_field(data, "ilink_bot_id"),
            "weixin_oc_base_url": base_url,
            "weixin_oc_user_id": _string_field(data, "ilink_user_id"),
        }
    if raw_status == "expired":
        return {"status": "expired", "qr_status": raw_status, "message": "二维码已过期"}
    if raw_status in {"cancel", "canceled", "denied"}:
        return {"status": "denied", "qr_status": raw_status, "message": "用户取消登录"}
    if raw_status == "need_verifycode":
        return {
            "status": "need_verifycode",
            "qr_status": raw_status,
            "message": "请输入手机微信显示的数字",
        }
    if raw_status == "verify_code_blocked":
        return {
            "status": "error",
            "qr_status": raw_status,
            "message": "配对码多次输入错误，请重新扫码",
        }
    if raw_status == "binded_redirect":
        if existing_token:
            return {
                "status": "created",
                "qr_status": raw_status,
                "weixin_oc_token": existing_token,
                "weixin_oc_account_id": existing_account_id,
                "weixin_oc_base_url": normalize_weixin_oc_base_url(default_base_url),
                "message": "该微信已绑定当前登录态，无需重复扫码",
            }
        return {
            "status": "error",
            "qr_status": raw_status,
            "message": "该微信已绑定其他实例，无法完成登录",
        }
    if raw_status == "scaned_but_redirect":
        redirect_host = _string_field(data, "redirect_host")
        return {
            "status": "pending",
            "qr_status": raw_status,
            "redirect_host": redirect_host,
        }
    return {"status": "pending", "qr_status": raw_status}


def _client(
    *,
    adapter_id: str,
    base_url: str,
    api_timeout_ms: int,
) -> WeixinOCClient:
    return WeixinOCClient(
        adapter_id=adapter_id,
        base_url=base_url,
        cdn_base_url=DEFAULT_WEIXIN_OC_CDN_BASE_URL,
        api_timeout_ms=api_timeout_ms,
    )


async def request_weixin_oc_login_qr(
    platform_config: dict[str, Any],
) -> WeixinOCLoginRegistration:
    bot_type = _string_field(platform_config, "weixin_oc_bot_type")
    if not bot_type:
        bot_type = DEFAULT_WEIXIN_OC_BOT_TYPE
    api_timeout_ms = _int_config(
        platform_config.get("weixin_oc_api_timeout_ms"),
        DEFAULT_WEIXIN_OC_API_TIMEOUT_MS,
        1_000,
    )
    interval = _int_config(
        platform_config.get("weixin_oc_qr_poll_interval"),
        DEFAULT_WEIXIN_OC_QR_POLL_INTERVAL,
        1,
    )

    client = _client(
        adapter_id=str(platform_config.get("id") or "weixin_oc"),
        base_url=DEFAULT_WEIXIN_OC_BASE_URL,
        api_timeout_ms=api_timeout_ms,
    )
    try:
        data = await client.get_bot_qrcode(
            bot_type,
            collect_local_bot_tokens(platform_config),
        )
    finally:
        await client.close()

    qrcode = _string_field(data, "qrcode")
    qrcode_img_content = _string_field(data, "qrcode_img_content")
    if not qrcode or not qrcode_img_content:
        raise RuntimeError("个人微信二维码响应格式异常")

    _remember_qr_poll_base_url(qrcode, DEFAULT_WEIXIN_OC_BASE_URL)
    return WeixinOCLoginRegistration(
        qrcode=qrcode,
        qrcode_img_content=qrcode_img_content,
        interval=interval,
    )


async def poll_weixin_oc_login_once(
    *,
    platform_config: dict[str, Any],
    qrcode: str,
    verify_code: str | None = None,
) -> dict[str, Any]:
    if not qrcode:
        raise ValueError("Missing qrcode")

    api_timeout_ms = _int_config(
        platform_config.get("weixin_oc_api_timeout_ms"),
        DEFAULT_WEIXIN_OC_API_TIMEOUT_MS,
        1_000,
    )
    long_poll_timeout_ms = _int_config(
        platform_config.get("weixin_oc_long_poll_timeout_ms"),
        DEFAULT_WEIXIN_OC_LONG_POLL_TIMEOUT_MS,
        1_000,
    )
    existing_token = _string_field(platform_config, "weixin_oc_token")
    existing_account_id = _string_field(platform_config, "weixin_oc_account_id")
    poll_base_url = _qr_poll_base_url(qrcode)

    client = _client(
        adapter_id=str(platform_config.get("id") or "weixin_oc"),
        base_url=poll_base_url,
        api_timeout_ms=api_timeout_ms,
    )
    try:
        data = await client.get_qrcode_status(
            qrcode,
            verify_code=verify_code,
            timeout_ms=long_poll_timeout_ms,
            base_url=poll_base_url,
        )
        result = weixin_oc_login_result(
            data,
            default_base_url=poll_base_url,
            existing_token=existing_token,
            existing_account_id=existing_account_id,
        )
        if result.get("qr_status") == "scaned_but_redirect":
            redirected_base = resolve_weixin_https_base_url(
                str(result.get("redirect_host") or "")
            )
            if redirected_base:
                _remember_qr_poll_base_url(qrcode, redirected_base)
                data = await client.get_qrcode_status(
                    qrcode,
                    verify_code=verify_code,
                    timeout_ms=long_poll_timeout_ms,
                    base_url=redirected_base,
                )
                result = weixin_oc_login_result(
                    data,
                    default_base_url=redirected_base,
                    existing_token=existing_token,
                    existing_account_id=existing_account_id,
                )
        if result.get("status") in {"created", "expired", "denied", "error"}:
            _forget_qr_poll_base_url(qrcode)
        return result
    finally:
        await client.close()
