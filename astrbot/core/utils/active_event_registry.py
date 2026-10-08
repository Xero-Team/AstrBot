import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class ActiveEventControl(Protocol):
    """Narrow control port for active event cancellation."""

    def stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int: ...

    def request_agent_stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int: ...

    def get_background_stop_signal(self, event: AstrMessageEvent) -> asyncio.Event: ...

    def register_background_task(
        self,
        event: AstrMessageEvent,
        task: asyncio.Task,
    ) -> None: ...


class ActiveEventRegistry:
    """维护 unified_msg_origin 到活跃事件的映射。

    用于在 reset 等场景下终止该会话正在处理的事件。
    """

    def __init__(self) -> None:
        self._events: dict[str, set[AstrMessageEvent]] = defaultdict(set)
        self._agent_stop_callbacks: dict[
            AstrMessageEvent, set[Callable[[], object]]
        ] = defaultdict(set)
        self._background_tasks: dict[str, dict[asyncio.Task, AstrMessageEvent]] = (
            defaultdict(dict)
        )
        self._background_cancel_requested: set[asyncio.Task] = set()

    def register(self, event: AstrMessageEvent) -> None:
        self._events[event.unified_msg_origin].add(event)

    def unregister(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        self._events[umo].discard(event)
        if not self._events[umo]:
            del self._events[umo]
        self._agent_stop_callbacks.pop(event, None)

    def register_agent_stop_callback(
        self,
        event: AstrMessageEvent,
        callback: Callable[[], object],
    ) -> None:
        """Register the current runner's stop callback for one active event."""
        self._agent_stop_callbacks[event].add(callback)

    def unregister_agent_stop_callback(
        self,
        event: AstrMessageEvent,
        callback: Callable[[], object],
    ) -> None:
        """Remove a runner stop callback after its lifecycle has ended."""
        callbacks = self._agent_stop_callbacks.get(event)
        if callbacks is None:
            return
        callbacks.discard(callback)
        if not callbacks:
            self._agent_stop_callbacks.pop(event, None)

    def get_background_stop_signal(self, event: AstrMessageEvent) -> asyncio.Event:
        """Return the stop signal shared with an event's background wakeups."""
        signal = event.get_extra("_background_stop_signal")
        if not isinstance(signal, asyncio.Event):
            signal = asyncio.Event()
            event.set_extra("_background_stop_signal", signal)
        if event.get_extra("agent_stop_requested"):
            signal.set()
        return signal

    def register_background_task(
        self,
        event: AstrMessageEvent,
        task: asyncio.Task,
    ) -> None:
        """Retain a background task by session until it finishes."""
        if task.done():
            return
        umo = event.unified_msg_origin
        self._background_tasks[umo][task] = event

        def remove_task(done_task: asyncio.Task) -> None:
            tasks = self._background_tasks.get(umo)
            if tasks is not None:
                tasks.pop(done_task, None)
                if not tasks:
                    del self._background_tasks[umo]
            self._background_cancel_requested.discard(done_task)

        task.add_done_callback(remove_task)
        if self.get_background_stop_signal(event).is_set():
            self._background_cancel_requested.add(task)
            task.cancel()

    def _events_for_umo(self, umo: str) -> set[AstrMessageEvent]:
        events = set(self._events.get(umo, ()))
        events.update(
            event
            for task, event in self._background_tasks.get(umo, {}).items()
            if not task.done()
        )
        return events

    def stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """终止指定 UMO 的所有活跃事件。

        Args:
            umo: 统一消息来源标识符。
            exclude: 需要排除的事件（通常是发起 reset 的事件本身）。

        Returns:
            被终止的事件数量。
        """
        for event in self._events_for_umo(umo):
            if event is not exclude:
                event.stop_event()
        return self.request_agent_stop_all(umo, exclude)

    def request_agent_stop_all(
        self,
        umo: str,
        exclude: AstrMessageEvent | None = None,
    ) -> int:
        """请求停止指定 UMO 的所有活跃事件中的 Agent 运行。

        与 stop_all 不同，这里不会调用 event.stop_event()，
        因此不会中断事件传播，后续流程（如历史记录保存）仍可继续。
        """
        tasks = self._background_tasks.get(umo, {})
        count = 0
        for event in self._events_for_umo(umo):
            if event is not exclude:
                event.set_extra("agent_stop_requested", True)
                self.get_background_stop_signal(event).set()
                for callback in tuple(self._agent_stop_callbacks.get(event, ())):
                    try:
                        callback()
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Failed to stop active Agent for %s: %s",
                            umo,
                            safe_error("", exc),
                        )
                count += 1
        for task, event in tuple(tasks.items()):
            if (
                event is not exclude
                and not task.done()
                and task not in self._background_cancel_requested
            ):
                self._background_cancel_requested.add(task)
                task.cancel()
        return count
