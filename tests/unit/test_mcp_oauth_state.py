import asyncio

import pytest

from astrbot.core.agent.mcp_client import (
    MAX_PENDING_OAUTH_STATES,
    MCPAuthorizationCoordinator,
)


@pytest.mark.asyncio
async def test_abandoned_oauth_states_are_bounded() -> None:
    coordinator = MCPAuthorizationCoordinator()
    try:
        for index in range(MAX_PENDING_OAUTH_STATES + 10):
            await coordinator.redirect_handler(
                "server",
                f"https://example.test/authorize?state=s{index}",
            )

        assert len(coordinator._states) == MAX_PENDING_OAUTH_STATES
        assert "s0" not in coordinator._states
        assert f"s{MAX_PENDING_OAUTH_STATES + 9}" in coordinator._states
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_reset_identity_discards_previous_attempt() -> None:
    coordinator = MCPAuthorizationCoordinator()
    try:
        url = "https://example.test/authorize?state=old"
        await coordinator.redirect_handler("server", url)
        assert await coordinator.wait_for_url("server") == url

        await coordinator.reset_identity("server")

        assert coordinator._urls == {}
        assert "old" not in coordinator._states
    finally:
        await coordinator.close()


@pytest.mark.asyncio
async def test_callback_handler_starts_fresh_after_completion() -> None:
    coordinator = MCPAuthorizationCoordinator()
    try:
        first = asyncio.create_task(coordinator.callback_handler("server"))
        await asyncio.sleep(0)
        assert await coordinator.complete_callback("server", "code-1", "state-1", None)
        assert (await first).code == "code-1"

        second = asyncio.create_task(coordinator.callback_handler("server"))
        await asyncio.sleep(0)
        assert not second.done()
        assert await coordinator.complete_callback("server", "code-2", "state-2", None)
        assert (await second).code == "code-2"
    finally:
        await coordinator.close()
