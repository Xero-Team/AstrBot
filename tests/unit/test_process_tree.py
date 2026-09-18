from astrbot.core.utils import process_tree as pt


def test_bind_is_a_noop_without_a_windows_job(monkeypatch) -> None:
    monkeypatch.setattr(pt, "_KERNEL32", None)
    started: list[object] = []

    class FakeThread:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            started.append(self)

    monkeypatch.setattr(pt.threading, "Thread", FakeThread)
    pt.ProcessTree.create()._bind(1)
    pt.ProcessTree()._bind(1)
    assert started == []


def test_bind_blocking_is_a_noop_without_kernel32(monkeypatch) -> None:
    monkeypatch.setattr(pt, "_KERNEL32", None)
    pt.ProcessTree()._bind_blocking(1)
