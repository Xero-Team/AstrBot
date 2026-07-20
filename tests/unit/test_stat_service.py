import time
from datetime import datetime
from types import SimpleNamespace

import pytest

from astrbot.core.db.po import PlatformStat
from astrbot.dashboard.services import stat_service
from astrbot.dashboard.services.stat_service import StatService


@pytest.mark.asyncio
async def test_sqlite_get_platform_stats_returns_platform_stat_rows(temp_db):
    await temp_db.insert_platform_stats(
        "qq-main",
        "onebot",
        count=2,
        timestamp=datetime(2026, 6, 30, 1, 0, 0),
    )

    rows = await temp_db.get_platform_stats(offset_sec=10 * 365 * 24 * 3600)

    assert len(rows) == 1
    assert isinstance(rows[0], PlatformStat)
    assert rows[0].platform_id == "qq-main"
    assert rows[0].platform_type == "onebot"
    assert rows[0].count == 2


@pytest.mark.asyncio
async def test_stat_service_get_stat_accepts_unix_second_timestamps(
    astrbot_config,
    monkeypatch: pytest.MonkeyPatch,
):
    timestamp = int(time.time()) - 120
    db_helper = SimpleNamespace(
        get_platform_stats=lambda _offset_sec: None,
    )

    async def _get_platform_stats(_offset_sec: int):
        return [
            SimpleNamespace(
                platform_id="qq-main",
                platform_type="onebot",
                count=4,
                timestamp=timestamp,
            )
        ]

    db_helper.get_platform_stats = _get_platform_stats
    core_lifecycle = SimpleNamespace(
        start_time=timestamp - 3600,
        services=SimpleNamespace(demo_mode=False),
        star_context=SimpleNamespace(get_all_stars=lambda: []),
        platform_manager=SimpleNamespace(get_platform_count=lambda: 1),
    )

    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.cpu_percent",
        lambda interval=0.5: 12.5,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.Process",
        lambda: SimpleNamespace(
            memory_info=lambda: SimpleNamespace(rss=256 << 20),
        ),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.stat_service.psutil.virtual_memory",
        lambda: SimpleNamespace(total=1024 << 20),
    )

    service = StatService(db_helper, core_lifecycle, astrbot_config)

    data = await service.get_stat(offset_sec=3600)

    assert data["message_count"] == 4
    assert data["platform"] == [
        {
            "name": "qq-main",
            "count": 4,
            "timestamp": timestamp,
        }
    ]


def test_stat_service_get_first_notice_uses_only_supported_locales(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "FIRST_NOTICE.md").write_text("Chinese notice", encoding="utf-8")
    (tmp_path / "FIRST_NOTICE.en-US.md").write_text("English notice", encoding="utf-8")
    monkeypatch.setattr(stat_service, "get_astrbot_path", lambda: str(tmp_path))

    service = object.__new__(StatService)

    assert service.get_first_notice("zh-CN") == {"content": "Chinese notice"}
    assert service.get_first_notice("en-US") == {"content": "English notice"}
    assert service.get_first_notice(None) == {"content": "Chinese notice"}
