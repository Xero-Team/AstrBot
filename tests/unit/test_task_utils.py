import asyncio

import pytest

from astrbot.core.utils.task_utils import await_first_terminal_task


@pytest.mark.asyncio
async def test_await_first_terminal_task_empty_returns_none():
    assert await await_first_terminal_task([]) is None


@pytest.mark.asyncio
async def test_await_first_terminal_task_prefers_exception_over_cancel():
    loop = asyncio.get_running_loop()
    fail_future: asyncio.Future[None] = loop.create_future()
    hang_future: asyncio.Future[None] = loop.create_future()

    async def wait_fail() -> None:
        await fail_future

    async def wait_hang() -> None:
        await hang_future

    fail_task = asyncio.create_task(wait_fail(), name="fail")
    hang_task = asyncio.create_task(wait_hang(), name="hang")
    await asyncio.sleep(0)
    fail_future.set_exception(ValueError("boom"))
    hang_task.cancel()
    await asyncio.wait({fail_task, hang_task})
    try:
        with pytest.raises(ValueError, match="boom"):
            await await_first_terminal_task([hang_task, fail_task])
    finally:
        if not hang_task.done():
            hang_task.cancel()
        await asyncio.gather(fail_task, hang_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_await_first_terminal_task_raises_cancelled_without_exception():
    async def hang() -> None:
        await asyncio.Event().wait()

    hanging = asyncio.create_task(hang(), name="hang")
    hanging.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await await_first_terminal_task([hanging])
    finally:
        await asyncio.gather(hanging, return_exceptions=True)


@pytest.mark.asyncio
async def test_await_first_terminal_task_returns_finished_task_without_cancelling_siblings():
    async def finish() -> str:
        return "done"

    async def hang() -> None:
        await asyncio.Event().wait()

    finished = asyncio.create_task(finish(), name="finished")
    hanging = asyncio.create_task(hang(), name="hang")
    try:
        result = await await_first_terminal_task([finished, hanging])
        assert result is finished
        assert not hanging.done()
        assert not hanging.cancelled()
    finally:
        hanging.cancel()
        await asyncio.gather(finished, hanging, return_exceptions=True)
