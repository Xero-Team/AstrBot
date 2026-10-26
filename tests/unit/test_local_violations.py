"""Bounded, redacted sandbox violation stores."""

from __future__ import annotations

import threading

from astrbot.core.computer.process_sandbox.violations import (
    MAX_LEASE_VIOLATIONS,
    MAX_SNAPSHOT_VIOLATIONS,
    MAX_VIOLATION_TEXT,
    ViolationStore,
    redact_violation_target,
)


def test_violation_store_is_bounded_and_snapshot_does_not_drain() -> None:
    store = ViolationStore()
    for index in range(MAX_LEASE_VIOLATIONS + 20):
        store.record("network", f"denied {index}")
    assert len(store) == MAX_LEASE_VIOLATIONS
    assert store.dropped == 20
    snapshot = store.snapshot()
    assert len(snapshot) == MAX_SNAPSHOT_VIOLATIONS
    assert store.snapshot() == snapshot
    drained = store.drain()
    assert drained == snapshot
    assert len(store) == 0


def test_violation_text_is_redacted_and_bounded() -> None:
    store = ViolationStore()
    violation = store.record(
        "proxy",
        "token=supersecret " + "x" * 500,
        "https://user:password@example.com:8443/private?token=supersecret",
    )
    assert "supersecret" not in violation.reason
    assert "user" not in violation.target
    assert "private" not in violation.target
    assert "supersecret" not in violation.target
    assert len(violation.reason) <= MAX_VIOLATION_TEXT
    assert len(violation.target) <= MAX_VIOLATION_TEXT


def test_redact_violation_target_hides_host_paths() -> None:
    redacted_path = redact_violation_target("/home/operator/.ssh/id_ed25519")
    assert redacted_path == "<local-path>"
    assert "/home/operator" not in redacted_path
    assert ".ssh" not in redacted_path
    assert "id_ed25519" not in redacted_path
    redacted_url = redact_violation_target("https://example.com/a/b?q=1")
    assert redacted_url.startswith("[REDACTED")
    assert "example.com" not in redacted_url
    assert "q=1" not in redacted_url
    assert redact_violation_target("token-abc").startswith("token"[:0])


def test_violation_store_is_thread_safe() -> None:
    store = ViolationStore(max_entries=64, snapshot_limit=32)

    def worker(offset: int) -> None:
        for index in range(50):
            store.record("socket", f"denied-{offset}-{index}")

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(store) == 64
    result = store.as_result()
    assert len(result) <= 32
    assert all(set(item) == {"kind", "reason", "target", "at"} for item in result)
