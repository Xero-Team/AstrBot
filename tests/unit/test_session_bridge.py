import secrets
from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from astrbot.core.auth.models import AuthContext, Resource, Role, Subject
from astrbot.core.platform.message_protocol import (
    ContentKind,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    PortablePart,
    SenderSnapshot,
)
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.route_identity import PlatformRouteIdentity
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.session_bridge import (
    DEFAULT_WATCH_TTL_SECONDS,
    MAX_WATCH_TTL_SECONDS,
    MIN_WATCH_TTL_SECONDS,
    SessionBridgeManager,
)


def _event(umo="source:FriendMessage:sender", *, sender="actor", components=()):
    from astrbot.core.platform.message_session import MessageSession

    subject = Subject.im(
        platform_instance="source", bot_account_id="bot", sender_id=sender
    )
    session = MessageSession.from_str(umo)
    return SimpleNamespace(
        unified_msg_origin=umo,
        subject=subject,
        auth_context=AuthContext(
            subject=subject,
            source="im",
            config_id="default",
            authenticated=True,
            origin_session_resource_id=Resource.session("default", umo).id,
        ),
        route_identity=PlatformRouteIdentity(
            session.platform_id, session.message_type, session.session_id
        ),
        get_messages=lambda: list(components),
        get_platform_name=lambda: "telegram",
        get_sender_id=lambda: sender,
        get_sender_name=lambda: sender,
        get_self_id=lambda: "bot",
        message_obj=SimpleNamespace(message_id="inbound"),
        created_at=0.0,
    )


class FakeSessionBridgeStore:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}
        self.by_direction: dict[tuple[str, str, str], str] = {}

    def seed(self, **fields) -> SimpleNamespace:
        payload = {
            "header": True,
            "pair_id": None,
            "match": {},
            "except_": {},
        }
        payload.update(fields)
        row = SimpleNamespace(**payload)
        self.rows[row.rule_id] = row
        self.by_direction[(row.subject_id, row.source_umo, row.target_umo)] = (
            row.rule_id
        )
        return row

    async def insert_session_bridge_rule(self, **kwargs) -> SimpleNamespace:
        key = (kwargs["subject_id"], kwargs["source_umo"], kwargs["target_umo"])
        if key in self.by_direction:
            raise IntegrityError("statement", {}, Exception("direction"))
        rule_id = kwargs.get("rule_id") or secrets.token_hex(6)
        if rule_id in self.rows:
            raise IntegrityError("statement", {}, Exception("rule_id"))
        return self.seed(
            rule_id=rule_id,
            expires_at=kwargs.get("expires_at"),
            kind=kwargs["kind"],
            subject_id=kwargs["subject_id"],
            source_umo=kwargs["source_umo"],
            target_umo=kwargs["target_umo"],
            source_config_id=kwargs["source_config_id"],
            target_config_id=kwargs["target_config_id"],
            header=kwargs.get("header", True),
            pair_id=kwargs.get("pair_id"),
            match=kwargs.get("match") or {},
            except_=kwargs.get("except_") or {},
        )

    async def get_session_bridge_rule(self, rule_id: str):
        return self.rows.get(rule_id)

    async def get_session_bridge_rule_by_direction(
        self, subject_id: str, source_umo: str, target_umo: str
    ):
        rule_id = self.by_direction.get((subject_id, source_umo, target_umo))
        return None if rule_id is None else self.rows.get(rule_id)

    async def list_session_bridge_rules(self):
        return list(self.rows.values())

    async def list_session_bridge_rules_by_subject(self, subject_id: str):
        return [row for row in self.rows.values() if row.subject_id == subject_id]

    async def list_session_bridge_connects_for_listener(
        self, subject_id: str, source_umo: str
    ):
        return [
            row
            for row in self.rows.values()
            if row.subject_id == subject_id
            and row.source_umo == source_umo
            and row.kind == "connect"
        ]

    async def list_session_bridge_rules_touching_config(self, config_id: str):
        return [
            row
            for row in self.rows.values()
            if row.source_config_id == config_id or row.target_config_id == config_id
        ]

    async def update_session_bridge_rule(self, rule_id: str, **kwargs):
        row = self.rows.get(rule_id)
        if row is None:
            return None
        for key, value in kwargs.items():
            setattr(row, key, value)
        return row

    async def delete_session_bridge_rule(self, rule_id: str) -> None:
        row = self.rows.pop(rule_id, None)
        if row is None:
            return
        self.by_direction.pop((row.subject_id, row.source_umo, row.target_umo), None)

    async def delete_session_bridge_connects_for_listener(
        self, subject_id: str, source_umo: str
    ) -> None:
        for row in list(self.rows.values()):
            if (
                row.subject_id == subject_id
                and row.source_umo == source_umo
                and row.kind == "connect"
            ):
                await self.delete_session_bridge_rule(row.rule_id)


def _manager(send=None, store=None, *, max_watches_per_subject=16, get_config_id=None):
    authorization = SimpleNamespace(
        authorize=AsyncMock(
            return_value=SimpleNamespace(allowed=True, effective_role=None)
        )
    )
    sender = send or AsyncMock(
        return_value=PlatformSendResult("target", True, "target", message_ids=("sent",))
    )
    manager = SessionBridgeManager(
        sender,
        lambda _: MessageDeliveryCapabilities(quote=True, media=frozenset({"image"})),
        authorization=authorization,
        get_config_id=get_config_id or (lambda _: "default"),
        store=store or FakeSessionBridgeStore(),
        max_watches_per_subject=max_watches_per_subject,
    )
    return manager, authorization, sender


def test_session_bridge_state_is_not_a_public_export():
    import astrbot.api.platform as api_platform
    import astrbot.core.platform as core_platform

    assert "SessionBridgeState" not in api_platform.__all__
    assert "SessionBridgeState" not in core_platform.__all__
    assert not hasattr(api_platform, "SessionBridgeState")


@pytest.mark.asyncio
async def test_watch_records_rule_id_and_rejects_zero_ttl():
    manager, _, _ = _manager()
    event = _event()
    target = "target:GroupMessage:room"
    watch = await manager.watch(event, target, ttl_seconds=1)
    assert len(watch.rule_id) == 12
    assert watch.rule_id == watch.rule_id.lower()
    int(watch.rule_id, 16)
    assert 0 <= watch.remaining_seconds <= 1
    with pytest.raises(ValueError, match="Invalid watch duration"):
        await manager.watch(event, target, ttl_seconds=0)
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_custom_source_and_ttl_and_rejects_out_of_range():
    manager, authorization, _ = _manager()
    event = _event()
    listener = "other:FriendMessage:box"
    target = "target:GroupMessage:room"
    watch = await manager.watch(
        event, target, source_umo=listener, ttl_seconds=MIN_WATCH_TTL_SECONDS
    )
    assert watch.source_umo == listener
    assert watch.target_umo == target
    assert MIN_WATCH_TTL_SECONDS - 1 <= watch.remaining_seconds <= MIN_WATCH_TTL_SECONDS
    assert [call.args[2].umo for call in authorization.authorize.await_args_list] == [
        listener,
        target,
    ]
    default = await manager.watch(_event("source:FriendMessage:two"), target)
    assert (
        DEFAULT_WATCH_TTL_SECONDS - 1
        <= default.remaining_seconds
        <= DEFAULT_WATCH_TTL_SECONDS
    )
    with pytest.raises(ValueError, match="Invalid watch duration"):
        await manager.watch(event, target, ttl_seconds=MIN_WATCH_TTL_SECONDS - 1)
    with pytest.raises(ValueError, match="Invalid watch duration"):
        await manager.watch(event, target, ttl_seconds=MAX_WATCH_TTL_SECONDS + 1)
    assert await manager.unwatch(event, target, source_umo=listener)
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_expiry_notifies_listener(monkeypatch):
    import asyncio

    sent = []

    async def send(session, chain):
        sent.append((str(session), chain.get_plain_text()))
        return PlatformSendResult(session.platform_id, True, str(session))

    async def instant_sleep(_delay):
        return

    monkeypatch.setattr(
        "astrbot.core.platform.session_bridge.asyncio.sleep", instant_sleep
    )
    manager, _, _ = _manager(send)
    source = "source:FriendMessage:sender"
    target = "target:GroupMessage:room"
    await manager.watch(_event(source), target, ttl_seconds=60)
    await asyncio.sleep(0)
    pending = [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("session-watch-expire")
    ]
    if pending:
        await asyncio.gather(*pending)
    assert sent == [(source, "对 target:GroupMessage:room 的监听已结束。")]
    assert await manager.list_watches(_event(source)) == ()
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_expiry_notice_follows_locale(monkeypatch):
    import asyncio

    sent = []

    async def send(session, chain):
        sent.append(chain.get_plain_text())
        return PlatformSendResult(session.platform_id, True, str(session))

    async def instant_sleep(_delay):
        return

    monkeypatch.setattr(
        "astrbot.core.platform.session_bridge.asyncio.sleep", instant_sleep
    )
    manager, _, _ = _manager(send)
    manager._get_locale = AsyncMock(return_value="en-US")
    await manager.watch(_event(), "target:GroupMessage:room", ttl_seconds=60)
    await asyncio.sleep(0)
    pending = [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("session-watch-expire")
    ]
    if pending:
        await asyncio.gather(*pending)
    assert sent == ["The watch on target:GroupMessage:room has ended."]
    await manager.terminate()


@pytest.mark.asyncio
async def test_terminate_clears_watches_and_message_maps():
    manager, _, _ = _manager()
    event = _event()
    await manager.watch(event, "target:GroupMessage:room")
    await manager.observe(
        MessageEnvelope(
            PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
            source_message_id="original",
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )
    assert manager._state.total_kind("watch")
    assert manager._message_ids
    await manager.terminate()
    assert manager._state.total_kind("watch") == 0
    assert manager._state.total_kind("connect") == 0
    assert manager._forwarded == {}
    assert manager._message_ids == {}


@pytest.mark.asyncio
async def test_connect_forwards_without_expiry_and_send_uses_link():
    from astrbot.core.message.components import Plain
    from astrbot.core.star.plugin_context import SessionBridgeCapability

    sent = []

    async def send(session, chain):
        sent.append((str(session), chain.get_plain_text()))
        return PlatformSendResult(session.platform_id, True, str(session))

    manager, authorization, _ = _manager(send)
    event = _event()
    target = "target:GroupMessage:room"
    capability = SessionBridgeCapability(manager)
    link = await capability.connect(event, target)
    assert link.expires_at is None
    assert await capability.connection(event) == link
    assert [call.args[2].umo for call in authorization.authorize.await_args_list] == [
        event.unified_msg_origin,
        target,
    ]
    await manager.observe(
        MessageEnvelope(
            PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
            source_message_id="9",
            sender=SenderSnapshot("1", "Alice", "napcat"),
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )
    assert sent[-1][0] == event.unified_msg_origin
    assert "hello" in sent[-1][1]

    send_event = _event(components=[Plain("/send ping")])
    receipt = await capability.send(send_event, target, target_in_header=False)
    assert receipt.status == "accepted"
    assert await capability.disconnect(event)
    assert await capability.connection(event) is None
    await manager.terminate()


@pytest.mark.asyncio
async def test_same_watch_direction_keeps_rule_id_and_resets_ttl():
    manager, _, _ = _manager()
    event = _event()
    target = "target:GroupMessage:room"
    first = await manager.watch(event, target, ttl_seconds=10)
    second = await manager.watch(event, target, ttl_seconds=100)
    assert first.rule_id == second.rule_id
    assert 90 <= second.remaining_seconds <= 100
    listed = await manager.list_watches(event)
    assert len(listed) == 1
    await manager.terminate()


@pytest.mark.asyncio
async def test_connect_retarget_replaces_and_same_target_keeps_rule_id():
    manager, _, _ = _manager()
    event = _event()
    first = await manager.connect(event, "target:GroupMessage:one")
    again = await manager.connect(event, "target:GroupMessage:one")
    assert again.rule_id == first.rule_id
    retarget = await manager.connect(event, "target:GroupMessage:two")
    assert retarget.rule_id != first.rule_id
    current = await manager.connection(event)
    assert current is not None
    assert current.target_umo == "target:GroupMessage:two"
    assert manager._state.total_kind("connect") == 1
    await manager.terminate()


@pytest.mark.asyncio
async def test_cross_kind_replace_uses_new_rule_id():
    manager, _, _ = _manager()
    event = _event()
    target = "target:GroupMessage:room"
    watch = await manager.watch(event, target, ttl_seconds=30)
    link = await manager.connect(event, target)
    assert link.rule_id != watch.rule_id
    assert await manager.list_watches(event) == ()
    current = await manager.connection(event)
    assert current is not None
    assert current.rule_id == link.rule_id
    watch_again = await manager.watch(event, target, ttl_seconds=30)
    assert watch_again.rule_id != link.rule_id
    assert await manager.connection(event) is None
    await manager.terminate()


@pytest.mark.asyncio
async def test_pair_direction_rejects_watch_and_connect():
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="abcdef123456",
        subject_id=_event().subject.id,
        source_umo="source:FriendMessage:sender",
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="pair",
        expires_at=None,
    )
    manager, _, _ = _manager(store=store)
    event = _event()
    with pytest.raises(ValueError, match="occupied by a pair"):
        await manager.watch(event, "target:GroupMessage:room", ttl_seconds=30)
    with pytest.raises(ValueError, match="occupied by a pair"):
        await manager.connect(event, "target:GroupMessage:room")
    remaining = await store.get_session_bridge_rule("abcdef123456")
    assert remaining is not None
    assert remaining.kind == "pair"
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_reloads_unexpired_watch_and_connect():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="watchrule0001",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    store.seed(
        rule_id="connectrule01",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="other:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="connect",
        expires_at=None,
    )
    manager, _, _ = _manager(store=store)
    await manager.restore()
    watches = await manager.list_watches(event)
    assert [item.rule_id for item in watches] == ["watchrule0001"]
    link = await manager.connection(event)
    assert link is not None
    assert link.rule_id == "connectrule01"
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_deletes_expired_watch_and_notifies():
    sent = []

    async def send(session, chain):
        sent.append((str(session), chain.get_plain_text()))
        return PlatformSendResult(session.platform_id, True, str(session))

    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="expiredwatch1",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) - 10,
    )
    manager, _, _ = _manager(send, store)
    await manager.restore()
    assert await manager.list_watches(event) == ()
    assert await store.get_session_bridge_rule("expiredwatch1") is None
    assert sent == [
        (event.unified_msg_origin, "对 target:GroupMessage:room 的监听已结束。")
    ]
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_deletes_row_when_reauthorize_denied():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="revokedwatch1",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    manager, authorization, _ = _manager(store=store)
    authorization.authorize = AsyncMock(return_value=SimpleNamespace(allowed=False))
    await manager.restore()
    assert await manager.list_watches(event) == ()
    assert await store.get_session_bridge_rule("revokedwatch1") is None
    await manager.terminate()


@pytest.mark.asyncio
async def test_unavailable_adapter_keeps_restored_rule():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="hangingwatch1",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    manager, _, send = _manager(store=store)
    manager._get_capabilities = lambda _: MessageDeliveryCapabilities(
        proactive=False, available=False
    )
    await manager.restore()
    await manager.observe(
        MessageEnvelope(
            PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
            source_message_id="keep-me",
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )
    assert await store.get_session_bridge_rule("hangingwatch1") is not None
    send.assert_not_called()
    await manager.terminate()


@pytest.mark.asyncio
async def test_terminate_keeps_sqlite_rows():
    store = FakeSessionBridgeStore()
    manager, _, _ = _manager(store=store)
    watch = await manager.watch(_event(), "target:GroupMessage:room", ttl_seconds=30)
    await manager.terminate()
    assert await store.get_session_bridge_rule(watch.rule_id) is not None
    assert manager._state.total_kind("watch") == 0


@pytest.mark.asyncio
async def test_list_links_creator_and_instance_operator_visibility():
    owner = _event()
    other = _event(sender="other")
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="ownwatch00001",
        subject_id=owner.subject.id,
        source_umo=owner.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 60,
    )
    store.seed(
        rule_id="otherwatch001",
        subject_id=other.subject.id,
        source_umo="ops:FriendMessage:box",
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="ops",
        kind="connect",
        expires_at=None,
    )
    store.seed(
        rule_id="foreignwatch01",
        subject_id=other.subject.id,
        source_umo="alt:FriendMessage:x",
        target_umo="alt:GroupMessage:y",
        source_config_id="othercfg",
        target_config_id="othercfg",
        kind="watch",
        expires_at=int(time()) + 60,
    )
    manager, authorization, _ = _manager(store=store)
    authorization.authorize = AsyncMock(
        return_value=SimpleNamespace(allowed=True, effective_role=None)
    )
    own_links = await manager.list_links(owner)
    assert [item[0].rule_id for item in own_links] == ["ownwatch00001"]
    authorization.authorize = AsyncMock(
        return_value=SimpleNamespace(
            allowed=True, effective_role=Role.INSTANCE_OPERATOR
        )
    )
    operator_links = await manager.list_links(owner)
    assert {item[0].rule_id for item in operator_links} == {
        "ownwatch00001",
        "otherwatch001",
    }
    authorization.authorize = AsyncMock(
        return_value=SimpleNamespace(allowed=True, effective_role=Role.ROOT)
    )
    root_links = await manager.list_links(owner)
    assert {item[0].rule_id for item in root_links} == {
        "ownwatch00001",
        "otherwatch001",
        "foreignwatch01",
    }
    await manager.terminate()


@pytest.mark.asyncio
async def test_unlink_allows_creator_after_revoke_and_scopes_instance_operator():
    owner = _event()
    other = _event(sender="other")
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="ownwatch00001",
        subject_id=owner.subject.id,
        source_umo=owner.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 60,
    )
    store.seed(
        rule_id="foreignwatch01",
        subject_id=other.subject.id,
        source_umo="alt:FriendMessage:x",
        target_umo="alt:GroupMessage:y",
        source_config_id="othercfg",
        target_config_id="othercfg",
        kind="watch",
        expires_at=int(time()) + 60,
    )
    manager, authorization, _ = _manager(store=store)
    authorization.authorize = AsyncMock(
        return_value=SimpleNamespace(allowed=False, effective_role=None)
    )
    assert await manager.unlink(owner, "ownwatch00001")
    assert await store.get_session_bridge_rule("ownwatch00001") is None
    authorization.authorize = AsyncMock(
        return_value=SimpleNamespace(
            allowed=True, effective_role=Role.INSTANCE_OPERATOR
        )
    )
    with pytest.raises(PermissionError):
        await manager.unlink(owner, "foreignwatch01")
    assert await store.get_session_bridge_rule("foreignwatch01") is not None
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_limit_does_not_drop_existing_connect():
    manager, _, _ = _manager(max_watches_per_subject=1)
    event = _event()
    await manager.watch(event, "target:GroupMessage:one", ttl_seconds=30)
    link = await manager.connect(event, "target:GroupMessage:two")
    with pytest.raises(ValueError, match="Watch limit exceeded"):
        await manager.watch(event, "target:GroupMessage:two", ttl_seconds=30)
    current = await manager.connection(event)
    assert current is not None
    assert current.rule_id == link.rule_id
    await manager.terminate()


@pytest.mark.asyncio
async def test_connect_limit_does_not_drop_existing_watch():
    manager, _, _ = _manager(max_watches_per_subject=1)
    event = _event()
    other = _event("source:FriendMessage:other")
    await manager.connect(other, "target:GroupMessage:two")
    watch = await manager.watch(event, "target:GroupMessage:one", ttl_seconds=30)
    with pytest.raises(ValueError, match="Watch limit exceeded"):
        await manager.connect(event, "target:GroupMessage:one")
    listed = await manager.list_watches(event)
    assert [item.rule_id for item in listed] == [watch.rule_id]
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_skips_pair_and_discards_invalid_umo():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="pairrule00001",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="pair",
        expires_at=None,
    )
    store.seed(
        rule_id="badumorule001",
        subject_id=event.subject.id,
        source_umo="not-a-umo",
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    manager, _, _ = _manager(store=store)
    await manager.restore()
    assert await store.get_session_bridge_rule("pairrule00001") is not None
    assert await store.get_session_bridge_rule("badumorule001") is None
    assert manager._state.total_kind("pair") == 0
    assert manager._state.total_kind("watch") == 0
    await manager.terminate()


@pytest.mark.asyncio
async def test_list_links_hides_expired_watches():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="expiredlink01",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) - 10,
    )
    store.seed(
        rule_id="liveconnect01",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="other:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="connect",
        expires_at=None,
    )
    manager, _, _ = _manager(store=store)
    links = await manager.list_links(event)
    assert [item[0].rule_id for item in links] == ["liveconnect01"]
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_expired_invalid_subject_does_not_abort():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="expiredbadid1",
        subject_id="not-a-subject",
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) - 10,
    )
    store.seed(
        rule_id="livewatch00001",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="other:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    manager, _, _ = _manager(store=store)
    await manager.restore()
    assert await store.get_session_bridge_rule("expiredbadid1") is None
    watches = await manager.list_watches(event)
    assert [item.rule_id for item in watches] == ["livewatch00001"]
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_continues_after_unexpected_authorize_error():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="brokenwatch01",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    store.seed(
        rule_id="goodwatch0001",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="other:GroupMessage:room",
        source_config_id="default",
        target_config_id="default",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    manager, authorization, _ = _manager(store=store)

    async def authorize(_subject, _action, resource, _context):
        if resource.umo == "target:GroupMessage:room":
            raise RuntimeError("transient")
        return SimpleNamespace(allowed=True, effective_role=None)

    authorization.authorize = authorize
    await manager.restore()
    assert await store.get_session_bridge_rule("brokenwatch01") is not None
    watches = await manager.list_watches(event)
    assert [item.rule_id for item in watches] == ["goodwatch0001"]
    await manager.terminate()


@pytest.mark.asyncio
async def test_same_direction_refresh_updates_config_ids():
    store = FakeSessionBridgeStore()
    manager, _, _ = _manager(store=store, get_config_id=lambda _: "ops")
    event = _event()
    target = "target:GroupMessage:room"
    watch = await manager.watch(event, target, ttl_seconds=30)
    manager._get_config_id = lambda _: "other"
    watch_again = await manager.watch(event, target, ttl_seconds=30)
    assert watch_again.rule_id == watch.rule_id
    watch_row = await store.get_session_bridge_rule(watch.rule_id)
    assert watch_row is not None
    assert watch_row.source_config_id == "other"
    assert watch_row.target_config_id == "other"

    link = await manager.connect(event, target)
    manager._get_config_id = lambda _: "third"
    link_again = await manager.connect(event, target)
    assert link_again.rule_id == link.rule_id
    link_row = await store.get_session_bridge_rule(link.rule_id)
    assert link_row is not None
    assert link_row.source_config_id == "third"
    assert link_row.target_config_id == "third"
    await manager.terminate()


@pytest.mark.asyncio
async def test_restore_refreshes_stale_config_ids():
    event = _event()
    store = FakeSessionBridgeStore()
    store.seed(
        rule_id="staleconfig01",
        subject_id=event.subject.id,
        source_umo=event.unified_msg_origin,
        target_umo="target:GroupMessage:room",
        source_config_id="stale",
        target_config_id="stale",
        kind="watch",
        expires_at=int(time()) + 3600,
    )
    manager, _, _ = _manager(store=store)
    await manager.restore()
    row = await store.get_session_bridge_rule("staleconfig01")
    assert row is not None
    assert row.source_config_id == "default"
    assert row.target_config_id == "default"
    await manager.terminate()
