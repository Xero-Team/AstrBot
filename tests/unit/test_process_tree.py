import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.utils import process_tree as pt


def test_bind_blocking_is_a_noop_without_a_windows_job(monkeypatch) -> None:
    monkeypatch.setattr(pt, "_KERNEL32", None)
    assert pt.ProcessTree.create()._bind_blocking(1) is True
    assert pt.ProcessTree()._bind_blocking(1) is True


@pytest.mark.asyncio
async def test_assigner_waits_for_a_pid_across_a_slow_arm_to_spawn_gap(
    monkeypatch,
) -> None:
    monkeypatch.setattr(pt, "_ASSIGNER_CLOSE_TIMEOUT", 0.05)
    assigner = pt.ThreadAssigner(SimpleNamespace(_job=1))
    assigned: list[tuple[int, int]] = []
    monkeypatch.setattr(
        pt.ThreadAssigner,
        "_assign",
        lambda _self, job, pid, **_kwargs: assigned.append((job, pid)) or True,
    )
    assigner.start()
    try:
        assert await assigner.ready() is True
        await asyncio.sleep(0.15)

        assert await assigner.assign(4242) is True
        assert assigned == [(1, 4242)]
    finally:
        await assigner.close()


@pytest.mark.asyncio
async def test_assigner_resumes_the_child_when_no_listener_is_available(
    monkeypatch,
) -> None:
    resumed: list[int] = []
    monkeypatch.setattr(pt, "_resume", lambda pid: resumed.append(pid))
    assigner = pt.ThreadAssigner(SimpleNamespace(_job=1))
    assigner.start()
    assert await assigner.ready() is True
    await assigner.close()

    assert await assigner.assign(77) is False
    assert resumed == [77]


@pytest.mark.asyncio
async def test_arm_closes_the_assigner_when_cancelled(monkeypatch) -> None:
    monkeypatch.setattr(pt, "_KERNEL32", object())
    started = asyncio.Event()
    closed = asyncio.Event()

    class FakeAssigner:
        def __init__(self, _tree) -> None:
            pass

        def start(self) -> None:
            started.set()

        async def ready(self) -> bool:
            await asyncio.Event().wait()
            return True

        async def close(self) -> None:
            closed.set()

    monkeypatch.setattr(pt, "ThreadAssigner", FakeAssigner)
    tree = pt.ProcessTree(1)
    task = asyncio.create_task(tree.arm())
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert closed.is_set()
    assert tree._assigner is None


@pytest.mark.asyncio
async def test_spawn_fails_closed_when_binding_is_required(monkeypatch) -> None:
    killed: list[bool] = []
    waited: list[bool] = []

    class FakeProcess:
        pid = 123

        def kill(self) -> None:
            killed.append(True)

        async def wait(self) -> int:
            waited.append(True)
            return 0

    async def fake_exec(*_argv, **_kwargs):
        return FakeProcess()

    async def fake_assign(_pid: int, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(pt.asyncio, "create_subprocess_exec", fake_exec)
    tree = pt.ProcessTree()
    tree._assigner = SimpleNamespace(assign=fake_assign)

    with pytest.raises(pt.ProcessTreeBindingError):
        await tree.spawn("cmd", require_binding=True)

    assert killed == [True]
    assert waited == [True]


@pytest.mark.asyncio
async def test_spawn_keeps_best_effort_binding_by_default(monkeypatch) -> None:
    class FakeProcess:
        pid = 123

    async def fake_exec(*_argv, **_kwargs):
        return FakeProcess()

    async def fake_assign(_pid: int, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(pt.asyncio, "create_subprocess_exec", fake_exec)
    tree = pt.ProcessTree()
    tree._assigner = SimpleNamespace(assign=fake_assign)

    process = await tree.spawn("cmd")

    assert isinstance(process, FakeProcess)


@pytest.mark.asyncio
async def test_spawn_requires_an_armed_job_before_starting(monkeypatch) -> None:
    started: list[bool] = []

    async def fake_exec(*_argv, **_kwargs):
        started.append(True)

    monkeypatch.setattr(pt.asyncio, "create_subprocess_exec", fake_exec)
    tree = pt.ProcessTree(1)

    with pytest.raises(pt.ProcessTreeBindingError):
        await tree.spawn("cmd", require_binding=True)

    assert started == []


@pytest.mark.asyncio
async def test_assigner_keeps_the_child_suspended_for_required_binding(
    monkeypatch,
) -> None:
    resumed: list[int] = []
    monkeypatch.setattr(pt, "_resume", lambda pid: resumed.append(pid))
    assigner = pt.ThreadAssigner(SimpleNamespace(_job=1))
    assigner.start()
    assert await assigner.ready() is True
    await assigner.close()

    assert await assigner.assign(77, resume_on_failure=False) is False
    assert resumed == []
