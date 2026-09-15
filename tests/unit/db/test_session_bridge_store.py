import pytest
from sqlalchemy.exc import IntegrityError

from astrbot.core.db.sqlite import SQLiteDatabase


async def _insert_rule(
    temp_db: SQLiteDatabase,
    *,
    subject_id: str = "im:source:bot:actor",
    source_umo: str = "source:FriendMessage:sender",
    target_umo: str = "target:GroupMessage:room",
    source_config_id: str = "default",
    target_config_id: str = "default",
    kind: str = "watch",
    expires_at: int | None = 1_800_000_000,
    **kwargs,
):
    return await temp_db.insert_session_bridge_rule(
        subject_id=subject_id,
        source_umo=source_umo,
        target_umo=target_umo,
        source_config_id=source_config_id,
        target_config_id=target_config_id,
        kind=kind,
        expires_at=expires_at,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_insert_session_bridge_rule_writes_s1_defaults(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    watch = await _insert_rule(temp_db)
    connect = await _insert_rule(
        temp_db,
        target_umo="other:GroupMessage:room",
        kind="connect",
        expires_at=None,
    )

    assert len(watch.rule_id) == 12
    assert watch.rule_id == watch.rule_id.lower()
    assert watch.rule_id.isalnum()
    assert int(watch.rule_id, 16) >= 0
    assert watch.header is True
    assert watch.pair_id is None
    assert watch.match == {}
    assert watch.except_ == {}
    assert watch.kind == "watch"
    assert watch.expires_at == 1_800_000_000
    assert connect.kind == "connect"
    assert connect.expires_at is None


@pytest.mark.asyncio
async def test_insert_session_bridge_rule_accepts_digit_only_hex_id(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    watch = await _insert_rule(temp_db, rule_id="225823821909")

    assert watch.rule_id == "225823821909"
    assert watch.rule_id == watch.rule_id.lower()
    assert int(watch.rule_id, 16) >= 0


@pytest.mark.asyncio
async def test_direction_unique_constraint_rejects_duplicate_edge(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    await _insert_rule(temp_db)
    with pytest.raises(IntegrityError):
        await _insert_rule(temp_db, kind="connect", expires_at=None)


@pytest.mark.asyncio
async def test_session_bridge_rule_queries_update_and_delete(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    watch = await _insert_rule(temp_db)
    other = await _insert_rule(
        temp_db,
        subject_id="im:source:bot:other",
        source_umo="ops:FriendMessage:box",
        target_umo="target:GroupMessage:room",
        source_config_id="ops",
        kind="connect",
        expires_at=None,
    )
    fetched = await temp_db.get_session_bridge_rule(watch.rule_id)
    by_direction = await temp_db.get_session_bridge_rule_by_direction(
        watch.subject_id, watch.source_umo, watch.target_umo
    )
    owned = await temp_db.list_session_bridge_rules_by_subject(watch.subject_id)
    touching = await temp_db.list_session_bridge_rules_touching_config("ops")
    connects = await temp_db.list_session_bridge_connects_for_listener(
        other.subject_id, other.source_umo
    )
    updated = await temp_db.update_session_bridge_rule(
        watch.rule_id, expires_at=1_800_000_100
    )

    assert fetched is not None
    assert fetched.rule_id == watch.rule_id
    assert by_direction is not None
    assert by_direction.rule_id == watch.rule_id
    assert [item.rule_id for item in owned] == [watch.rule_id]
    assert [item.rule_id for item in touching] == [other.rule_id]
    assert [item.rule_id for item in connects] == [other.rule_id]
    assert updated is not None
    assert updated.expires_at == 1_800_000_100
    assert updated.kind == "watch"

    await temp_db.delete_session_bridge_connects_for_listener(
        other.subject_id, other.source_umo
    )
    await temp_db.delete_session_bridge_rule(watch.rule_id)
    remaining = await temp_db.list_session_bridge_rules()
    assert remaining == []


@pytest.mark.asyncio
async def test_insert_session_bridge_pair_replaces_both_directions(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    watch = await _insert_rule(temp_db)
    reverse = await _insert_rule(
        temp_db,
        source_umo="target:GroupMessage:room",
        target_umo="source:FriendMessage:sender",
        kind="connect",
        expires_at=None,
    )
    left, right = await temp_db.insert_session_bridge_pair(
        subject_id=watch.subject_id,
        source_umo=watch.source_umo,
        target_umo=watch.target_umo,
        source_config_id=watch.source_config_id,
        target_config_id=watch.target_config_id,
        pair_id="pairidabcdef",
        drop_rule_ids=(watch.rule_id, reverse.rule_id),
    )
    assert left.kind == "pair"
    assert right.kind == "pair"
    assert left.header is True
    assert right.header is True
    assert left.pair_id == right.pair_id == "pairidabcdef"
    assert left.source_umo == watch.source_umo
    assert right.source_umo == watch.target_umo
    assert await temp_db.get_session_bridge_rule(watch.rule_id) is None
    assert await temp_db.get_session_bridge_rule(reverse.rule_id) is None


@pytest.mark.asyncio
async def test_insert_session_bridge_pair_rolls_back_partial_replace(
    temp_db: SQLiteDatabase,
):
    await temp_db.initialize()
    watch = await _insert_rule(temp_db)
    reverse = await _insert_rule(
        temp_db,
        source_umo="target:GroupMessage:room",
        target_umo="source:FriendMessage:sender",
        kind="watch",
        expires_at=1_800_000_000,
    )
    with pytest.raises(IntegrityError):
        await temp_db.insert_session_bridge_pair(
            subject_id=watch.subject_id,
            source_umo=watch.source_umo,
            target_umo=watch.target_umo,
            source_config_id=watch.source_config_id,
            target_config_id=watch.target_config_id,
            pair_id="pairidabcdef",
            drop_rule_ids=(watch.rule_id,),
        )
    assert await temp_db.get_session_bridge_rule(watch.rule_id) is not None
    assert await temp_db.get_session_bridge_rule(reverse.rule_id) is not None
