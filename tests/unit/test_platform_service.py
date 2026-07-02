from types import SimpleNamespace

import pytest

from astrbot.dashboard.services.platform_service import (
    PlatformService,
    PlatformServiceError,
)


@pytest.mark.asyncio
async def test_platform_service_invoke_platform_action_success() -> None:
    calls: list[tuple[str, str, dict]] = []

    async def _invoke_action(platform_id: str, action_name: str, **kwargs) -> dict:
        calls.append((platform_id, action_name, kwargs))
        return {"status": "ok", "data": {"done": True}}

    service = PlatformService(
        SimpleNamespace(
            platform_manager=SimpleNamespace(invoke_action=_invoke_action),
        )
    )

    result = await service.invoke_platform_action(
        "napcat-main",
        "send_poke",
        {"user_id": "123456", "target_id": "654321"},
    )

    assert result == {"status": "ok", "data": {"done": True}}
    assert calls == [
        (
            "napcat-main",
            "send_poke",
            {"user_id": "123456", "target_id": "654321"},
        )
    ]


@pytest.mark.asyncio
async def test_platform_service_invoke_platform_action_validates_input() -> None:
    service = PlatformService(
        SimpleNamespace(
            platform_manager=SimpleNamespace(invoke_action=None),
        )
    )

    with pytest.raises(PlatformServiceError, match="Missing action_name") as exc_info:
        await service.invoke_platform_action("napcat-main", "   ", {})
    assert exc_info.value.status_code == 400

    with pytest.raises(PlatformServiceError, match="Payload must be an object") as exc_info:
        await service.invoke_platform_action("napcat-main", "send_poke", [])
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_platform_service_invoke_platform_action_maps_common_errors() -> None:
    async def _missing(*_args, **_kwargs):
        raise LookupError("Platform adapter not found: missing")

    async def _unsupported(*_args, **_kwargs):
        raise NotImplementedError("Platform missing does not support action `send_poke`")

    async def _bad_payload(*_args, **_kwargs):
        raise ValueError("group_id is required")

    missing_service = PlatformService(
        SimpleNamespace(platform_manager=SimpleNamespace(invoke_action=_missing))
    )
    unsupported_service = PlatformService(
        SimpleNamespace(platform_manager=SimpleNamespace(invoke_action=_unsupported))
    )
    bad_payload_service = PlatformService(
        SimpleNamespace(platform_manager=SimpleNamespace(invoke_action=_bad_payload))
    )

    with pytest.raises(PlatformServiceError, match="Platform adapter not found") as exc_info:
        await missing_service.invoke_platform_action("missing", "send_poke", {})
    assert exc_info.value.status_code == 404

    with pytest.raises(PlatformServiceError, match="does not support action") as exc_info:
        await unsupported_service.invoke_platform_action("missing", "send_poke", {})
    assert exc_info.value.status_code == 400

    with pytest.raises(PlatformServiceError, match="group_id is required") as exc_info:
        await bad_payload_service.invoke_platform_action("napcat-main", "send_group_notice", {})
    assert exc_info.value.status_code == 400
