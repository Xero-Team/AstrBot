"""Bounded runtime statistics for local text-to-image rendering."""

from dataclasses import dataclass
from typing import Literal

RenderResult = Literal["success", "failed", "cancelled"]


@dataclass(slots=True)
class T2iRuntimeStats:
    """Collect non-sensitive, process-local renderer statistics.

    The counters deliberately do not retain template names, rendered content,
    file paths, URLs, or exception messages.
    """

    render_in_progress: int = 0
    active_pages: int = 0
    peak_active_pages: int = 0
    successful_renders: int = 0
    failed_renders: int = 0
    cancelled_renders: int = 0
    total_render_duration_ms: float = 0.0
    last_render_duration_ms: float = 0.0
    max_render_duration_ms: float = 0.0
    output_bytes: int = 0
    browser_starts: int = 0
    browser_restarts: int = 0
    browser_connected: bool = False
    context_count: int = 0

    def record_render_started(self) -> None:
        """Record that a render has started."""
        self.render_in_progress += 1

    def record_render_finished(
        self,
        result: RenderResult,
        duration_ms: float,
        output_bytes: int = 0,
    ) -> None:
        """Record the terminal state of one render."""
        self.render_in_progress = max(0, self.render_in_progress - 1)
        self.last_render_duration_ms = duration_ms
        self.total_render_duration_ms += duration_ms
        self.max_render_duration_ms = max(self.max_render_duration_ms, duration_ms)
        self.output_bytes += output_bytes

        if result == "success":
            self.successful_renders += 1
        elif result == "cancelled":
            self.cancelled_renders += 1
        else:
            self.failed_renders += 1

    def record_page_opened(self) -> None:
        """Record a page acquired for rendering."""
        self.active_pages += 1
        self.peak_active_pages = max(self.peak_active_pages, self.active_pages)

    def record_page_closed(self) -> None:
        """Record a render page being released."""
        self.active_pages = max(0, self.active_pages - 1)

    def record_browser_started(self, *, restarted: bool) -> None:
        """Record a Chromium browser launch."""
        self.browser_starts += 1
        if restarted:
            self.browser_restarts += 1
        self.browser_connected = True

    def set_browser_connected(self, connected: bool) -> None:
        """Update the cached browser connection state."""
        self.browser_connected = connected

    def set_context_count(self, count: int) -> None:
        """Update the number of reusable browser contexts."""
        self.context_count = max(0, count)

    def snapshot(self) -> dict[str, int | float | bool]:
        """Return the current bounded statistics snapshot."""
        completed_renders = (
            self.successful_renders + self.failed_renders + self.cancelled_renders
        )
        average_duration_ms = (
            self.total_render_duration_ms / completed_renders
            if completed_renders
            else 0.0
        )
        return {
            "render_in_progress": self.render_in_progress,
            "active_pages": self.active_pages,
            "peak_active_pages": self.peak_active_pages,
            "successful_renders": self.successful_renders,
            "failed_renders": self.failed_renders,
            "cancelled_renders": self.cancelled_renders,
            "total_render_duration_ms": self.total_render_duration_ms,
            "last_render_duration_ms": self.last_render_duration_ms,
            "average_render_duration_ms": average_duration_ms,
            "max_render_duration_ms": self.max_render_duration_ms,
            "output_bytes": self.output_bytes,
            "browser_starts": self.browser_starts,
            "browser_restarts": self.browser_restarts,
            "browser_connected": self.browser_connected,
            "context_count": self.context_count,
        }
