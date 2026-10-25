import sys

import pytest

from astrbot.core.pipeline.content_safety_check.strategies.strategy import (
    StrategySelector,
)


@pytest.mark.asyncio
async def test_missing_configured_strategy_fails_closed(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "astrbot.core.pipeline.content_safety_check.strategies.baidu_aip",
        None,
    )
    selector = StrategySelector(
        {
            "internal_keywords": {"enable": False, "extra_keywords": []},
            "baidu_aip": {
                "enable": True,
                "app_id": "app",
                "api_key": "key",
                "secret_key": "secret",
            },
        }
    )

    ok, info = await selector.check("content")

    assert not ok
    assert "不可用" in info
