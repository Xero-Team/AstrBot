from types import SimpleNamespace
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
async def test_initialize_discards_corrupt_persisted_routing_data() -> None:
    preferences = SimpleNamespace(get_async=AsyncMock(return_value=["::"]))
    router = UmopConfigRouter(sp=preferences)

    await router.initialize()

    assert router.umop_to_conf_id == {}
    assert router.get_conf_id_for_umop("telegram:group:1000") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("routing_data", "error_message"),
    [
        (["::"], "routing data"),
        ({"::": ""}, "routing data"),
        ({"::": object()}, "routing data"),
        ({1: "default"}, "umop keys must be strings"),
    ],
)
async def test_update_routing_data_rejects_invalid_mapping_values(
    routing_data: object,
    error_message: str,
) -> None:
    preferences = SimpleNamespace(global_put=AsyncMock())
    router = make_router({"::": "original"})
    router.sp = preferences

    with pytest.raises(ValueError, match=error_message):
        await router.update_routing_data(routing_data)  # type: ignore[arg-type]

    assert router.umop_to_conf_id == {"::": "original"}
    preferences.global_put.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_route_rejects_non_string_umo() -> None:
    preferences = SimpleNamespace(global_put=AsyncMock())
    router = make_router({"::": "original"})
    router.sp = preferences

    with pytest.raises(ValueError, match="umop must be a string"):
        await router.update_route(1, "replacement")  # type: ignore[arg-type]

    assert router.umop_to_conf_id == {"::": "original"}
    preferences.global_put.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_routing_data_owns_a_snapshot_of_valid_routes() -> None:
    preferences = SimpleNamespace(global_put=AsyncMock())
    router = make_router()
    router.sp = preferences
    routes = {"::": "default"}

    await router.update_routing_data(routes)
    routes["telegram:group:1000"] = "later"

    assert router.umop_to_conf_id == {"::": "default"}
    preferences.global_put.assert_awaited_once_with(
        "umop_config_routing",
        {"::": "default"},
    )


@pytest.mark.asyncio
async def test_update_routing_data_keeps_live_routes_when_persistence_fails() -> None:
    preferences = SimpleNamespace(
        global_put=AsyncMock(side_effect=RuntimeError("storage unavailable"))
    )
    router = make_router({"::": "original"})
    router.sp = preferences

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await router.update_routing_data({"::": "replacement"})

    assert router.umop_to_conf_id == {"::": "original"}


@pytest.mark.asyncio
async def test_update_route_keeps_live_routes_when_persistence_fails() -> None:
    preferences = SimpleNamespace(
        global_put=AsyncMock(side_effect=RuntimeError("storage unavailable"))
    )
    router = make_router({"::": "original"})
    router.sp = preferences

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await router.update_route("telegram:group:1000", "replacement")

    assert router.umop_to_conf_id == {"::": "original"}


@pytest.mark.asyncio
async def test_delete_route_keeps_live_routes_when_persistence_fails() -> None:
    preferences = SimpleNamespace(
        global_put=AsyncMock(side_effect=RuntimeError("storage unavailable"))
    )
    router = make_router({"::": "original"})
    router.sp = preferences

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await router.delete_route("::")

    assert router.umop_to_conf_id == {"::": "original"}
