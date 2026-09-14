"""Tests for the BTW work-submission hand-off and its built-in tool."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.btw import runtime_registry
from astrbot.core.agent.btw.runtime_registry import config_id_of
from astrbot.core.agent.btw.submission import (
    submit_work_task,
    work_event_for,
)
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.tools.work_tools import SubmitWorkTaskTool

UMO = "webchat:FriendMessage:webchat!user!session"


class StubWorkExecutor:
    """An Agent executor that holds one work run open until it is released."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.events: list[object] = []

    async def process(self, event):
        self.events.append(event)
        self.started.set()
        await self.release.wait()
        for _ in ():
            yield


def _requesting_event(*, config_id: str = "default"):
    subject = Subject.dashboard_account("account-1", "user")
    resource = Resource.session(config_id, UMO)
    return SimpleNamespace(
        unified_msg_origin=UMO,
        subject=subject,
        resource=resource,
        platform_member_role="instance_operator",
        platform_role_source="config",
        platform_role_expires_at=None,
        auth_context=AuthContext(
            subject=subject,
            source="webchat",
            config_id=config_id,
            authenticated=True,
            origin_session_resource_id=resource.id,
            step_up_token="raw-proof",
            metadata={
                "dashboard_session_id": "sid-1",
                "webchat_step_up_tokens": {"tool.local_exec": "raw-proof"},
                "_webchat_step_up_consumed": {"tool.local_exec": "consumed"},
            },
        ),
    )


def _work_loop_context() -> SimpleNamespace:
    return SimpleNamespace(
        send_message=AsyncMock(),
        active_event_registry=SimpleNamespace(
            register=MagicMock(),
            unregister=MagicMock(),
        ),
    )


async def _register_work_loop(config_id: str):
    executor = StubWorkExecutor()
    work_loop = WorkLoop(executor, WorkSessionManager())
    work_loop.configure_detached_execution(
        background_tasks=set(),
        result_dispatcher=AsyncMock(),
        event_finalizer=AsyncMock(),
    )
    runtime_registry.register_work_loop(config_id, work_loop)
    return executor, work_loop


def test_config_id_of_reads_the_profile_resource():
    assert config_id_of(_requesting_event(config_id="other")) == "other"
    assert config_id_of(SimpleNamespace()) == ""


def test_work_event_mirrors_identity_without_a_consumed_proof():
    """A handed-over task keeps the subject and role, not the request proof."""
    event = _requesting_event()

    work_event = work_event_for(_work_loop_context(), event, "the task")

    assert work_event.unified_msg_origin == UMO
    assert work_event.message_str == "the task"
    assert work_event.get_extra("btw_loop") == "work"
    assert work_event.platform_member_role == "instance_operator"
    assert work_event.platform_role_source == "config"
    assert work_event.resource is event.resource
    assert work_event.subject is event.subject
    assert work_event.auth_context.request_id != event.auth_context.request_id
    assert work_event.auth_context.step_up_token is None
    assert work_event.auth_context.metadata == {"dashboard_session_id": "sid-1"}


@pytest.mark.asyncio
async def test_submit_work_task_hands_the_task_to_the_profile_work_loop():
    executor, work_loop = await _register_work_loop("profile-a")
    try:
        session = await submit_work_task(
            _work_loop_context(),
            _requesting_event(config_id="profile-a"),
            "  run the tools  ",
        )

        assert session is not None
        assert session.request == "run the tools"
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        [work_event] = executor.events
        assert work_event.message_str == "run the tools"
        assert work_event.unified_msg_origin == UMO
        assert work_event.get_extra("btw_loop") == "work"
        executor.release.set()
        await asyncio.wait_for(work_loop.close(), timeout=5)
    finally:
        runtime_registry.unregister_work_loop("profile-a", work_loop)


@pytest.mark.asyncio
async def test_submit_work_task_ignores_an_empty_task():
    executor, work_loop = await _register_work_loop("profile-b")
    try:
        assert (
            await submit_work_task(
                _work_loop_context(),
                _requesting_event(config_id="profile-b"),
                "   ",
            )
            is None
        )
        assert not executor.started.is_set()
    finally:
        runtime_registry.unregister_work_loop("profile-b", work_loop)


@pytest.mark.asyncio
async def test_submit_work_task_returns_none_without_a_work_loop():
    assert (
        await submit_work_task(
            _work_loop_context(),
            _requesting_event(config_id="profile-missing"),
            "run the tools",
        )
        is None
    )


@pytest.mark.asyncio
async def test_tool_reports_submission_without_waiting_for_the_work():
    executor, work_loop = await _register_work_loop("profile-c")
    tool = SubmitWorkTaskTool()
    run_context = SimpleNamespace(
        context=SimpleNamespace(
            event=_requesting_event(config_id="profile-c"),
            context=_work_loop_context(),
        )
    )
    try:
        result = await tool.call(run_context, prompt="run the tools")

        assert "submitted" in result
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        executor.release.set()
        await asyncio.wait_for(work_loop.close(), timeout=5)
    finally:
        runtime_registry.unregister_work_loop("profile-c", work_loop)


@pytest.mark.asyncio
async def test_tool_answers_directly_when_no_work_loop_is_available():
    tool = SubmitWorkTaskTool()
    run_context = SimpleNamespace(
        context=SimpleNamespace(
            event=_requesting_event(config_id="profile-none"),
            context=_work_loop_context(),
        )
    )

    result = await tool.call(run_context, prompt="run the tools")

    assert result.startswith("error:")


@pytest.mark.asyncio
async def test_submit_work_task_registers_the_run_for_stop():
    executor, work_loop = await _register_work_loop("profile-d")
    context = _work_loop_context()
    try:
        session = await submit_work_task(
            context,
            _requesting_event(config_id="profile-d"),
            "run the tools",
        )

        assert session is not None
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        [work_event] = executor.events
        context.active_event_registry.register.assert_called_once_with(work_event)
        executor.release.set()
        await asyncio.wait_for(work_loop.close(), timeout=5)
    finally:
        runtime_registry.unregister_work_loop("profile-d", work_loop)


@pytest.mark.asyncio
async def test_submit_work_task_reports_a_failed_hand_off():
    """A work loop that cannot run detached leaves no run registered."""
    work_loop = WorkLoop(StubWorkExecutor(), WorkSessionManager())
    runtime_registry.register_work_loop("profile-e", work_loop)
    context = _work_loop_context()
    try:
        session = await submit_work_task(
            context,
            _requesting_event(config_id="profile-e"),
            "run the tools",
        )

        assert session is None
        context.active_event_registry.register.assert_called_once()
        context.active_event_registry.unregister.assert_called_once()
    finally:
        runtime_registry.unregister_work_loop("profile-e", work_loop)
