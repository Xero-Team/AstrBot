import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import discovery
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.send_result import PlatformSendResult


def _make_manager() -> PlatformManager:
    return PlatformManager(
        {
            "platform": [],
            "platform_settings": {},
        },
        asyncio.Queue(),
    )


def test_platform_manager_sets_and_clears_concurrency_limit() -> None:
    manager = _make_manager()

    assert manager.get_platform_concurrency_limit("telegram") is None

    manager.set_platform_concurrency_limit("telegram", 2)
    assert manager.get_platform_concurrency_limit("telegram") == 2

    manager.set_platform_concurrency_limit("telegram", None)
    assert manager.get_platform_concurrency_limit("telegram") is None


def test_platform_manager_find_inst_by_name_returns_matching_adapter() -> None:
    manager = _make_manager()
    platform = MagicMock()
    platform.meta.return_value.name = "telegram"
    manager._platform_insts = [platform]

    result = manager._find_inst_by_name("telegram")

    assert result is platform


def test_platform_manager_get_platform_count_returns_loaded_adapter_count() -> None:
    manager = _make_manager()
    manager._platform_insts = [MagicMock(), MagicMock()]

    assert manager.get_platform_count() == 2


def test_platform_manager_find_inst_by_webhook_uuid_returns_only_unified_webhook():
    manager = _make_manager()
    matched = MagicMock()
    matched.config = {"webhook_uuid": "uuid-1"}
    matched.unified_webhook.return_value = True
    unmatched = MagicMock()
    unmatched.config = {"webhook_uuid": "uuid-1"}
    unmatched.unified_webhook.return_value = False
    manager._platform_insts = [unmatched, matched]

    result = manager.find_inst_by_webhook_uuid("uuid-1")

    assert result is matched


def test_platform_manager_rejects_invalid_concurrency_limit() -> None:
    manager = _make_manager()

    with pytest.raises(ValueError, match="platform concurrency limit must be >= 1"):
        manager.set_platform_concurrency_limit("telegram", 0)


@pytest.mark.asyncio
async def test_platform_manager_run_with_platform_limit_without_registered_limit():
    manager = _make_manager()

    async def operation() -> str:
        return "ok"

    result = await manager.run_with_platform_limit("telegram", operation)

    assert result == "ok"


@pytest.mark.asyncio
async def test_platform_manager_invoke_action_uses_registered_platform_limit():
    manager = _make_manager()
    manager.set_platform_concurrency_limit("telegram", 1)
    events: list[str] = []
    release = asyncio.Event()

    async def action_handler(*, value: str) -> dict[str, object]:
        events.append(f"start:{value}")
        await release.wait()
        events.append(f"end:{value}")
        return {"value": value}

    platform = MagicMock()
    platform.supports_action.return_value = True
    platform.some_action = action_handler
    manager._find_inst_by_id = MagicMock(return_value=platform)

    first = asyncio.create_task(
        manager.invoke_action("telegram", "some_action", value="first")
    )
    await asyncio.sleep(0)
    second = asyncio.create_task(
        manager.invoke_action("telegram", "some_action", value="second")
    )
    await asyncio.sleep(0)

    assert events == ["start:first"]

    release.set()
    first_result = await first
    second_result = await second

    assert first_result == {"value": "first"}
    assert second_result == {"value": "second"}
    assert events == [
        "start:first",
        "end:first",
        "start:second",
        "end:second",
    ]


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_uses_registered_platform_limit():
    manager = _make_manager()
    manager.set_platform_concurrency_limit("telegram", 1)
    events: list[str] = []
    release = asyncio.Event()
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])

    async def send_by_session(_session, _chain) -> PlatformSendResult:
        events.append("start")
        await release.wait()
        events.append("end")
        return PlatformSendResult(
            platform_id="telegram",
            success=True,
            target="chat-1",
            message_count=1,
        )

    platform = MagicMock()
    platform.send_by_session = AsyncMock(side_effect=send_by_session)
    manager._find_inst_by_id = MagicMock(return_value=platform)

    first = asyncio.create_task(manager.send_to_session(session, chain))
    await asyncio.sleep(0)
    second = asyncio.create_task(manager.send_to_session(session, chain))
    await asyncio.sleep(0)

    assert events == ["start"]

    release.set()
    first_result = await first
    second_result = await second

    assert first_result.success is True
    assert second_result.success is True
    assert events == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_returns_failure_when_missing():
    manager = _make_manager()
    manager._find_inst_by_id = MagicMock(return_value=None)
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])

    result = await manager.send_to_session(session, chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="platform adapter not found",
    )


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_normalizes_legacy_none_result():
    manager = _make_manager()
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])
    platform = MagicMock()
    platform.send_by_session = AsyncMock(return_value=None)
    manager._find_inst_by_id = MagicMock(return_value=platform)

    result = await manager.send_to_session(session, chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=True,
        target="chat-1",
        message_count=1,
    )


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_returns_failure_when_adapter_raises():
    manager = _make_manager()
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])
    platform = MagicMock()
    platform.send_by_session = AsyncMock(
        side_effect=RuntimeError("adapter rejected payload")
    )
    manager._find_inst_by_id = MagicMock(return_value=platform)

    result = await manager.send_to_session(session, chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="adapter rejected payload",
    )


@pytest.mark.asyncio
async def test_platform_manager_terminate_platform_clears_platform_limit():
    manager = _make_manager()
    manager.set_platform_concurrency_limit("telegram", 2)
    platform = MagicMock()
    platform.client_self_id = "client-1"
    manager._inst_map["telegram"] = {
        "inst": platform,
        "client_id": "client-1",
    }
    manager._platform_insts = [platform]
    manager._terminate_inst_and_tasks = AsyncMock()

    await manager.terminate_platform("telegram")

    assert manager.get_platform_concurrency_limit("telegram") is None


@pytest.mark.asyncio
async def test_platform_manager_serializes_disable_then_enable_reload(monkeypatch):
    manager = _make_manager()
    first_termination_started = asyncio.Event()
    allow_first_termination = asyncio.Event()
    events: list[str] = []
    termination_count = 0

    async def terminate_platform_unlocked(platform_id: str) -> None:
        nonlocal termination_count
        termination_count += 1
        events.append(f"terminate:{platform_id}:{termination_count}")
        if termination_count == 1:
            first_termination_started.set()
            await allow_first_termination.wait()

    async def load_platform_unlocked(platform_config: dict) -> None:
        events.append(f"load:{platform_config['id']}")

    monkeypatch.setattr(
        manager,
        "_terminate_platform_unlocked",
        terminate_platform_unlocked,
    )
    monkeypatch.setattr(
        manager,
        "_load_platform_unlocked",
        load_platform_unlocked,
    )

    disable_task = asyncio.create_task(
        manager.reload({"enable": False, "id": "napcat", "type": "napcat"})
    )
    await first_termination_started.wait()
    enable_task = asyncio.create_task(
        manager.reload({"enable": True, "id": "napcat", "type": "napcat"})
    )
    await asyncio.sleep(0)

    assert events == ["terminate:napcat:1"]

    allow_first_termination.set()
    await asyncio.gather(disable_task, enable_task)

    assert events == [
        "terminate:napcat:1",
        "terminate:napcat:2",
        "load:napcat",
    ]


def test_platform_manager_create_event_falls_back_to_platform_name() -> None:
    manager = _make_manager()
    platform = MagicMock()
    platform.create_event.return_value = MagicMock()
    manager._find_inst_by_id = MagicMock(return_value=None)
    manager._find_inst_by_name = MagicMock(return_value=platform)

    manager.create_event("telegram", MagicMock(), is_wake=False)

    manager._find_inst_by_id.assert_called_once_with("telegram")
    manager._find_inst_by_name.assert_called_once_with("telegram")
    platform.create_event.assert_called_once()
    platform.commit_event.assert_called_once()
    assert platform.commit_event.call_args.args[0].is_wake is False


def test_platform_discovery_imports_registered_builtin_adapter_once(monkeypatch):
    adapter_type = "test-adapter"
    module_name = "astrbot.core.platform.sources.test_adapter"
    adapter = type("TestAdapter", (), {})
    imported = []
    monkeypatch.setattr(
        discovery, "BUILTIN_PLATFORM_MODULES", {adapter_type: module_name}
    )
    monkeypatch.setattr(discovery, "platform_cls_map", {})

    def import_module(name):
        imported.append(name)
        discovery.platform_cls_map[adapter_type] = adapter

    monkeypatch.setattr(discovery.importlib, "import_module", import_module)

    assert discovery.discover_platform_adapter(adapter_type) is adapter
    assert discovery.discover_platform_adapter(adapter_type) is adapter
    assert imported == [module_name]


@pytest.mark.asyncio
async def test_platform_manager_skips_disabled_and_unknown_platform(monkeypatch):
    manager = _make_manager()
    discover = MagicMock(return_value=None)
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter", discover
    )

    await manager.load_platform({"enable": False, "id": "disabled", "type": "x"})
    await manager.load_platform({"enable": True, "id": "unknown", "type": "x"})

    assert discover.call_args_list == [(("x",), {})]
    assert manager._platform_insts == []
