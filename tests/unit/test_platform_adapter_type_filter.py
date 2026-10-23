from astrbot.core.star.filter.platform_adapter_type import (
    ADAPTER_NAME_2_TYPE,
    PlatformAdapterType,
)


def test_napcat_adapter_matches_aiocqhttp_filter():
    assert ADAPTER_NAME_2_TYPE["napcat"] is PlatformAdapterType.AIOCQHTTP
