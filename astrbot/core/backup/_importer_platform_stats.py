import os
from datetime import UTC, datetime
from typing import Any

from astrbot import logger

DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT = 5
PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV = (
    "ASTRBOT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT"
)


def load_platform_stats_invalid_count_warn_limit() -> int:
    raw_value = os.getenv(PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV)
    if raw_value is None:
        return DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT

    try:
        value = int(raw_value)
    except TypeError, ValueError:
        value = -1

    if value < 0:
        logger.warning(
            "Invalid env %s=%r, fallback to default %d",
            PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT_ENV,
            raw_value,
            DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT,
        )
        return DEFAULT_PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT

    return value


PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT = load_platform_stats_invalid_count_warn_limit()


class InvalidCountWarnLimiter:
    """Rate-limit warnings for invalid platform_stats count values."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._count = 0
        self._suppression_logged = False

    def warn_invalid_count(self, value: Any, key_for_log: tuple[Any, ...]) -> None:
        """Record a warning for an invalid count value.

        Args:
            value: Raw invalid count value.
            key_for_log: Normalized key used in the warning log message.
        """

        if self.limit <= 0:
            self._warn_suppressed()
            return

        if self._count >= self.limit:
            return

        logger.warning(
            "platform_stats count 非法，已按 0 处理: value=%r, key=%s",
            value,
            key_for_log,
        )
        self._count += 1
        if self._count == self.limit:
            self._warn_suppressed()

    def _warn_suppressed(self) -> None:
        if self._suppression_logged:
            return
        logger.warning(
            "platform_stats 非法 count 告警已达到上限 (%d)，后续将抑制",
            self.limit,
        )
        self._suppression_logged = True


def merge_platform_stats_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge duplicate platform stats rows using normalized UTC timestamps.

    Args:
        rows: Raw platform stats rows from the backup payload.

    Returns:
        Normalized rows with duplicate timestamp/platform keys merged.
    """

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    result: list[dict[str, Any]] = []
    warn_limiter = InvalidCountWarnLimiter(PLATFORM_STATS_INVALID_COUNT_WARN_LIMIT)

    for row in rows:
        normalized_row, merge_key, count = normalize_platform_stats_entry(
            row,
            warn_limiter,
        )
        if merge_key is None:
            result.append(normalized_row)
            continue

        existing = merged.get(merge_key)
        if existing is None:
            merged[merge_key] = normalized_row
            result.append(normalized_row)
            continue

        existing["count"] += count

    return result


def normalize_platform_stats_entry(
    row: dict[str, Any],
    warn_limiter: InvalidCountWarnLimiter,
) -> tuple[dict[str, Any], tuple[str, str, str] | None, int]:
    normalized_row = dict(row)
    normalized_timestamp = normalize_platform_stats_timestamp(
        normalized_row.get("timestamp")
    )
    _apply_normalized_timestamp(normalized_row, normalized_timestamp)

    count = _normalize_platform_stats_count(normalized_row, warn_limiter)
    platform_id = normalized_row.get("platform_id")
    platform_type = normalized_row.get("platform_type")
    if (
        normalized_timestamp is None
        or not isinstance(platform_id, str)
        or not isinstance(platform_type, str)
    ):
        return normalized_row, None, count

    return normalized_row, (normalized_timestamp, platform_id, platform_type), count


def normalize_platform_stats_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return _normalize_datetime(value).isoformat()
    if not isinstance(value, str):
        return None

    timestamp = value.strip()
    if not timestamp:
        return None
    if timestamp.endswith("Z"):
        timestamp = f"{timestamp[:-1]}+00:00"

    try:
        return _normalize_datetime(datetime.fromisoformat(timestamp)).isoformat()
    except ValueError:
        return None


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _apply_normalized_timestamp(
    normalized_row: dict[str, Any],
    normalized_timestamp: str | None,
) -> None:
    if normalized_timestamp is not None:
        normalized_row["timestamp"] = normalized_timestamp
        return

    raw_timestamp = normalized_row.get("timestamp")
    if isinstance(raw_timestamp, str):
        normalized_row["timestamp"] = raw_timestamp.strip()
    elif raw_timestamp is None:
        normalized_row["timestamp"] = ""
    else:
        normalized_row["timestamp"] = str(raw_timestamp)


def _normalize_platform_stats_count(
    normalized_row: dict[str, Any],
    warn_limiter: InvalidCountWarnLimiter,
) -> int:
    raw_count = normalized_row.get("count", 0)
    try:
        count = int(raw_count)
    except TypeError, ValueError:
        warn_limiter.warn_invalid_count(
            raw_count,
            (
                normalized_row.get("timestamp"),
                repr(normalized_row.get("platform_id")),
                repr(normalized_row.get("platform_type")),
            ),
        )
        count = 0

    normalized_row["count"] = count
    return count
