from types import SimpleNamespace

import pytest

from astrbot.core.umop_config_router import UmopConfigRouter


def make_router(routes: dict[str, str] | None = None) -> UmopConfigRouter:
    router = UmopConfigRouter(sp=SimpleNamespace())
    router.umop_to_conf_id = routes or {}
    return router


def test_exact_route_beats_platform_wildcard_route() -> None:
    router = make_router(
        {
            "onebot::*": "platform-default",
            "onebot:group:123": "exact-match",
        }
    )

    result = router.get_conf_id_for_umop("onebot:group:123")

    assert result == "exact-match"


def test_message_type_specific_route_beats_global_default() -> None:
    router = make_router(
        {
            "::": "global-default",
            ":group:": "group-default",
        }
    )

    result = router.get_conf_id_for_umop("telegram:group:9988")

    assert result == "group-default"


def test_partial_wildcard_route_beats_catch_all_platform_route() -> None:
    router = make_router(
        {
            "telegram::": "platform-default",
            "telegram:group:room-*": "room-pattern",
        }
    )

    result = router.get_conf_id_for_umop("telegram:group:room-42")

    assert result == "room-pattern"


def test_same_specificity_routes_keep_insertion_order() -> None:
    router = make_router(
        {
            "telegram:group:room-*": "first-match",
            "telegram:group:room-?": "second-match",
        }
    )

    result = router.get_conf_id_for_umop("telegram:group:room-7")

    assert result == "first-match"


def test_invalid_pattern_priority_is_ignored_when_no_match() -> None:
    router = make_router(
        {
            "invalid-pattern": "broken",
            "::": "global-default",
        }
    )

    result = router.get_conf_id_for_umop("discord:friend:1001")

    assert result == "global-default"


@pytest.mark.asyncio
async def test_update_routing_data_rejects_invalid_umo_format() -> None:
    router = make_router()

    with pytest.raises(ValueError, match="umop keys must be strings"):
        await router.update_routing_data({"invalid-pattern": "conf-a"})
