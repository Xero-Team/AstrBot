import asyncio
import copy
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig
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


@pytest.mark.asyncio
async def test_get_astrbot_config_redacts_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "_ensure_dashboard_platform_metadata_loaded",
        lambda: None,
    )
    monkeypatch.setattr(config_service, "platform_registry", [])
    monkeypatch.setattr(config_service, "provider_registry", [])
    service = config_service.ConfigDisplayService(
        SimpleNamespace(
            astrbot_config={
                "dashboard": {
                    "jwt_secret": "jwt-secret",
                    "pbkdf2_password": "pbkdf2-hash",
                    "totp": {
                        "enable": True,
                        "secret": "totp-secret",
                        "recovery_code_hash": "recovery-hash",
                    },
                },
                "provider": [
                    {"id": "demo", "key": ["sk-live-1", "sk-live-2"]},
                    {"id": "embed", "embedding_api_key": "embed-secret"},
                ],
                "provider_settings": {"default_provider_id": "demo"},
            }
        ),
    )

    result = await service.get_astrbot_config()
    redacted = result["config"]

    assert (
        redacted["dashboard"]["jwt_secret"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        redacted["dashboard"]["pbkdf2_password"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        redacted["dashboard"]["totp"]["secret"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert (
        redacted["dashboard"]["totp"]["recovery_code_hash"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert redacted["provider"][0]["key"] == [
        config_service.REDACTED_SECRET_PLACEHOLDER,
        config_service.REDACTED_SECRET_PLACEHOLDER,
    ]
    assert (
        redacted["provider"][1]["embedding_api_key"]
        == config_service.REDACTED_SECRET_PLACEHOLDER
    )
    assert redacted["provider_settings"]["default_provider_id"] == "demo"


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


def test_save_config_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(asyncio.CancelledError()),
    )

    with pytest.raises(asyncio.CancelledError):
        config_service.save_config({}, SimpleNamespace(save_config=lambda *_args: None))


def test_save_config_restores_redacted_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda post_config, _schema, _is_core: ([], post_config),
    )

    class FakeConfig(dict):
        def __init__(self, initial: dict) -> None:
            super().__init__(copy.deepcopy(initial))
            self.saved = None

        def save_config(self, post_config=None, *, indent: int = 2) -> None:  # noqa: ARG002
            self.saved = copy.deepcopy(post_config)
            self.clear()
            self.update(post_config)

    current = FakeConfig(
        {
            "dashboard": {
                "jwt_secret": "jwt-secret",
                "pbkdf2_password": "pbkdf2-hash",
                "totp": {
                    "enable": True,
                    "secret": "totp-secret",
                    "recovery_code_hash": "recovery-hash",
                },
            },
            "provider": [
                {"id": "demo", "key": ["sk-live-1", "sk-live-2"]},
                {"id": "embed", "embedding_api_key": "embed-secret"},
            ],
            "provider_settings": {"default_provider_id": "demo"},
        }
    )
    posted = {
        "dashboard": {
            "jwt_secret": config_service.REDACTED_SECRET_PLACEHOLDER,
            "pbkdf2_password": config_service.REDACTED_SECRET_PLACEHOLDER,
            "totp": {
                "enable": True,
                "secret": config_service.REDACTED_SECRET_PLACEHOLDER,
                "recovery_code_hash": config_service.REDACTED_SECRET_PLACEHOLDER,
            },
        },
        "provider": [
            {
                "id": "demo",
                "key": [
                    config_service.REDACTED_SECRET_PLACEHOLDER,
                    config_service.REDACTED_SECRET_PLACEHOLDER,
                ],
            },
            {
                "id": "embed",
                "embedding_api_key": config_service.REDACTED_SECRET_PLACEHOLDER,
            },
        ],
        "provider_settings": {"default_provider_id": "embed"},
    }

    config_service.save_config(posted, current, is_core=True)

    assert current.saved["dashboard"]["jwt_secret"] == "jwt-secret"
    assert current.saved["dashboard"]["pbkdf2_password"] == "pbkdf2-hash"
    assert current.saved["dashboard"]["totp"]["secret"] == "totp-secret"
    assert current.saved["dashboard"]["totp"]["recovery_code_hash"] == "recovery-hash"
    assert current.saved["provider"][0]["key"] == ["sk-live-1", "sk-live-2"]
    assert current.saved["provider"][1]["embedding_api_key"] == "embed-secret"
    assert current.saved["provider_settings"]["default_provider_id"] == "embed"


def test_save_config_uses_plain_dict_snapshot_for_live_config(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_service,
        "validate_config",
        lambda post_config, _schema, _is_core: ([], post_config),
    )

    config_path = tmp_path / "cmd_config.json"
    config_path.write_text('{"config_version": 2}', encoding="utf-8")

    config = AstrBotConfig(config_path=str(config_path), default_config={})
    object.__setattr__(config, "_runtime_lock", threading.Lock())
    config["provider_sources"] = [{"id": "demo", "type": "openai_chat_completion"}]

    config_service.save_config(config, config, is_core=True)

    saved = AstrBotConfig._load_config_dict(str(config_path))
    assert "_runtime_lock" not in saved
    assert saved["provider_sources"][0]["id"] == "demo"


@pytest.mark.asyncio
async def test_delete_profile_clears_routing_entries_for_deleted_config() -> None:
    acm = SimpleNamespace(delete_conf=AsyncMock(return_value=True))
    ucr = SimpleNamespace(
        umop_to_conf_id={
            "onebot:group:123": "conf-a",
            "onebot:friend:456": "conf-b",
        },
        update_routing_data=AsyncMock(),
    )
    core_lifecycle = SimpleNamespace(
        astrbot_config_mgr=acm,
        pipeline_scheduler_mapping={"conf-a": object(), "conf-b": object()},
        umop_config_router=ucr,
    )
    service = config_service.ConfigProfileService(core_lifecycle)

    await service.delete_profile("conf-a")

    assert "conf-a" not in core_lifecycle.pipeline_scheduler_mapping
    acm.delete_conf.assert_awaited_once_with("conf-a")
    ucr.update_routing_data.assert_awaited_once_with({"onebot:friend:456": "conf-b"})


@pytest.mark.asyncio
async def test_delete_profile_preserves_more_specific_routes_for_other_profiles() -> None:
    acm = SimpleNamespace(delete_conf=AsyncMock(return_value=True))
    ucr = SimpleNamespace(
        umop_to_conf_id={
            "::": "conf-a",
            "telegram::": "conf-b",
            "telegram:group:room-*": "conf-b",
            "telegram:group:room-123": "conf-c",
        },
        update_routing_data=AsyncMock(),
    )
    core_lifecycle = SimpleNamespace(
        astrbot_config_mgr=acm,
        pipeline_scheduler_mapping={
            "conf-a": object(),
            "conf-b": object(),
            "conf-c": object(),
        },
        umop_config_router=ucr,
    )
    service = config_service.ConfigProfileService(core_lifecycle)

    await service.delete_profile("conf-a")

    assert "conf-a" not in core_lifecycle.pipeline_scheduler_mapping
    ucr.update_routing_data.assert_awaited_once_with(
        {
            "telegram::": "conf-b",
            "telegram:group:room-*": "conf-b",
            "telegram:group:room-123": "conf-c",
        }
    )
