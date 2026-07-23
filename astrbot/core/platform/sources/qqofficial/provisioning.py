"""Dashboard provisioning capability shared by QQ Official adapters."""

from __future__ import annotations

from typing import Any

from astrbot.core.platform.provisioning import PlatformProvisioningValidationError

from .login_registration import (
    poll_qqofficial_login_once,
    request_qqofficial_login_qr,
)


async def provision_qqofficial_registration(
    *,
    action: str,
    payload: dict[str, Any],
    platform_config: dict[str, Any],
) -> dict[str, Any]:
    """Start or poll the QQ Official Bot QR binding flow."""

    if action == "start":
        registration = await request_qqofficial_login_qr(platform_config)
        return {
            "status": "pending",
            "registration_code": registration.task_id,
            "task_id": registration.task_id,
            "bind_key": registration.bind_key,
            "qrcode": registration.qrcode,
            "qrcode_img_content": registration.qrcode,
            "interval": registration.interval,
        }

    if action != "poll":
        raise PlatformProvisioningValidationError(f"Unsupported action: {action}")

    task_id = str(
        payload.get("task_id") or payload.get("registration_code") or ""
    ).strip()
    bind_key = str(payload.get("bind_key") or "").strip()
    if not task_id:
        raise PlatformProvisioningValidationError("Missing task_id")
    if not bind_key:
        raise PlatformProvisioningValidationError("Missing bind_key")
    return await poll_qqofficial_login_once(
        platform_config=platform_config,
        task_id=task_id,
        bind_key=bind_key,
    )
