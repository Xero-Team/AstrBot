from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.star.session_plugin_manager import SessionPluginManager


@pytest.mark.asyncio
async def test_filter_handlers_respects_enabled_plugins(
    monkeypatch: pytest.MonkeyPatch,
):
    event = SimpleNamespace(unified_msg_origin="umo")
    handlers = [
        SimpleNamespace(handler_module_path="module.a", handler_name="ha"),
        SimpleNamespace(handler_module_path="module.b", handler_name="hb"),
    ]
    preferences = SimpleNamespace(
        get_async=AsyncMock(
            return_value={
                "umo": {
                    "enabled_plugins": ["plugin-a"],
                    "disabled_plugins": [],
                }
            }
        )
    )

    from astrbot.core.star import star as star_module

    monkeypatch.setattr(
        star_module,
        "star_map",
        {
            "module.a": SimpleNamespace(name="plugin-a", reserved=False),
            "module.b": SimpleNamespace(name="plugin-b", reserved=False),
        },
    )

    filtered = await SessionPluginManager(preferences).filter_handlers_by_session(
        event, handlers
    )

    assert filtered == [handlers[0]]
