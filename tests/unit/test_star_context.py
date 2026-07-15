from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata, star_registry
from astrbot.core.star.star_tools import StarTools


@pytest.fixture(autouse=True)
def restore_star_registry():
    original_registry = list(star_registry)
    star_registry.clear()
    try:
        yield
    finally:
        star_registry[:] = original_registry


def make_context() -> Context:
    context = Context.__new__(Context)
    context.provider_manager = SimpleNamespace(llm_tools=FunctionToolManager())
    return context


def make_initialized_context() -> Context:
    from asyncio import Queue

    return Context(
        Queue(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )


def make_tool(name: str, module_path: str) -> FunctionTool:
    tool = FunctionTool(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
    )
    tool.__module__ = module_path
    return tool


def test_add_llm_tools_resolves_subdirectory_plugin_without_name_prefix():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.main",
        )
    )
    context = make_context()
    tool = make_tool("search", "custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.main"


def test_add_llm_tools_uses_registered_non_main_plugin_entrypoint():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            module_path="data.plugins.custom_plugin.custom_plugin",
        )
    )
    context = make_context()
    tool = make_tool("search", "custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.custom_plugin"


def test_add_llm_tools_resolves_prefixed_subdirectory_tool_from_registry():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.custom_plugin",
        )
    )
    context = make_context()
    tool = make_tool("search", "data.plugins.custom_plugin.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "data.plugins.custom_plugin.custom_plugin"


def test_add_llm_tools_does_not_treat_unknown_module_as_plugin():
    star_registry.append(
        StarMetadata(
            name="Custom Plugin",
            root_dir_name="custom_plugin",
            module_path="data.plugins.custom_plugin.main",
        )
    )
    context = make_context()
    tool = make_tool("search", "external_package.tools.search")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == "external_package.tools.search"


def test_add_llm_tools_handles_empty_tool_module_path():
    context = make_context()
    tool = make_tool("search", "")

    context.add_llm_tools(tool)

    assert tool.handler_module_path == ""


def test_context_mutable_state_is_not_shared_between_instances():
    first = make_initialized_context()
    second = make_initialized_context()

    first.registered_web_apis.append(("route", MagicMock(), ["GET"], "desc"))
    first.register_task(SimpleNamespace(), "task")
    first._star_manager = object()

    assert second.registered_web_apis == []
    assert second._register_tasks == []
    assert second._star_manager is None


def test_context_commit_event_returns_false_when_queue_is_full():
    from asyncio import Queue

    context = make_initialized_context()
    context._event_queue = Queue(maxsize=1)
    context._event_queue.put_nowait(SimpleNamespace(unified_msg_origin="first"))

    result = context.commit_event(SimpleNamespace(unified_msg_origin="second"))

    assert result is False


@pytest.mark.asyncio
async def test_send_message_returns_platform_send_result():
    context = make_initialized_context()
    context._platform_manager.send_to_session = AsyncMock(
        return_value=PlatformSendResult(
            platform_id="telegram",
            success=True,
            target="chat-1",
            message_count=1,
        )
    )
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    message_chain = MessageChain(chain=[Plain("hello")])

    result = await context.send_message(session, message_chain)

    assert result.success is True
    assert result.platform_id == "telegram"
    assert result.target == "chat-1"
    context._platform_manager.send_to_session.assert_awaited_once_with(
        session, message_chain
    )


@pytest.mark.asyncio
async def test_send_message_returns_failure_when_platform_missing():
    context = make_initialized_context()
    context._platform_manager.send_to_session = AsyncMock(
        return_value=PlatformSendResult(
            platform_id="telegram",
            success=False,
            target="chat-1",
            message_count=1,
            error_message="platform adapter not found",
        )
    )
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    message_chain = MessageChain(chain=[Plain("hello")])

    result = await context.send_message(session, message_chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="platform adapter not found",
    )
    context._platform_manager.send_to_session.assert_awaited_once_with(
        session, message_chain
    )


@pytest.mark.asyncio
async def test_send_message_returns_failure_when_adapter_rejects_payload():
    context = make_initialized_context()
    context._platform_manager.send_to_session = AsyncMock(
        return_value=PlatformSendResult(
            platform_id="telegram",
            success=False,
            target="chat-1",
            message_count=1,
            error_message="adapter rejected payload",
        )
    )
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    message_chain = MessageChain(chain=[Plain("hello")])

    result = await context.send_message(session, message_chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="adapter rejected payload",
    )
    context._platform_manager.send_to_session.assert_awaited_once_with(
        session, message_chain
    )


@pytest.mark.asyncio
async def test_context_invoke_platform_action_delegates_to_platform_manager():
    context = make_initialized_context()
    context._platform_manager.invoke_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )

    result = await context.invoke_platform_action(
        "telegram",
        "send_poke",
        user_id="123456",
    )

    assert result == {"status": "ok", "data": {"done": True}}
    context._platform_manager.invoke_action.assert_awaited_once_with(
        "telegram",
        "send_poke",
        user_id="123456",
    )


@pytest.mark.asyncio
async def test_context_invoke_event_platform_action_uses_event_platform_id():
    context = make_initialized_context()
    context.invoke_platform_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )
    event = MagicMock()
    event.get_platform_id.return_value = "telegram"

    result = await context.invoke_event_platform_action(
        event,
        "send_poke",
        user_id="123456",
    )

    assert result == {"status": "ok", "data": {"done": True}}
    context.invoke_platform_action.assert_awaited_once_with(
        "telegram",
        "send_poke",
        user_id="123456",
    )


@pytest.mark.asyncio
async def test_startools_create_event_prefers_platform_id_lookup():
    context = make_initialized_context()
    context.create_platform_event = MagicMock()

    StarTools.initialize(context)
    try:
        await StarTools.create_event(MagicMock(), platform="telegram", is_wake=False)
    finally:
        StarTools._context = None

    context.create_platform_event.assert_called_once_with(
        "telegram",
        ANY,
        is_wake=False,
    )


def test_context_create_platform_event_delegates_to_platform_manager():
    context = make_initialized_context()
    context._platform_manager.create_event = MagicMock()
    payload = MagicMock()

    context.create_platform_event("telegram", payload, is_wake=True)

    context._platform_manager.create_event.assert_called_once_with(
        "telegram",
        payload,
        is_wake=True,
    )


def test_context_create_platform_event_propagates_platform_error():
    context = make_initialized_context()
    context._platform_manager.create_event = MagicMock(
        side_effect=ValueError("Platform not found: telegram")
    )

    with pytest.raises(ValueError, match="Platform not found: telegram"):
        context.create_platform_event("telegram", MagicMock())


@pytest.mark.asyncio
async def test_startools_invoke_platform_action_uses_context_boundary():
    context = make_initialized_context()
    context.invoke_platform_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )

    StarTools.initialize(context)
    try:
        result = await StarTools.invoke_platform_action(
            "telegram",
            "send_poke",
            user_id="123456",
        )
    finally:
        StarTools._context = None

    assert result == {"status": "ok", "data": {"done": True}}
    context.invoke_platform_action.assert_awaited_once_with(
        "telegram",
        "send_poke",
        user_id="123456",
    )


@pytest.mark.asyncio
async def test_startools_invoke_event_platform_action_uses_context_boundary():
    context = make_initialized_context()
    context.invoke_event_platform_action = AsyncMock(
        return_value={"status": "ok", "data": {"done": True}}
    )
    event = MagicMock()

    StarTools.initialize(context)
    try:
        result = await StarTools.invoke_event_platform_action(
            event,
            "send_poke",
            user_id="123456",
        )
    finally:
        StarTools._context = None

    assert result == {"status": "ok", "data": {"done": True}}
    context.invoke_event_platform_action.assert_awaited_once_with(
        event,
        "send_poke",
        user_id="123456",
    )


def test_context_does_not_expose_platform_manager_attribute():
    context = make_initialized_context()

    assert not hasattr(context, "platform_manager")
