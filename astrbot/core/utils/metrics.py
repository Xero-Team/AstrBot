"""Runtime-owned local statistics recording.

AstrBot does not upload telemetry. Platform counters are written to the local
statistics store only, so the Dashboard can render message trends without any
network or installation-identity state.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from astrbot import logger
from astrbot.core.db.protocols import StatisticsStore


class MetricsSink(Protocol):
    """Minimal local-statistics capability needed by runtime collaborators."""

    async def record_platform_event(
        self,
        *,
        platform_id: str,
        platform_type: str = "unknown",
    ) -> None:
        """Record one local platform event."""


class MetricsRuntime:
    """Record local platform statistics for one AstrBot runtime instance."""

    def __init__(self, db: StatisticsStore | None) -> None:
        self._db = db

    async def record_platform_event(
        self,
        *,
        platform_id: str,
        platform_type: str = "unknown",
    ) -> None:
        """Persist one platform event in the local statistics store.

        Args:
            platform_id: Configured adapter name that handled the event.
            platform_type: Adapter type; ``"unknown"`` when the caller does not
                know a more specific type.
        """
        if self._db is None:
            return
        try:
            await self._db.insert_platform_stats(
                platform_id=platform_id,
                platform_type=platform_type,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("保存平台统计到数据库失败: %s", exc)
