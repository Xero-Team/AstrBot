import asyncio
from collections.abc import Awaitable, Coroutine
from typing import Any, cast

from astrbot import logger


def create_tracked_task(
    task_set: set[asyncio.Task],
    coro: Awaitable,
    *,
    name: str | None = None,
) -> asyncio.Task:
    """Create a task with a strong reference until completion."""
    if asyncio.iscoroutine(coro):
        task = asyncio.create_task(
            cast(Coroutine[Any, Any, Any], coro),
            name=name,
        )
    else:

        async def _await_coro() -> Any:
            return await coro

        task = asyncio.create_task(_await_coro(), name=name)
    task_set.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        task_set.discard(done_task)
        if done_task.cancelled():
            return
        try:
            exc = done_task.exception()
        except Exception as err:
            logger.error("Failed to inspect task %s exception: %s", done_task, err)
            return
        if exc is not None:
            logger.error(
                "Background task %s failed",
                done_task.get_name(),
                exc_info=exc,
            )

    task.add_done_callback(_on_done)
    return task


async def cancel_tracked_tasks(task_set: set[asyncio.Task]) -> None:
    """Cancel and await all tracked tasks."""
    tasks = list(task_set)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    task_set.clear()
