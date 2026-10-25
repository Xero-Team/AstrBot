from unittest.mock import AsyncMock

import pytest

from astrbot.core.computer.booters.bay_manager import BAY_PORT, BayContainerManager


def test_bay_container_port_is_bound_to_loopback():
    manager = BayContainerManager()

    config = manager._build_container_config()

    binding = config["HostConfig"]["PortBindings"][f"{BAY_PORT}/tcp"][0]
    assert binding == {"HostIp": "127.0.0.1", "HostPort": str(BAY_PORT)}


def _inspect(host_bindings, network_bindings=None):
    key = f"{BAY_PORT}/tcp"
    return {
        "HostConfig": {"PortBindings": {key: host_bindings}},
        "NetworkSettings": (
            {} if network_bindings is None else {"Ports": {key: network_bindings}}
        ),
    }


@pytest.mark.parametrize(
    ("host_bindings", "network_bindings"),
    [
        ([{"HostIp": "127.0.0.1", "HostPort": "8114"}], None),
        (
            [{"HostIp": "127.0.0.1", "HostPort": "8114"}],
            [{"HostIp": "127.0.0.1", "HostPort": "8114"}],
        ),
        (
            [{"HostIp": "::1", "HostPort": "8114"}],
            [{"HostIp": "::1", "HostPort": "8114"}],
        ),
    ],
)
def test_loopback_bound_reuses_container(host_bindings, network_bindings):
    existing = _inspect(host_bindings, network_bindings)

    assert BayContainerManager._is_loopback_bound(existing) is True


@pytest.mark.parametrize(
    "host_bindings",
    [
        [{"HostPort": "8114"}],
        [{"HostIp": "0.0.0.0", "HostPort": "8114"}],
        [{"HostIp": "", "HostPort": "8114"}],
        [{"HostIp": "::", "HostPort": "8114"}],
        ("unexpected",),
        [],
    ],
)
def test_non_loopback_or_missing_binding_is_rejected(host_bindings):
    existing = _inspect(host_bindings)

    assert BayContainerManager._is_loopback_bound(existing) is False


def test_effective_non_loopback_binding_is_rejected():
    existing = _inspect(
        [{"HostIp": "127.0.0.1", "HostPort": "8114"}],
        [{"HostIp": "0.0.0.0", "HostPort": "8114"}],
    )

    assert BayContainerManager._is_loopback_bound(existing) is False


def test_missing_port_bindings_are_rejected():
    assert BayContainerManager._is_loopback_bound({}) is False


@pytest.mark.asyncio
async def test_ensure_running_recreates_a_non_loopback_container(monkeypatch):
    from astrbot.core.computer.booters import bay_manager

    deleted: list[bool] = []
    created: list[dict] = []

    class FakeContainer:
        async def delete(self, *, force: bool = False) -> None:
            deleted.append(force)

        async def start(self) -> None:
            return None

    class FakeContainers:
        async def get(self, _container_id: str) -> FakeContainer:
            return FakeContainer()

        async def create_or_replace(self, _name: str, config: dict) -> FakeContainer:
            created.append(config)
            return FakeContainer()

    class FakeDocker:
        containers = FakeContainers()

    monkeypatch.setattr(bay_manager.aiodocker, "Docker", lambda: FakeDocker())

    manager = BayContainerManager()
    manager._find_managed_container = AsyncMock(
        return_value={
            "Id": "legacy-container",
            "State": {"Running": True},
            **_inspect([{"HostIp": "0.0.0.0", "HostPort": str(BAY_PORT)}]),
        }
    )
    manager._pull_image_if_needed = AsyncMock()

    endpoint = await manager.ensure_running()

    assert endpoint == f"http://127.0.0.1:{BAY_PORT}"
    assert deleted == [True]
    binding = created[0]["HostConfig"]["PortBindings"][f"{BAY_PORT}/tcp"][0]
    assert binding["HostIp"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_ensure_running_reuses_a_loopback_container(monkeypatch):
    from astrbot.core.computer.booters import bay_manager

    deleted: list[bool] = []
    created: list[dict] = []

    class FakeContainer:
        async def delete(self, *, force: bool = False) -> None:
            deleted.append(force)

        async def start(self) -> None:
            return None

    class FakeContainers:
        async def get(self, _container_id: str) -> FakeContainer:
            return FakeContainer()

        async def create_or_replace(self, _name: str, config: dict) -> FakeContainer:
            created.append(config)
            return FakeContainer()

    class FakeDocker:
        containers = FakeContainers()

    monkeypatch.setattr(bay_manager.aiodocker, "Docker", lambda: FakeDocker())

    manager = BayContainerManager()
    manager._find_managed_container = AsyncMock(
        return_value={
            "Id": "loopback-container",
            "State": {"Running": True},
            **_inspect([{"HostIp": "127.0.0.1", "HostPort": str(BAY_PORT)}]),
        }
    )
    manager._pull_image_if_needed = AsyncMock()

    endpoint = await manager.ensure_running()

    assert endpoint == f"http://127.0.0.1:{BAY_PORT}"
    assert deleted == []
    assert created == []
