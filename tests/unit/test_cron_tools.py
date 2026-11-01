"""Tests for cron tool metadata."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.auth.models import AuthContext, Resource, Role, Subject
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.platform.message_type import MessageType
from astrbot.core.tools.cron_tools import FutureTaskTool
from astrbot.core.tools.function_tool_manager import FunctionToolManager

_UMO = "telegram:GroupMessage:shared"


def _allowing_authorization() -> SimpleNamespace:
    return SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )


def _denying_authorization() -> SimpleNamespace:
    return SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=False))
    )


def _context(
    cron_mgr,
    *,
    umo: str = "test:group:shared",
    sender_id: str = "user-1",
    tz_name: str | None = None,
    message_type: MessageType = MessageType.GROUP_MESSAGE,
    authorization=None,
    manages: bool = False,
):
    event = SimpleNamespace(
        unified_msg_origin=umo,
        get_sender_id=lambda: sender_id,
        get_message_type=lambda: message_type,
    )
    if authorization is not None:
        event.subject = object()
        event.resource = SimpleNamespace(config_id="default")
        event.auth_context = object()
    return SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(
                cron_manager=cron_mgr,
                get_config=lambda umo=None: {"timezone": tz_name},
                authorization=authorization,
            ),
            event=event,
        )
    )


def _job(job_id: str, *, umo: str = "test:group:shared", sender_id: str = "user-1"):
    return SimpleNamespace(
        job_id=job_id,
        name=f"name-{job_id}",
        job_type="active_agent",
        run_once=False,
        cron_expression="0 8 * * *",
        enabled=True,
        next_run_time=None,
        payload={
            "session": umo,
            "sender_id": sender_id,
            "note": f"note-{job_id}",
            "origin": "tool",
        },
    )


@pytest_asyncio.fixture
async def authorization(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "authorization.db"))
    await db.initialize()
    service = AuthorizationService(db)
    await service.start()
    try:
        yield service
    finally:
        await service.close()
        await db.close()


def _im_subject(sender_id: str) -> Subject:
    return Subject.im(
        platform_instance="telegram", bot_account_id="bot", sender_id=sender_id
    )


def _session_resource() -> Resource:
    return Resource.session("default", _UMO)


def _executor_event(subject: Subject, resource: Resource, sender_id: str):
    return SimpleNamespace(
        unified_msg_origin=_UMO,
        get_sender_id=lambda: sender_id,
        get_message_type=lambda: MessageType.GROUP_MESSAGE,
        subject=subject,
        resource=resource,
        auth_context=AuthContext(
            subject=subject,
            source="im",
            config_id=resource.config_id,
            authenticated=True,
            origin_session_resource_id=resource.id,
            message_type="group",
        ),
    )


def _executor_context(event, authorization, cron_mgr):
    return ContextWrapper(
        context=SimpleNamespace(
            event=event,
            context=SimpleNamespace(
                authorization=authorization,
                cron_manager=cron_mgr,
            ),
        )
    )


def _registered_future_task_tool():
    """Return the future_task tool exactly as the runtime registers it."""
    return FunctionToolManager().get_builtin_tool("future_task")


async def _execute_through_executor(tool, run_context, **tool_args) -> str:
    """Run one call through the real execution and authorization boundary."""
    return "".join(
        [
            content.text
            async for result in FunctionToolExecutor.execute(
                tool, run_context, **tool_args
            )
            for content in result.content
            if getattr(content, "text", None)
        ]
    )


def test_future_task_schema_has_action_and_create_cron_guidance():
    """The merged tool should expose action routing and unambiguous cron guidance."""
    tool = FutureTaskTool()

    assert tool.name == "future_task"
    assert tool.parameters["required"] == ["action"]
    assert tool.parameters["properties"]["action"]["enum"] == [
        "create",
        "edit",
        "delete",
        "list",
    ]

    description = tool.parameters["properties"]["cron_expression"]["description"]

    assert "mon-fri" in description
    assert "sat,sun" in description
    assert "1-5" in description
    assert "Prefer named weekdays" in description


def test_future_task_schema_has_no_job_type_and_delete_job_id():
    """The merged tool should remove job_type and document delete requirements."""
    tool = FutureTaskTool()

    assert "job_type" not in tool.parameters["properties"]
    action_description = tool.parameters["properties"]["action"]["description"]
    job_id_description = tool.parameters["properties"]["job_id"]["description"]

    assert "'edit' requires 'job_id'" in action_description
    assert "Required for 'delete' and 'edit'" in job_id_description


@pytest.mark.asyncio
async def test_future_task_edit_requires_job_id():
    """Edit mode should require job_id."""
    tool = FutureTaskTool()
    cron_mgr = SimpleNamespace()

    result = await tool.call(
        _context(
            cron_mgr,
            umo="test:private:session",
            message_type=MessageType.FRIEND_MESSAGE,
        ),
        action="edit",
    )

    assert result == "error: job_id is required when action=edit."

    assert result == "error: job_id is required when action=edit."


@pytest.mark.asyncio
async def test_future_task_edit_updates_existing_job():
    """Edit mode should update note and one-time scheduling fields."""
    tool = FutureTaskTool()
    existing_job = SimpleNamespace(
        job_id="job-1",
        name="old name",
        job_type="active_agent",
        run_once=False,
        cron_expression="0 8 * * *",
        payload={
            "session": "test:private:session",
            "sender_id": "user-1",
            "note": "old note",
            "origin": "tool",
        },
    )
    updated_job = SimpleNamespace(
        job_id="job-1",
        name="new name",
        run_once=True,
        cron_expression=None,
        next_run_time=None,
    )
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        update_job=AsyncMock(return_value=updated_job),
    )

    result = await tool.call(
        _context(
            cron_mgr,
            umo="test:private:session",
            message_type=MessageType.FRIEND_MESSAGE,
        ),
        action="edit",
        job_id="job-1",
        name="new name",
        note="new note",
        run_once=True,
        run_at="2026-02-02T08:00:00+08:00",
    )

    cron_mgr.update_job.assert_awaited_once_with(
        "job-1",
        name="new name",
        description="new note",
        run_once=True,
        cron_expression=None,
        payload={
            "session": "test:private:session",
            "sender_id": "user-1",
            "note": "new note",
            "origin": "tool",
            "run_at": "2026-02-02T08:00:00+08:00",
        },
    )
    assert result == "Updated future task job-1 (new name)."


@pytest.mark.asyncio
async def test_future_task_edit_rejects_same_umo_different_sender():
    """Same-session users should not edit another sender's task."""
    tool = FutureTaskTool()
    existing_job = _job("job-1", sender_id="admin-user")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        update_job=AsyncMock(),
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="attacker-user"),
        action="edit",
        job_id="job-1",
        note="attacker note",
    )

    assert "created by another member of this group chat" in result
    cron_mgr.update_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_delete_rejects_same_umo_different_sender():
    """Same-session users should not delete another sender's task."""
    tool = FutureTaskTool()
    existing_job = _job("job-1", sender_id="admin-user")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        delete_job=AsyncMock(),
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="attacker-user"),
        action="delete",
        job_id="job-1",
    )

    assert "created by another member of this group chat" in result
    cron_mgr.delete_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_list_filters_by_umo_and_sender():
    """Private-chat list mode shows only tasks owned by the current sender."""
    tool = FutureTaskTool()
    own_job = _job("own-job", sender_id="user-1")
    same_umo_other_sender = _job("other-sender-job", sender_id="user-2")
    different_umo_same_sender = _job(
        "other-umo-job",
        umo="test:group:other",
        sender_id="user-1",
    )
    cron_mgr = SimpleNamespace(
        list_jobs=AsyncMock(
            return_value=[own_job, same_umo_other_sender, different_umo_same_sender]
        )
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="user-1", message_type=MessageType.FRIEND_MESSAGE),
        action="list",
    )

    assert "own-job" in result
    assert "other-sender-job" not in result
    assert "other-umo-job" not in result
    assert "tasks in this chat that were not created by you" in result


@pytest.mark.asyncio
async def test_future_task_list_shares_group_tasks_with_creator():
    """Every group member sees all tasks in the group with their creators."""
    tool = FutureTaskTool()
    own_job = _job("own-job", sender_id="user-1")
    other_sender_job = _job("other-sender-job", sender_id="user-2")
    dashboard_job = _job("dashboard-job")
    dashboard_job.payload.pop("sender_id")
    different_umo_job = _job("other-umo-job", umo="test:group:other")
    cron_mgr = SimpleNamespace(
        list_jobs=AsyncMock(
            return_value=[own_job, other_sender_job, dashboard_job, different_umo_job]
        )
    )

    result = await tool.call(_context(cron_mgr, sender_id="user-1"), action="list")

    assert "own-job" in result
    assert "other-sender-job" in result
    assert "creator=user-2" in result
    assert "dashboard-job" in result
    assert "creator=unknown" in result
    assert "other-umo-job" not in result
    assert "tasks in this chat that were not created by you" not in result


@pytest.mark.asyncio
async def test_future_task_delete_allows_session_admin_in_group():
    """A session administrator may delete another member's group task."""
    tool = FutureTaskTool()
    existing_job = _job("job-1", sender_id="admin-user")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        delete_job=AsyncMock(),
    )
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="admin-user-2", authorization=authorization),
        action="delete",
        job_id="job-1",
    )

    assert result == "Deleted cron job job-1."
    authorization.authorize.assert_awaited_once()
    assert authorization.authorize.await_args.args[1] == "session.manage"
    cron_mgr.delete_job.assert_awaited_once_with("job-1")


@pytest.mark.asyncio
async def test_future_task_delete_rejects_group_member_without_manage():
    """A regular group member still cannot delete somebody else's task."""
    tool = FutureTaskTool()
    existing_job = _job("job-1", sender_id="admin-user")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        delete_job=AsyncMock(),
    )
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=False))
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="user-1", authorization=authorization),
        action="delete",
        job_id="job-1",
    )

    assert "or an AstrBot admin can delete it" in result
    cron_mgr.delete_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_delete_requires_session_manage_for_dashboard_jobs():
    """Group administrators can delete group tasks without a chat creator."""
    tool = FutureTaskTool()
    existing_job = _job("job-1")
    existing_job.payload.pop("sender_id")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        delete_job=AsyncMock(),
    )
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="user-1", authorization=authorization),
        action="delete",
        job_id="job-1",
    )

    assert result == "Deleted cron job job-1."
    cron_mgr.delete_job.assert_awaited_once_with("job-1")


@pytest.mark.asyncio
async def test_future_task_delete_explains_dashboard_jobs_without_sender():
    tool = FutureTaskTool()
    existing_job = _job("job-1")
    existing_job.payload.pop("sender_id")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        delete_job=AsyncMock(),
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="user-1"),
        action="delete",
        job_id="job-1",
    )

    assert "has no chat member as its creator" in result
    cron_mgr.delete_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_list_localizes_naive_utc_next_run_time():
    """Naive SQLite timestamps are UTC before display conversion."""
    tool = FutureTaskTool()
    job = _job("job-1")
    job.next_run_time = datetime(2026, 1, 1, 0, 0)
    cron_mgr = SimpleNamespace(list_jobs=AsyncMock(return_value=[job]))

    result = await tool.call(_context(cron_mgr, tz_name="Asia/Shanghai"), action="list")

    assert "2026-01-01 08:00:00+08:00" in result


@pytest.mark.asyncio
async def test_future_task_list_localizes_to_new_york():
    """The configured IANA timezone is honored for list output."""
    tool = FutureTaskTool()
    job = _job("job-1")
    job.next_run_time = datetime(2026, 1, 1, 0, 0)
    cron_mgr = SimpleNamespace(list_jobs=AsyncMock(return_value=[job]))

    result = await tool.call(
        _context(cron_mgr, tz_name="America/New_York"), action="list"
    )

    assert "2025-12-31 19:00:00-05:00" in result


@pytest.mark.asyncio
async def test_future_task_list_invalid_timezone_is_ignored():
    """An invalid display timezone must not crash or be persisted."""
    tool = FutureTaskTool()
    job = _job("job-1")
    job.next_run_time = datetime(2026, 1, 1, 0, 0)
    cron_mgr = SimpleNamespace(list_jobs=AsyncMock(return_value=[job]))

    result = await tool.call(_context(cron_mgr, tz_name="Not/AZone"), action="list")

    assert "job-1" in result


@pytest.mark.asyncio
async def test_future_task_create_uses_live_scheduler_next_run():
    """Create output should use the scheduler before the DB write catches up."""
    tool = FutureTaskTool()
    created_job = SimpleNamespace(
        job_id="job-1", name="active_agent_task", next_run_time=None
    )
    cron_mgr = SimpleNamespace(
        add_active_job=AsyncMock(return_value=created_job),
        get_next_run_time=MagicMock(return_value=datetime(2026, 1, 1, 0, 0)),
    )

    result = await tool.call(
        _context(
            cron_mgr, tz_name="Asia/Shanghai", authorization=_allowing_authorization()
        ),
        action="create",
        cron_expression="0 8 * * *",
        note="daily reminder",
    )

    _, call_kwargs = cron_mgr.add_active_job.call_args
    assert call_kwargs["timezone"] == "Asia/Shanghai"
    cron_mgr.get_next_run_time.assert_called_once_with("job-1")
    assert "2026-01-01 08:00:00+08:00" in result


@pytest.mark.asyncio
async def test_future_task_create_denied_without_authorization_context():
    """Create fails closed when the authorization context is unavailable."""
    tool = FutureTaskTool()
    cron_mgr = SimpleNamespace(add_active_job=AsyncMock())

    result = await tool.call(
        _context(cron_mgr),
        action="create",
        cron_expression="0 8 * * *",
        note="daily reminder",
    )

    assert result.startswith("error: Permission denied.")
    cron_mgr.add_active_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_create_falls_back_to_run_at():
    """One-shot creation displays the supplied time if the scheduler is empty."""
    tool = FutureTaskTool()
    created_job = SimpleNamespace(
        job_id="job-1", name="active_agent_task", next_run_time=None
    )
    cron_mgr = SimpleNamespace(
        add_active_job=AsyncMock(return_value=created_job),
        get_next_run_time=MagicMock(return_value=None),
    )

    result = await tool.call(
        _context(
            cron_mgr, tz_name="Asia/Shanghai", authorization=_allowing_authorization()
        ),
        action="create",
        run_once=True,
        run_at="2026-02-02T08:00:00+08:00",
        note="one-time reminder",
    )

    assert "2026-02-02 08:00:00+08:00" in result


@pytest.mark.asyncio
async def test_group_member_lists_group_tasks_through_executor(authorization):
    """A plain group member reaches list through the real execution boundary."""
    tool = _registered_future_task_tool()
    assert tool.required_actions == ("tool.schedule_read",)
    resource = _session_resource()
    subject = _im_subject("member-1")
    cron_mgr = SimpleNamespace(
        list_jobs=AsyncMock(
            return_value=[
                _job("admin-job", umo=_UMO, sender_id="owner-1"),
                _job("member-job", umo=_UMO, sender_id="member-1"),
            ]
        )
    )

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "member-1"), authorization, cron_mgr
        ),
        action="list",
    )

    assert "admin-job" in text
    assert "creator=owner-1" in text
    assert "member-job" in text
    assert "Permission denied" not in text


@pytest.mark.asyncio
async def test_group_member_cannot_delete_another_members_task_through_executor(
    authorization,
):
    """tool.schedule_read admits the call, but the per-task check still denies."""
    tool = _registered_future_task_tool()
    resource = _session_resource()
    subject = _im_subject("member-1")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(
            get_cron_job=AsyncMock(
                return_value=_job("job-1", umo=_UMO, sender_id="owner-1")
            )
        ),
        delete_job=AsyncMock(),
    )

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "member-1"), authorization, cron_mgr
        ),
        action="delete",
        job_id="job-1",
    )

    assert "or an AstrBot admin can delete it" in text
    cron_mgr.delete_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_admin_deletes_another_members_task_through_executor(
    authorization,
):
    """A session administrator reaches the new cross-owner deletion branch."""
    tool = _registered_future_task_tool()
    resource = _session_resource()
    subject = _im_subject("admin-1")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_ADMIN,
        scope_type="session",
        scope_id=resource.id,
        config_id="default",
        enforce_actor=False,
    )
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(
            get_cron_job=AsyncMock(
                return_value=_job("job-1", umo=_UMO, sender_id="owner-1")
            )
        ),
        delete_job=AsyncMock(),
    )

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "admin-1"), authorization, cron_mgr
        ),
        action="delete",
        job_id="job-1",
    )

    assert text == "Deleted cron job job-1."
    cron_mgr.delete_job.assert_awaited_once_with("job-1")


@pytest.mark.asyncio
async def test_group_member_cannot_create_tasks_through_executor(authorization):
    """Creating still requires tool.schedule_write at the execution boundary."""
    tool = _registered_future_task_tool()
    resource = _session_resource()
    subject = _im_subject("member-1")
    cron_mgr = SimpleNamespace(add_active_job=AsyncMock())

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "member-1"), authorization, cron_mgr
        ),
        action="create",
        cron_expression="0 8 * * *",
        note="daily reminder",
    )

    assert text.startswith("error: Permission denied.")
    cron_mgr.add_active_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_owner_creates_task_through_executor(authorization):
    """A session owner keeps the ability to create scheduled tasks."""
    tool = _registered_future_task_tool()
    resource = _session_resource()
    subject = _im_subject("owner-1")
    await authorization.grant_binding(
        actor=Subject.system("test"),
        subject_id=subject.id,
        role=Role.SESSION_OWNER,
        scope_type="session",
        scope_id=resource.id,
        config_id="default",
        enforce_actor=False,
    )
    created_job = SimpleNamespace(
        job_id="job-9",
        name="daily",
        next_run_time=None,
        run_once=False,
    )
    cron_mgr = SimpleNamespace(add_active_job=AsyncMock(return_value=created_job))

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "owner-1"), authorization, cron_mgr
        ),
        action="create",
        cron_expression="0 8 * * *",
        note="daily reminder",
    )

    assert "Scheduled future task job-9" in text
    cron_mgr.add_active_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_member_edits_own_task_through_executor(authorization):
    """A member may edit a task they created without tool-level write access."""
    tool = _registered_future_task_tool()
    resource = _session_resource()
    subject = _im_subject("member-1")
    updated_job = SimpleNamespace(job_id="job-1", name="name-job-1")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(
            get_cron_job=AsyncMock(
                return_value=_job("job-1", umo=_UMO, sender_id="member-1")
            )
        ),
        update_job=AsyncMock(return_value=updated_job),
    )

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "member-1"), authorization, cron_mgr
        ),
        action="edit",
        job_id="job-1",
        note="new note",
    )

    assert text == "Updated future task job-1 (name-job-1)."
    cron_mgr.update_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_member_cannot_edit_another_members_task_through_executor(
    authorization,
):
    """The per-task creator check still denies editing somebody else's task."""
    tool = _registered_future_task_tool()
    resource = _session_resource()
    subject = _im_subject("member-1")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(
            get_cron_job=AsyncMock(
                return_value=_job("job-1", umo=_UMO, sender_id="owner-1")
            )
        ),
        update_job=AsyncMock(),
    )

    text = await _execute_through_executor(
        tool,
        _executor_context(
            _executor_event(subject, resource, "member-1"), authorization, cron_mgr
        ),
        action="edit",
        job_id="job-1",
        note="attacker note",
    )

    assert "created by another member of this group chat" in text
    cron_mgr.update_job.assert_not_awaited()
