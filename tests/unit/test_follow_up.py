import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.agent.follow_up import FollowUpCapture, FollowUpCoordinator
from astrbot.core.agent.runners.tool_loop_agent_runner import FollowUpTicket


class FakeEvent:
    def __init__(
        self,
        *,
        unified_msg_origin: str = "umo-1",
        sender_id: str | None = "user-1",
        message_str: str = "",
        outline: str = "",
        extras: dict | None = None,
    ) -> None:
        self.unified_msg_origin = unified_msg_origin
        self._sender_id = sender_id
        self._message_str = message_str
        self._outline = outline
        self._extras = extras or {}

    def get_sender_id(self) -> str | None:
        return self._sender_id

    def get_message_str(self) -> str:
        return self._message_str

    def get_message_outline(self) -> str:
        return self._outline

    def get_extra(self, key: str):
        return self._extras.get(key)


@pytest.fixture
def coordinator() -> FollowUpCoordinator:
    return FollowUpCoordinator()


@pytest.mark.asyncio
async def test_try_capture_follow_up_requires_matching_sender_and_non_stopping_runner(
    coordinator: FollowUpCoordinator,
):
    runner_event = FakeEvent(sender_id="owner", extras={"agent_stop_requested": True})
    runner = SimpleNamespace(
        run_context=SimpleNamespace(context=SimpleNamespace(event=runner_event)),
        follow_up=lambda message_text: FollowUpTicket(seq=1, text=message_text),
    )
    coordinator.register_active_runner("umo-1", runner)

    assert coordinator.try_capture(FakeEvent(sender_id=None)) is None
    assert coordinator.try_capture(FakeEvent(sender_id="other")) is None
    assert coordinator.try_capture(FakeEvent(sender_id="owner")) is None


@pytest.mark.asyncio
async def test_try_capture_follow_up_uses_outline_when_message_text_is_blank(
    coordinator: FollowUpCoordinator,
):
    captured_texts: list[str] = []
    runner_event = FakeEvent(sender_id="owner")

    def _follow_up(*, message_text: str):
        captured_texts.append(message_text)
        return FollowUpTicket(seq=7, text=message_text)

    runner = SimpleNamespace(
        run_context=SimpleNamespace(context=SimpleNamespace(event=runner_event)),
        follow_up=_follow_up,
    )
    coordinator.register_active_runner("umo-1", runner)
    event = FakeEvent(
        sender_id="owner",
        message_str="   ",
        outline="  fallback outline  ",
    )

    capture = coordinator.try_capture(event)

    assert capture is not None
    assert capture.order_seq == 0
    assert captured_texts == ["fallback outline"]
    capture.ticket.resolved.set()
    await coordinator.finalize_capture(
        capture,
        activated=False,
        consumed_marked=False,
    )


@pytest.mark.asyncio
async def test_prepare_follow_up_capture_marks_consumed_ticket_without_activation(
    coordinator: FollowUpCoordinator,
):
    ticket = FollowUpTicket(seq=1, text="consumed")
    ticket.consumed = True
    ticket.resolved.set()
    seq = coordinator._allocate_order("umo-1")
    capture = FollowUpCapture(
        umo="umo-1",
        ticket=ticket,
        order_seq=seq,
        monitor_task=asyncio.create_task(asyncio.sleep(30)),
    )

    consumed_marked, activated = await coordinator.prepare_capture(capture)

    assert (consumed_marked, activated) == (True, False)
    assert "umo-1" not in coordinator._order_states
    await coordinator.finalize_capture(
        capture,
        activated=activated,
        consumed_marked=consumed_marked,
    )
    assert capture.monitor_task.cancelled()


@pytest.mark.asyncio
async def test_follow_up_activation_waits_for_previous_turn_to_finish(
    coordinator: FollowUpCoordinator,
):
    first_ticket = FollowUpTicket(seq=1, text="first")
    second_ticket = FollowUpTicket(seq=2, text="second")
    first_ticket.resolved.set()
    second_ticket.resolved.set()

    first_capture = FollowUpCapture(
        umo="umo-1",
        ticket=first_ticket,
        order_seq=coordinator._allocate_order("umo-1"),
        monitor_task=asyncio.create_task(asyncio.sleep(30)),
    )
    second_capture = FollowUpCapture(
        umo="umo-1",
        ticket=second_ticket,
        order_seq=coordinator._allocate_order("umo-1"),
        monitor_task=asyncio.create_task(asyncio.sleep(30)),
    )

    first_result = await coordinator.prepare_capture(first_capture)
    second_task = asyncio.create_task(coordinator.prepare_capture(second_capture))
    await asyncio.sleep(0)

    assert first_result == (False, True)
    assert not second_task.done()

    await coordinator.finalize_capture(
        first_capture,
        activated=True,
        consumed_marked=False,
    )
    second_result = await second_task

    assert second_result == (False, True)
    state = coordinator._order_states["umo-1"]
    assert state["next_turn"] == 1

    await coordinator.finalize_capture(
        second_capture,
        activated=True,
        consumed_marked=False,
    )
    assert "umo-1" not in coordinator._order_states


def test_follow_up_coordinators_do_not_share_active_runner_state() -> None:
    first = FollowUpCoordinator()
    second = FollowUpCoordinator()
    runner = object()

    first.register_active_runner("umo-1", runner)

    assert first._active_runners["umo-1"] is runner
    assert second._active_runners == {}


@pytest.mark.asyncio
async def test_terminate_wakes_a_pending_ticket(coordinator: FollowUpCoordinator):
    ticket = FollowUpTicket(seq=1, text="pending")
    capture = FollowUpCapture(
        umo="umo-1",
        ticket=ticket,
        order_seq=coordinator._allocate_order("umo-1"),
        monitor_task=asyncio.create_task(asyncio.sleep(30)),
    )
    coordinator._pending_tickets.append(ticket)
    waiter = asyncio.create_task(coordinator.prepare_capture(capture))
    await asyncio.sleep(0)
    await coordinator.terminate()
    capture.monitor_task.cancel()
    await asyncio.gather(capture.monitor_task, return_exceptions=True)

    assert await waiter == (True, False)
