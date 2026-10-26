"""ComputerRuntime ownership of the Local proxy."""

from __future__ import annotations

import sys

import pytest

from astrbot.core.computer.computer_client import ComputerRuntime


@pytest.mark.asyncio
@pytest.mark.skipif(
    not sys.platform.startswith(("linux", "darwin")),
    reason="The Local sandbox proxy is not supported on this platform.",
)
async def test_runtime_starts_and_stops_one_local_proxy() -> None:
    runtime = ComputerRuntime()
    try:
        booter = runtime.get_local_booter()
        assert booter is runtime.get_local_booter()
        proxy = runtime.get_local_proxy()
        assert proxy is runtime.get_local_proxy()
        assert proxy.state == "running"
    finally:
        await runtime.terminate()
    assert proxy.state == "stopped"
    with pytest.raises(RuntimeError, match="terminated"):
        runtime.get_local_booter()
    with pytest.raises(RuntimeError, match="terminated"):
        runtime.get_local_proxy()


@pytest.mark.asyncio
async def test_runtime_termination_is_idempotent() -> None:
    runtime = ComputerRuntime()
    await runtime.terminate()
    await runtime.terminate()


@pytest.mark.asyncio
async def test_local_booter_receives_the_runtime_proxy_provider() -> None:
    runtime = ComputerRuntime()
    try:
        booter = runtime.get_local_booter()
        provider = booter._proxy_provider  # noqa: SLF001
        assert provider is not None
        assert provider.__self__ is runtime  # type: ignore[attr-defined]
        assert provider.__func__ is runtime.get_local_proxy.__func__  # type: ignore[attr-defined]
        shell_provider = booter.shell.proxy_provider  # noqa: SLF001
        assert shell_provider is not None
        assert shell_provider.__self__ is runtime  # type: ignore[attr-defined]
    finally:
        await runtime.terminate()
