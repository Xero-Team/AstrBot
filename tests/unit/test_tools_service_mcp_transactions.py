import asyncio
import copy
from types import SimpleNamespace

import pytest

from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError


class FakeToolManager:
    def __init__(self, servers: dict) -> None:
        self.config = {"mcpServers": copy.deepcopy(servers)}
        self.mcp_server_runtime_view: dict = {}
        self.fail_enable = False
        self.fail_disable = False
        self.enabled: list[str] = []
        self.disabled: list[str] = []

    def load_mcp_config(self) -> dict:
        return copy.deepcopy(self.config)

    def save_mcp_config(self, config: dict) -> bool:
        self.config = copy.deepcopy(config)
        return True

    async def enable_mcp_server(self, name: str, config: dict, **_kwargs) -> None:
        if self.fail_enable and config.get("args") == ["new.py"]:
            raise TimeoutError("enable timed out")
        self.enabled.append(name)
        self.mcp_server_runtime_view[name] = SimpleNamespace(client=SimpleNamespace())

    async def disable_mcp_server(self, name: str, **_kwargs) -> None:
        if self.fail_disable:
            raise TimeoutError("disable timed out")
        self.disabled.append(name)
        self.mcp_server_runtime_view.pop(name, None)


def _service(servers: dict) -> tuple[ToolsService, FakeToolManager]:
    manager = FakeToolManager(servers)
    service = ToolsService(
        tool_manager=manager,
        preferences=SimpleNamespace(),
        config_manager=SimpleNamespace(),
        plugin_catalog=SimpleNamespace(),
    )
    return service, manager


@pytest.mark.asyncio
async def test_update_rolls_back_config_and_runtime_when_enable_fails():
    old_config = {"command": "python", "args": ["old.py"], "active": True}
    service, manager = _service({"server": old_config})
    manager.mcp_server_runtime_view["server"] = SimpleNamespace(
        client=SimpleNamespace()
    )
    manager.fail_enable = True

    with pytest.raises(ToolsServiceError, match="Timed out"):
        await service.update_mcp_server(
            "server",
            {
                "name": "server",
                "command": "python",
                "args": ["new.py"],
                "active": True,
            },
        )

    assert manager.config["mcpServers"]["server"] == old_config
    assert manager.enabled == ["server"]
    assert "server" in manager.mcp_server_runtime_view


@pytest.mark.asyncio
async def test_delete_keeps_config_when_runtime_cannot_stop():
    old_config = {"command": "python", "args": ["old.py"], "active": True}
    service, manager = _service({"server": old_config})
    manager.mcp_server_runtime_view["server"] = SimpleNamespace(
        client=SimpleNamespace()
    )
    manager.fail_disable = True

    with pytest.raises(ToolsServiceError, match="Timed out"):
        await service.delete_mcp_server({"name": "server"})

    assert manager.config["mcpServers"]["server"] == old_config


@pytest.mark.asyncio
async def test_delete_cancels_orphaned_oauth_probe():
    old_config = {
        "url": "https://example.com/mcp",
        "transport": "streamable_http",
        "auth_ref": "ref-1",
        "active": True,
    }
    service, manager = _service({"server": old_config})

    async def probe() -> None:
        await asyncio.sleep(3600)

    probe_task = asyncio.create_task(probe())
    service._oauth_probe_tasks["server:ref-1"] = probe_task

    await service.delete_mcp_server({"name": "server"})

    assert "server" not in manager.config["mcpServers"]
    assert probe_task.cancelled()
    assert "server:ref-1" not in service._oauth_probe_tasks


@pytest.mark.asyncio
async def test_update_cancels_oauth_probes_for_old_and_new_names():
    old_config = {
        "command": "python",
        "args": ["old.py"],
        "auth_ref": "ref-old",
        "active": True,
    }
    service, manager = _service({"server": old_config})

    async def probe() -> None:
        await asyncio.sleep(3600)

    old_probe = asyncio.create_task(probe())
    new_probe = asyncio.create_task(probe())
    service._oauth_probe_tasks["server:ref-old"] = old_probe
    service._oauth_probe_tasks["renamed:ref-new"] = new_probe

    await service.update_mcp_server(
        "server",
        {
            "name": "renamed",
            "command": "python",
            "args": ["new.py"],
            "auth_ref": "ref-new",
            "active": True,
        },
    )

    assert old_probe.cancelled()
    assert new_probe.cancelled()
    assert service._oauth_probe_tasks == {}
    assert "renamed" in manager.config["mcpServers"]


@pytest.mark.asyncio
async def test_failed_update_rollback_cancels_oauth_probes():
    old_config = {
        "command": "python",
        "args": ["old.py"],
        "auth_ref": "ref-old",
        "active": True,
    }
    service, manager = _service({"server": old_config})
    manager.fail_enable = True

    async def probe() -> None:
        await asyncio.sleep(3600)

    old_probe = asyncio.create_task(probe())
    new_probe = asyncio.create_task(probe())
    service._oauth_probe_tasks["server:ref-old"] = old_probe
    service._oauth_probe_tasks["renamed:ref-new"] = new_probe

    with pytest.raises(ToolsServiceError, match="Timed out"):
        await service.update_mcp_server(
            "server",
            {
                "name": "renamed",
                "command": "python",
                "args": ["new.py"],
                "auth_ref": "ref-new",
                "active": True,
            },
        )

    assert old_probe.cancelled()
    assert new_probe.cancelled()
    assert service._oauth_probe_tasks == {}
    assert "server" in manager.config["mcpServers"]
    assert "renamed" not in manager.config["mcpServers"]
