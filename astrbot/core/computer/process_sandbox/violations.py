"""Bounded, redacted sandbox violation records."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from astrbot.core.utils.error_redaction import redact_sensitive_text

MAX_VIOLATION_TEXT = 256
MAX_LEASE_VIOLATIONS = 128
MAX_SNAPSHOT_VIOLATIONS = 32

ViolationKind = Literal["network", "filesystem", "socket", "proxy", "lifecycle"]


@dataclass(frozen=True, slots=True)
class SandboxViolation:
    """One bounded denial that can be returned to a tool caller.

    Args:
        kind: Policy area that denied the operation.
        reason: Short, redacted description.
        target: Redacted destination metadata, never a token or host path.
    """

    kind: ViolationKind
    reason: str
    target: str = ""


def redact_violation_target(target: str) -> str:
    """Return destination metadata without credentials, queries, or host paths."""
    value = str(target or "").strip()
    if not value:
        return ""
    if "://" in value:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return "<url>"
        if parsed.scheme and parsed.hostname:
            host = parsed.hostname
            try:
                port = f":{parsed.port}" if parsed.port else ""
            except ValueError:
                port = ""
            return redact_sensitive_text(f"{parsed.scheme}://{host}{port}")[
                :MAX_VIOLATION_TEXT
            ]
        return "<url>"
    if "/" in value or "\\" in value:
        return "<local-path>"
    return redact_sensitive_text(value)[:MAX_VIOLATION_TEXT]


class ViolationStore:
    """Per-lease, bounded, concurrency-safe denial store.

    The store keeps the most recent entries with a fixed ceiling and never
    evicts a lease. Snapshots do not clear history; callers explicitly drain
    when they need to acknowledge records. Revocation preserves the final
    snapshot for the completed invocation.
    """

    def __init__(
        self,
        *,
        max_entries: int = MAX_LEASE_VIOLATIONS,
        snapshot_limit: int = MAX_SNAPSHOT_VIOLATIONS,
    ) -> None:
        """Create a store with explicit bounds.

        Args:
            max_entries: Maximum retained records for one lease.
            snapshot_limit: Maximum records returned by a snapshot or drain.
        """
        if max_entries <= 0 or snapshot_limit <= 0:
            raise ValueError("Violation limits must be positive.")
        self._entries: deque[SandboxViolation] = deque(maxlen=max_entries)
        self._snapshot_limit = min(snapshot_limit, max_entries)
        self._lock = threading.Lock()
        self._dropped = 0

    def record(
        self,
        kind: ViolationKind,
        reason: str,
        target: str = "",
    ) -> SandboxViolation:
        """Record one denial without raising on malformed input."""
        violation = SandboxViolation(
            kind=kind,
            reason=redact_sensitive_text(str(reason or ""))[:MAX_VIOLATION_TEXT],
            target=redact_violation_target(target),
        )
        with self._lock:
            if len(self._entries) == self._entries.maxlen:
                self._dropped += 1
            self._entries.append(violation)
        return violation

    def snapshot(self) -> tuple[SandboxViolation, ...]:
        """Return the newest bounded records without clearing them."""
        with self._lock:
            entries = list(self._entries)
        return tuple(entries[-self._snapshot_limit :])

    def drain(self) -> tuple[SandboxViolation, ...]:
        """Return and clear every retained record."""
        with self._lock:
            entries = list(self._entries)
            self._entries.clear()
            self._dropped = 0
        return tuple(entries[-self._snapshot_limit :])

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def dropped(self) -> int:
        """Return how many records were discarded by the bounded ring."""
        with self._lock:
            return self._dropped

    def as_result(self) -> list[dict[str, object]]:
        """Return snapshot dictionaries with the current UTC timestamp."""
        now = int(time.time())
        return [
            {
                "kind": violation.kind,
                "reason": violation.reason,
                "target": violation.target,
                "at": now,
            }
            for violation in self.snapshot()
        ]


__all__ = (
    "MAX_LEASE_VIOLATIONS",
    "MAX_SNAPSHOT_VIOLATIONS",
    "MAX_VIOLATION_TEXT",
    "SandboxViolation",
    "ViolationStore",
    "redact_violation_target",
)
