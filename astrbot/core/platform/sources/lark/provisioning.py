"""Dashboard provisioning capability for the Lark platform adapter."""

from __future__ import annotations

from typing import Any

from astrbot import logger
from astrbot.core.platform.provisioning import PlatformProvisioningValidationError

from .app_registration import poll_app_registration_once, request_app_registration
from .bot_info import request_lark_bot_info


async def provision_lark_registration(
    *,
    action: str,
    payload: dict[str, Any],
    platform_config: dict[str, Any],
) -> dict[str, Any]:
    """Start or poll the Lark application registration flow."""

    domain = str(platform_config.get("domain") or "").strip()
    if action == "start":
        registration = await request_app_registration(domain)
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
    result = await poll_app_registration_once(
        domain=domain,
        device_code=device_code,
    )
    if result.get("status") != "created":
        return result

    try:
        bot_info = await request_lark_bot_info(
            domain=str(result.get("domain") or domain),
            app_id=str(result.get("app_id") or ""),
            app_secret=str(result.get("app_secret") or ""),
        )
        if bot_info.app_name:
            result["bot_name"] = bot_info.app_name
        if bot_info.open_id:
            result["bot_open_id"] = bot_info.open_id
    except Exception as exc:
        logger.error("Failed to retrieve Lark bot information: %s", exc, exc_info=True)
    return result
