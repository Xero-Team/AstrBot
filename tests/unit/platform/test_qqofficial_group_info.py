from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.platform import Group
from astrbot.core.platform.sources.qqofficial.qqofficial_group_info import (
    get_qq_group,
)


@pytest.mark.asyncio
async def test_qqofficial_group_lookup_redacts_sensitive_exception(caplog):
    """Network errors must not leak URLs or tokens into logs."""
    bot = SimpleNamespace(
        api=SimpleNamespace(
            _http=SimpleNamespace(
                request=AsyncMock(
                    side_effect=RuntimeError(
                        "request failed https://api.sgroup.qq.com/?token=secret"
                    )
                )
            )
        )
    )

    with caplog.at_level("WARNING"):
        group = await get_qq_group(bot, Group(group_id="group-redact"))

    assert group.group_id == "group-redact"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "api.sgroup.qq.com" not in logged
    assert "token=secret" not in logged
