"""Exercise a few contract helpers that are easy to miss in unit tests."""

from __future__ import annotations

import asyncio

import pytest


def test_star_handler_register_decorators_execute():
    from astrbot.core.star.register import star_handler as register

    async def dummy(*_args, **_kwargs):
        return None

    dummy.__module__ = "tests.dummy_plugin"
    dummy.__qualname__ = "dummy"
    dummy.__name__ = "dummy"

    applied = 0
    for name in (
        "register_on_astrbot_loaded",
        "register_on_platform_loaded",
        "register_on_plugin_error",
        "register_on_plugin_loaded",
        "register_on_plugin_unloaded",
        "register_on_waiting_llm_request",
        "register_on_llm_request",
        "register_on_llm_response",
        "register_on_agent_begin",
        "register_on_agent_done",
        "register_on_using_llm_tool",
        "register_on_llm_tool_respond",
        "register_on_decorating_result",
        "register_after_message_sent",
        "register_on_assistant_history_finalized",
        "register_regex",
        "register_command",
        "register_llm_tool",
        "register_permission",
        "register_event_message_type",
        "register_platform_adapter_type",
        "register_agent",
    ):
        factory = getattr(register, name)
        try:
            decorator = factory()
        except TypeError:
            try:
                decorator = factory("help")
            except Exception:
                continue
        if not callable(decorator):
            continue
        try:
            decorator(dummy)
            applied += 1
        except Exception:
            continue
    assert applied >= 5


@pytest.mark.asyncio
async def test_tracked_task_wraps_non_coroutine_awaitables():
    from astrbot.core.utils.task_utils import create_tracked_task

    future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    future.set_result(7)
    tasks: set[asyncio.Task] = set()
    task = create_tracked_task(tasks, future, name="future-wrap")
    assert await task == 7
