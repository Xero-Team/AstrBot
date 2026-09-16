"""Tests for the completion report a finished work task ends with."""

import pytest

from astrbot.core.agent.btw import runtime_registry
from astrbot.core.agent.btw.conversation_report import (
    compose_work_report,
    report_text,
)
from astrbot.core.agent.btw.types import (
    WORK_FAILED_EXTRA,
    WORK_REPORT_EXTRA,
    WorkSession,
    WorkSessionStatus,
    resolve_run_status,
)
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.agent.conversation_loop import ConversationLoop
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)


class FakeEvent:
    def __init__(self, message: str = "task", result=None) -> None:
        self.unified_msg_origin = "umo-1"
        self.message_str = message
        self.extras: dict = {}
        self.result = result
        self._stopped = False

    def set_extra(self, key, value) -> None:
        self.extras[key] = value

    def get_extra(self, key):
        return self.extras.get(key)

    def set_result(self, value) -> None:
        self.result = value

    def get_result(self):
        return self.result

    def is_stopped(self) -> bool:
        return self._stopped


def _result(text: str, kind: ResultContentType = ResultContentType.LLM_RESULT):
    return MessageEventResult(
        chain=MessageChain().message(text).chain, result_content_type=kind
    )


def _plain_text(result: MessageEventResult) -> str:
    return MessageChain(chain=result.chain).get_plain_text()


@pytest.mark.parametrize(
    ("extras", "produced", "expected"),
    [
        ({}, True, WorkSessionStatus.COMPLETED),
        ({}, False, WorkSessionStatus.FAILED),
        ({WORK_FAILED_EXTRA: True}, True, WorkSessionStatus.FAILED),
        ({"_third_party_runner_error": True}, True, WorkSessionStatus.FAILED),
        ({"agent_stop_requested": True}, True, WorkSessionStatus.CANCELLED),
        ({"agent_stop_requested": True}, False, WorkSessionStatus.CANCELLED),
    ],
)
def test_a_run_status_matches_what_the_work_loop_records(extras, produced, expected):
    event = FakeEvent()
    event.extras.update(extras)
    assert resolve_run_status(event, produced=produced) is expected


def test_a_report_names_the_status_and_its_files():
    assert report_text("en-US", WorkSessionStatus.COMPLETED, []) == (
        "✅ Work task completed."
    )
    with_files = report_text("en-US", WorkSessionStatus.FAILED, ["a.txt", "b/c.py"])
    assert with_files.splitlines() == [
        "❌ Work task failed.",
        "Files this task produced:",
        "- a.txt",
        "- b/c.py",
    ]


def test_an_unknown_locale_falls_back_to_the_default_bundle():
    assert report_text("xx-XX", WorkSessionStatus.CANCELLED, []).startswith("🛑")


def test_the_report_is_appended_to_the_final_result():
    session = WorkSession(origin="umo-1", request="task")
    session.artifacts.extend(["a.txt"])
    event = FakeEvent(result=_result("the answer"))
    assert compose_work_report(event, session, "en-US") is True
    text = _plain_text(event.get_result())
    assert text.startswith("the answer")
    assert "Work task completed." in text
    assert "- a.txt" in text


def test_the_report_is_added_only_once():
    event = FakeEvent(result=_result("the answer"))
    assert compose_work_report(event, None, "en-US") is True
    assert event.get_extra(WORK_REPORT_EXTRA) is True
    assert compose_work_report(event, None, "en-US") is False


def test_a_streamed_chunk_is_left_alone():
    event = FakeEvent(result=_result("chunk", ResultContentType.STREAMING_RESULT))
    assert compose_work_report(event, None, "en-US") is False
    assert event.get_extra(WORK_REPORT_EXTRA) is None


def test_a_run_without_a_result_reports_nothing():
    assert compose_work_report(FakeEvent(), None, "en-US") is False


def test_a_streamed_finish_still_carries_the_report():
    event = FakeEvent(result=_result("done", ResultContentType.STREAMING_FINISH))
    assert compose_work_report(event, None, "en-US") is True
    assert "Work task completed." in _plain_text(event.get_result())


@pytest.mark.asyncio
async def test_artifacts_are_recorded_once_per_session():
    manager = WorkSessionManager()
    session = await manager.create("umo-1", "task")
    assert (
        await manager.record_artifacts(session.id, ["a.txt", "a.txt", "b.txt"]) is True
    )
    assert session.artifacts == ["a.txt", "b.txt"]
    assert await manager.record_artifacts(session.id, ["a.txt", "", 7]) is True
    assert session.artifacts == ["a.txt", "b.txt"]
    assert await manager.record_artifacts("missing", ["a.txt"]) is False


@pytest.mark.asyncio
async def test_the_registry_records_artifacts_for_the_event_session():
    manager = WorkSessionManager()
    session = await manager.create("umo-1", "task")
    runtime_registry._managers["cfg"] = manager
    try:
        event = FakeEvent()
        event.extras["btw_work_session_id"] = session.id
        event.resource = type("R", (), {"config_id": "cfg"})()
        assert await runtime_registry.record_work_artifacts(event, ["a.txt"]) is True
        assert session.artifacts == ["a.txt"]
        assert await runtime_registry.record_work_artifacts(event, []) is False
        event.extras.pop("btw_work_session_id")
        assert await runtime_registry.record_work_artifacts(event, ["b.txt"]) is False
    finally:
        runtime_registry._managers.pop("cfg", None)


@pytest.mark.asyncio
async def test_the_registry_reports_an_unknown_profile():
    event = FakeEvent()
    event.extras["btw_work_session_id"] = "session"
    event.resource = type("R", (), {"config_id": "unknown"})()
    assert await runtime_registry.record_work_artifacts(event, ["a.txt"]) is False


@pytest.mark.asyncio
async def test_the_work_loop_reports_through_the_conversation_loop():
    delivered: list[tuple] = []
    reported: list[tuple] = []

    async def dispatcher(event):
        delivered.append(event)

    async def reporter(event, session_id):
        reported.append((event, session_id))

    async def finalizer(event):
        return None

    loop = WorkLoop(executor=None, sessions=WorkSessionManager())
    loop.configure_detached_execution(
        background_tasks=set(),
        result_dispatcher=dispatcher,
        event_finalizer=finalizer,
        result_reporter=reporter,
    )
    event = FakeEvent()
    await loop._deliver(event, "session-1")
    assert reported == [(event, "session-1")]
    assert delivered == []


@pytest.mark.asyncio
async def test_the_work_loop_delivers_itself_without_a_reporter():
    delivered: list[object] = []

    async def dispatcher(event):
        delivered.append(event)

    async def finalizer(event):
        return None

    loop = WorkLoop(executor=None, sessions=WorkSessionManager())
    loop.configure_detached_execution(
        background_tasks=set(),
        result_dispatcher=dispatcher,
        event_finalizer=finalizer,
    )
    event = FakeEvent()
    await loop._deliver(event, "session-1")
    assert delivered == [event]


@pytest.mark.asyncio
async def test_the_conversation_loop_composes_before_delivering():
    loop = ConversationLoop(agent_request=None)
    loop._report_via_conversation = True
    sent: list[object] = []

    async def dispatcher(event):
        sent.append(_plain_text(event.get_result()))

    loop._result_dispatcher = dispatcher
    session = await loop.work_sessions.create("umo-1", "task")
    await loop.work_sessions.record_artifacts(session.id, ["out/file.txt"])
    event = FakeEvent(result=_result("the answer"))
    await loop.report_work_result(event, session.id)
    assert sent and sent[0].startswith("the answer")
    assert "工作任务已完成" in sent[0]
    assert "- out/file.txt" in sent[0]


@pytest.mark.asyncio
async def test_the_conversation_loop_needs_a_dispatcher_to_report():
    loop = ConversationLoop(agent_request=None)
    with pytest.raises(RuntimeError):
        await loop.report_work_result(FakeEvent(), "session-1")


@pytest.mark.asyncio
async def test_an_expired_session_still_reports_its_status():
    loop = ConversationLoop(agent_request=None)
    sent: list[str] = []

    async def dispatcher(event):
        sent.append(_plain_text(event.get_result()))

    loop._result_dispatcher = dispatcher
    await loop.report_work_result(FakeEvent(result=_result("the answer")), "gone")
    assert sent and "工作任务已完成" in sent[0]
