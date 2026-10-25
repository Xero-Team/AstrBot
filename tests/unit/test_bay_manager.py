from astrbot.core.computer.booters.bay_manager import BAY_PORT, BayContainerManager


def test_bay_container_port_is_bound_to_loopback():
    manager = BayContainerManager()

    config = manager._build_container_config()

    binding = config["HostConfig"]["PortBindings"][f"{BAY_PORT}/tcp"][0]
    assert binding == {"HostIp": "127.0.0.1", "HostPort": str(BAY_PORT)}
