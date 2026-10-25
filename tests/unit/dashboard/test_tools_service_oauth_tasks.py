import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

import astrbot.dashboard.services.tools_service as tools_service_module
from astrbot.dashboard.services.tools_service import ToolsService


def _service(client: Any, *, authorization_url: str | None = None) -> ToolsService:
    tool_manager = SimpleNamespace(
        load_mcp_config=lambda: {"mcpServers": {"server": {"auth_ref": "auth-1"}}},
        mcp_server_runtime_view={"server": SimpleNamespace(client=client)},
        mcp_authorization_coordinator=SimpleNamespace(
            reset_identity=AsyncMock(),
            wait_for_url=AsyncMock(return_value=authorization_url),
        ),
    )
    return ToolsService(
        cast(Any, tool_manager),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
    )


@pytest.mark.asyncio
async def test_oauth_catalog_refresh_is_tracked_until_completion() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def list_tools_and_save() -> None:
        started.set()
        await release.wait()

    client = SimpleNamespace(
        connection_status="connected",
        list_tools_and_save=list_tools_and_save,
    )
    service = _service(client)

    result = await service.start_mcp_authorization("server")

    assert result == {"status": "pending"}
    await asyncio.wait_for(started.wait(), timeout=1)
    assert len(service._background_tasks) == 1

    release.set()
    for _ in range(10):
        if not service._background_tasks:
            break
        await asyncio.sleep(0)

    assert service._background_tasks == set()


@pytest.mark.asyncio
async def test_completed_oauth_probe_is_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup = AsyncMock()

    class _FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def connect_to_server(self, *_args: Any, **_kwargs: Any) -> None:
            raise ValueError("probe failed")

        async def cleanup(self) -> None:
            await cleanup()

    monkeypatch.setattr(tools_service_module, "MCPClient", _FakeClient)
    tool_manager = SimpleNamespace(
        load_mcp_config=lambda: {"mcpServers": {"server": {"auth_ref": "auth-1"}}},
        mcp_server_runtime_view={},
        mcp_interaction_coordinator=None,
        mcp_auth_store=object(),
        mcp_authorization_coordinator=SimpleNamespace(
            reset_identity=AsyncMock(),
            wait_for_url=AsyncMock(return_value=None),
        ),
    )
    service = ToolsService(
        cast(Any, tool_manager),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
    )

    result = await service.start_mcp_authorization("server")

    assert result == {"status": "pending"}
    for _ in range(10):
        if not service._oauth_probe_tasks:
            break
        await asyncio.sleep(0)

    assert service._oauth_probe_tasks == {}
    cleanup.assert_awaited_once()
