from types import SimpleNamespace

import pytest

from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NAPCAT_CONFIG_METADATA,
)
from astrbot.dashboard.services import config_service


def test_ensure_dashboard_platform_metadata_loaded_imports_napcat_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []

    monkeypatch.setattr(config_service, "platform_registry", [])
    monkeypatch.setattr(
        config_service.importlib,
        "import_module",
        lambda module_name: imported.append(module_name),
    )

    config_service._ensure_dashboard_platform_metadata_loaded()

    assert imported == ["astrbot.core.platform.sources.napcat.napcat_platform_adapter"]


def test_ensure_dashboard_platform_metadata_loaded_skips_import_when_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "platform_registry",
        [SimpleNamespace(name="napcat")],
    )

    def _unexpected_import(_: str) -> None:
        raise AssertionError("import_module should not be called")

    monkeypatch.setattr(config_service.importlib, "import_module", _unexpected_import)

    config_service._ensure_dashboard_platform_metadata_loaded()


@pytest.mark.asyncio
async def test_get_astrbot_config_loads_dashboard_platform_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[bool] = []

    monkeypatch.setattr(
        config_service,
        "_ensure_dashboard_platform_metadata_loaded",
        lambda: called.append(True),
    )
    service = config_service.ConfigDisplayService(
        SimpleNamespace(astrbot_config={}),
    )

    result = await service.get_astrbot_config()

    assert called == [True]
    assert "metadata" in result
    assert "config" in result


def test_inject_platform_metadata_with_i18n_rewrites_field_labels() -> None:
    metadata = {
        "platform_group": {
            "metadata": {
                "platform": {
                    "items": {},
                }
            }
        }
    }
    translations: dict = {}
    platform = SimpleNamespace(
        name="napcat",
        config_metadata={
            "ws_url": {
                "description": "NapCat WebSocket URL",
                "hint": "NapCat OneBot v11 forward WebSocket URL.",
            },
            "max_frame_size_mb": {
                "description": "Max Frame Size MB",
                "hint": "Maximum inbound WebSocket frame size in megabytes.",
                "collapsed": True,
            },
        },
        i18n_resources={
            "zh-CN": {
                "ws_url": {
                    "description": "NapCat WebSocket 地址",
                    "hint": "NapCat OneBot v11 正向 WebSocket 地址。",
                },
                "max_frame_size_mb": {
                    "description": "最大帧大小(MB)",
                    "hint": "允许接收的单个 WebSocket 帧的最大大小，单位 MB。",
                },
            }
        },
    )

    config_service.ConfigDisplayService.inject_platform_metadata_with_i18n(
        platform,
        metadata,
        translations,
    )

    assert metadata["platform_group"]["metadata"]["platform"]["items"]["ws_url"] == {
        "description": "platform_group.platform.napcat.ws_url.description",
        "hint": "platform_group.platform.napcat.ws_url.hint",
    }
    assert metadata["platform_group"]["metadata"]["platform"]["items"][
        "max_frame_size_mb"
    ] == {
        "description": "platform_group.platform.napcat.max_frame_size_mb.description",
        "hint": "platform_group.platform.napcat.max_frame_size_mb.hint",
        "collapsed": True,
    }
    assert translations["zh-CN"]["platform_group"]["platform"]["napcat"] == {
        "ws_url": {
            "description": "NapCat WebSocket 地址",
            "hint": "NapCat OneBot v11 正向 WebSocket 地址。",
        },
        "max_frame_size_mb": {
            "description": "最大帧大小(MB)",
            "hint": "允许接收的单个 WebSocket 帧的最大大小，单位 MB。",
        },
    }


def test_list_bot_types_includes_supported_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakePlatformClass:
        @classmethod
        def declared_supported_actions(cls) -> list[str]:
            return ["send_poke", "send_like"]

    monkeypatch.setattr(
        config_service,
        "platform_registry",
        [
            SimpleNamespace(
                name="napcat",
                id="napcat",
                description="NapCat platform adapter",
                adapter_display_name="NapCat",
                default_config_tmpl={"type": "napcat"},
                config_metadata={"ws_url": {"type": "string"}},
                support_streaming_message=False,
                support_proactive_message=True,
            )
        ],
    )
    monkeypatch.setattr(
        config_service,
        "platform_cls_map",
        {"napcat": _FakePlatformClass},
    )
    monkeypatch.setattr(
        config_service,
        "_ensure_dashboard_platform_metadata_loaded",
        lambda: None,
    )

    service = config_service.BotConfigService(
        SimpleNamespace(astrbot_config={}),
    )

    result = service.list_bot_types()

    assert result["bot_types"][0]["supported_actions"] == ["send_poke", "send_like"]


def test_napcat_config_metadata_uses_supported_numeric_types() -> None:
    assert NAPCAT_CONFIG_METADATA["timeout_seconds"]["type"] == "float"
    assert NAPCAT_CONFIG_METADATA["reconnect_interval_seconds"]["type"] == "float"
    assert NAPCAT_CONFIG_METADATA["max_frame_size_mb"]["type"] == "int"


def test_napcat_config_metadata_hides_advanced_ws_fields_by_default() -> None:
    assert NAPCAT_CONFIG_METADATA["token"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["verify_ssl"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["timeout_seconds"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["reconnect_interval_seconds"]["collapsed"] is True
    assert NAPCAT_CONFIG_METADATA["max_frame_size_mb"]["collapsed"] is True
