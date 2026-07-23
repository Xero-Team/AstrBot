"""Dashboard provisioning capability for the DingTalk platform adapter."""

from __future__ import annotations

from typing import Any

from astrbot.core.platform.provisioning import (
    PlatformProvisioningValidationError,
    random_platform_id_suffix,
)

from .app_registration import (
    poll_dingtalk_app_registration_once,
    request_dingtalk_app_registration,
)


async def provision_dingtalk_registration(
    *,
    action: str,
    payload: dict[str, Any],
    platform_config: dict[str, Any],  # noqa: ARG001
) -> dict[str, Any]:
    """Start or poll the DingTalk application registration flow."""

    if action == "start":
        registration = await request_dingtalk_app_registration()
        return {
            "status": "pending",
            "device_code": registration.device_code,
            "registration_code": registration.device_code,
            "user_code": registration.user_code,
            "verification_uri": registration.verification_uri,
            "verification_uri_complete": registration.verification_uri_complete,
            "expires_in": registration.expires_in,
            "interval": registration.interval,
        }

    if action != "poll":
        raise PlatformProvisioningValidationError(f"Unsupported action: {action}")

    device_code = str(
        payload.get("device_code") or payload.get("registration_code") or ""
    ).strip()
    if not device_code:
        raise PlatformProvisioningValidationError("Missing device_code")
    result = await poll_dingtalk_app_registration_once(device_code)
    if result.get("status") == "created":
        result["platform_id_suffix"] = random_platform_id_suffix()
    return result
