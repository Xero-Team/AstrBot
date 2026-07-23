from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core import astrbot_config_mgr as config_manager_module


@pytest.mark.asyncio
async def test_create_conf_persists_with_async_snapshot_api(monkeypatch, tmp_path):
    created_configs = []

    class FakeConfig:
        def __init__(self, *, config_path: str, default_config: dict) -> None:
            self.config_path = config_path
            self.default_config = default_config
            self.save_config_async = AsyncMock(return_value=True)
            created_configs.append(self)

    monkeypatch.setattr(config_manager_module, "AstrBotConfig", FakeConfig)
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    preferences = SimpleNamespace(global_put=AsyncMock())
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )

    config_id = await manager.create_conf(config={"provider": []}, name="profile")

    created = created_configs[0]
    created.save_config_async.assert_awaited_once()
    preferences.global_put.assert_awaited_once_with(
        "abconf_mapping",
        {
            config_id: {
                "path": f"abconf_{config_id}.json",
                "name": "profile",
            },
        },
    )
    assert manager.confs[config_id] is created


@pytest.mark.asyncio
async def test_create_conf_does_not_publish_profile_when_save_is_superseded(
    monkeypatch,
    tmp_path,
):
    created_configs = []

    class FakeConfig:
        def __init__(self, *, config_path: str, default_config: dict) -> None:
            self.config_path = config_path
            self.default_config = default_config
            self.save_config_async = AsyncMock(return_value=False)
            created_configs.append(self)

    monkeypatch.setattr(config_manager_module, "AstrBotConfig", FakeConfig)
    monkeypatch.setattr(
        config_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path),
    )
    preferences = SimpleNamespace(global_put=AsyncMock())
    manager = config_manager_module.AstrBotConfigManager(
        default_config=SimpleNamespace(),
        ucr=SimpleNamespace(),
        sp=preferences,
    )

    with pytest.raises(RuntimeError, match="superseded"):
        await manager.create_conf(config={"provider": []}, name="profile")

    created_configs[0].save_config_async.assert_awaited_once()
    preferences.global_put.assert_not_awaited()
    assert set(manager.confs) == {"default"}
