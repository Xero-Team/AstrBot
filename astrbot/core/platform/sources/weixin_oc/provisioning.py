"""Dashboard provisioning capability for the Weixin OC platform adapter."""

from __future__ import annotations

from typing import Any

from astrbot.core.platform.provisioning import (
    PlatformProvisioningValidationError,
    random_platform_id_suffix,
)

from .login_registration import (
    poll_weixin_oc_login_once,
    request_weixin_oc_login_qr,
)


async def provision_weixin_oc_registration(
    *,
    action: str,
    payload: dict[str, Any],
    platform_config: dict[str, Any],
) -> dict[str, Any]:
    """Start or poll the Weixin OC QR login flow."""

    if action == "start":
        registration = await request_weixin_oc_login_qr(platform_config)
        return {
            "status": "pending",
            "registration_code": registration.qrcode,
            "qrcode": registration.qrcode,
            "qrcode_img_content": registration.qrcode_img_content,
            "interval": registration.interval,
        }

    if action != "poll":
        raise PlatformProvisioningValidationError(f"Unsupported action: {action}")

    qrcode = str(
        payload.get("qrcode") or payload.get("registration_code") or ""
    ).strip()
    if not qrcode:
        raise PlatformProvisioningValidationError("Missing qrcode")
    result = await poll_weixin_oc_login_once(
        platform_config=platform_config,
        qrcode=qrcode,
    )
    if result.get("status") == "created":
        result["platform_id_suffix"] = random_platform_id_suffix()
    return result
