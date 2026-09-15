"""Live grant index and SQLite IO for session-bridge directed edges."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.auth.models import AuthContext, Subject

if TYPE_CHECKING:
    from astrbot.core.db.po.session_bridge import SessionBridgeRule
    from astrbot.core.db.protocols import SessionBridgeStore

PAIR_OCCUPIED = "Direction is occupied by a pair"
GrantKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class SessionWatch:
    """One watch or unbounded link owned by a trusted authorization subject."""

    source_umo: str
    target_umo: str
    subject_id: str
    expires_at: float | None
    rule_id: str

    @property
    def remaining_seconds(self) -> int:
        if self.expires_at is None:
            return 0
        return max(0, int(self.expires_at - time()))


@dataclass(frozen=True, slots=True)
class WatchGrant:
    """Trusted actor snapshot paired with one live watch or connect."""

    watch: SessionWatch
    subject: Subject
    context: AuthContext
    kind: str
    source_config_id: str
    target_config_id: str


ExpireWatch = Callable[[GrantKey, WatchGrant], Coroutine[object, object, None]]


class SessionBridgeState:
    """Unified direction index, connect 1:1 map, expiry tasks, and store IO."""

    def __init__(self, store: SessionBridgeStore) -> None:
        self._store = store
        self._grants: dict[GrantKey, WatchGrant] = {}
        self._connect_by_listener: dict[tuple[str, str], GrantKey] = {}
        self._expiry_tasks: dict[GrantKey, asyncio.Task[None]] = {}

    def count_kind(self, subject_id: str, kind: str) -> int:
        return sum(
            1
            for grant in self._grants.values()
            if grant.watch.subject_id == subject_id and grant.kind == kind
        )

    def total_kind(self, kind: str) -> int:
        return sum(1 for grant in self._grants.values() if grant.kind == kind)

    def get(self, key: GrantKey) -> WatchGrant | None:
        return self._grants.get(key)

    def connect_for(self, subject_id: str, source_umo: str) -> WatchGrant | None:
        key = self._connect_by_listener.get((subject_id, source_umo))
        return None if key is None else self._grants.get(key)

    def watches_for(self, subject_id: str, source_umo: str) -> tuple[SessionWatch, ...]:
        return tuple(
            grant.watch
            for key, grant in self._grants.items()
            if key[:2] == (subject_id, source_umo) and grant.kind == "watch"
        )

    def grants_observing(self, origin: str) -> tuple[tuple[GrantKey, WatchGrant], ...]:
        return tuple(
            (key, grant)
            for key, grant in self._grants.items()
            if grant.watch.target_umo == origin
        )

    def store_key(self, watch: SessionWatch) -> GrantKey:
        return (watch.subject_id, watch.source_umo, watch.target_umo)

    def grant_active(self, key: GrantKey, grant: WatchGrant, now: float) -> bool:
        if self._grants.get(key) is not grant:
            return False
        return grant.watch.expires_at is None or grant.watch.expires_at > now

    async def purge(self, now: float) -> tuple[WatchGrant, ...]:
        expired: list[WatchGrant] = []
        for key, grant in tuple(self._grants.items()):
            expires_at = grant.watch.expires_at
            if expires_at is not None and expires_at <= now:
                await self._store.delete_session_bridge_rule(grant.watch.rule_id)
                self._drop_memory(key)
                task = self._expiry_tasks.pop(key, None)
                if task is not None:
                    task.cancel()
                expired.append(grant)
        return tuple(expired)

    def arm_expiry(
        self,
        key: GrantKey,
        grant: WatchGrant,
        expire: ExpireWatch,
    ) -> None:
        previous = self._expiry_tasks.pop(key, None)
        if previous is not None:
            previous.cancel()
        if grant.watch.expires_at is None:
            return
        task = asyncio.create_task(
            expire(key, grant),
            name=f"session-watch-expire:{key[1]}:{key[2]}",
        )
        self._expiry_tasks[key] = task

        def _done(done: asyncio.Task[None]) -> None:
            if self._expiry_tasks.get(key) is done:
                self._expiry_tasks.pop(key, None)
            if done.cancelled():
                return
            try:
                exc = done.exception()
            except Exception:
                return
            if exc is not None:
                logger.warning("Session watch expiry task failed")

        task.add_done_callback(_done)

    def take_expiry_tasks(self) -> list[asyncio.Task[None]]:
        tasks = list(self._expiry_tasks.values())
        self._expiry_tasks.clear()
        return tasks

    def clear_grants(self) -> None:
        self._grants.clear()
        self._connect_by_listener.clear()

    async def save_watch(
        self,
        *,
        subject: Subject,
        context: AuthContext,
        source_umo: str,
        target_umo: str,
        source_config_id: str,
        target_config_id: str,
        expires_at: int,
        max_per_subject: int,
    ) -> WatchGrant:
        key = (subject.id, source_umo, target_umo)
        stored = await self._store.get_session_bridge_rule_by_direction(
            subject.id, source_umo, target_umo
        )
        if stored is not None and stored.kind == "pair":
            raise ValueError(PAIR_OCCUPIED)
        if stored is not None and stored.kind == "watch":
            updated = await self._store.update_session_bridge_rule(
                stored.rule_id,
                expires_at=expires_at,
                source_config_id=source_config_id,
                target_config_id=target_config_id,
            )
            row = updated or stored
            grant = self._grant_from_row(row, subject, context)
            self._index(grant)
            return grant
        if self.count_kind(subject.id, "watch") >= max_per_subject:
            raise ValueError("Watch limit exceeded")
        if self.total_kind("watch") >= 1024:
            raise ValueError("Runtime watch limit exceeded")
        if stored is not None:
            await self._delete_row(stored.rule_id, key)
        row = await self._store.insert_session_bridge_rule(
            subject_id=subject.id,
            source_umo=source_umo,
            target_umo=target_umo,
            source_config_id=source_config_id,
            target_config_id=target_config_id,
            kind="watch",
            expires_at=expires_at,
        )
        grant = self._grant_from_row(row, subject, context)
        self._index(grant)
        return grant

    async def save_connect(
        self,
        *,
        subject: Subject,
        context: AuthContext,
        source_umo: str,
        target_umo: str,
        source_config_id: str,
        target_config_id: str,
        max_per_subject: int,
    ) -> WatchGrant:
        key = (subject.id, source_umo, target_umo)
        stored = await self._store.get_session_bridge_rule_by_direction(
            subject.id, source_umo, target_umo
        )
        if stored is not None and stored.kind == "pair":
            raise ValueError(PAIR_OCCUPIED)
        if stored is not None and stored.kind == "connect":
            row = await self.persist_config_ids(
                stored, source_config_id, target_config_id
            )
            grant = self._grant_from_row(row, subject, context)
            self._index(grant)
            return grant
        listener = (subject.id, source_umo)
        had_connect = listener in self._connect_by_listener
        if not had_connect:
            if self.count_kind(subject.id, "connect") >= max_per_subject:
                raise ValueError("Watch limit exceeded")
            if self.total_kind("connect") >= 1024:
                raise ValueError("Runtime watch limit exceeded")
        occupant = stored
        await self._store.delete_session_bridge_connects_for_listener(
            subject.id, source_umo
        )
        self._drop_connects_for_listener(subject.id, source_umo)
        if occupant is not None:
            await self._delete_row(occupant.rule_id, key)
        row = await self._store.insert_session_bridge_rule(
            subject_id=subject.id,
            source_umo=source_umo,
            target_umo=target_umo,
            source_config_id=source_config_id,
            target_config_id=target_config_id,
            kind="connect",
            expires_at=None,
        )
        grant = self._grant_from_row(row, subject, context)
        self._index(grant)
        return grant

    async def drop_watch(
        self, subject_id: str, source_umo: str, target_umo: str
    ) -> bool:
        key = (subject_id, source_umo, target_umo)
        grant = self._grants.get(key)
        if grant is None or grant.kind != "watch":
            stored = await self._store.get_session_bridge_rule_by_direction(
                subject_id, source_umo, target_umo
            )
            if stored is None or stored.kind != "watch":
                return False
            await self._delete_row(stored.rule_id, key)
            return True
        await self._delete_row(grant.watch.rule_id, key)
        return True

    async def drop_connect(self, subject_id: str, source_umo: str) -> bool:
        grant = self.connect_for(subject_id, source_umo)
        if grant is None:
            rows = await self._store.list_session_bridge_connects_for_listener(
                subject_id, source_umo
            )
            if not rows:
                return False
            for row in rows:
                await self._delete_row(
                    row.rule_id, (row.subject_id, row.source_umo, row.target_umo)
                )
            return True
        await self._delete_row(grant.watch.rule_id, self.store_key(grant.watch))
        return True

    async def delete_rule(self, rule_id: str) -> WatchGrant | None:
        for key, grant in tuple(self._grants.items()):
            if grant.watch.rule_id == rule_id:
                await self._delete_row(rule_id, key)
                return grant
        stored = await self._store.get_session_bridge_rule(rule_id)
        if stored is None:
            return None
        await self._delete_row(
            rule_id, (stored.subject_id, stored.source_umo, stored.target_umo)
        )
        return None

    async def list_stored_rules(self) -> list[SessionBridgeRule]:
        return await self._store.list_session_bridge_rules()

    async def stored_rule(self, rule_id: str) -> SessionBridgeRule | None:
        return await self._store.get_session_bridge_rule(rule_id)

    async def stored_rules_by_subject(self, subject_id: str) -> list[SessionBridgeRule]:
        return await self._store.list_session_bridge_rules_by_subject(subject_id)

    async def stored_rules_touching_config(
        self, config_id: str
    ) -> list[SessionBridgeRule]:
        return await self._store.list_session_bridge_rules_touching_config(config_id)

    async def discard_stored_rule(self, rule_id: str) -> None:
        await self._store.delete_session_bridge_rule(rule_id)

    async def persist_config_ids(
        self,
        row: SessionBridgeRule,
        source_config_id: str,
        target_config_id: str,
    ) -> SessionBridgeRule:
        if (
            row.source_config_id == source_config_id
            and row.target_config_id == target_config_id
        ):
            return row
        updated = await self._store.update_session_bridge_rule(
            row.rule_id,
            source_config_id=source_config_id,
            target_config_id=target_config_id,
        )
        return updated or row

    def index_grant(self, grant: WatchGrant) -> None:
        self._index(grant)

    def grant_from_row(
        self,
        row: SessionBridgeRule,
        subject: Subject,
        context: AuthContext,
    ) -> WatchGrant:
        return self._grant_from_row(row, subject, context)

    def _grant_from_row(
        self,
        row: SessionBridgeRule,
        subject: Subject,
        context: AuthContext,
    ) -> WatchGrant:
        expires_at = None if row.expires_at is None else float(row.expires_at)
        watch = SessionWatch(
            row.source_umo,
            row.target_umo,
            row.subject_id,
            expires_at,
            row.rule_id,
        )
        return WatchGrant(
            watch,
            subject,
            context,
            row.kind,
            row.source_config_id,
            row.target_config_id,
        )

    def _index(self, grant: WatchGrant) -> None:
        key = self.store_key(grant.watch)
        self._grants[key] = grant
        listener = (grant.watch.subject_id, grant.watch.source_umo)
        if grant.kind == "connect":
            previous_key = self._connect_by_listener.get(listener)
            if previous_key is not None and previous_key != key:
                self._drop_memory(previous_key)
            self._connect_by_listener[listener] = key
        elif self._connect_by_listener.get(listener) == key:
            self._connect_by_listener.pop(listener, None)

    def _drop_memory(self, key: GrantKey) -> WatchGrant | None:
        grant = self._grants.pop(key, None)
        listener = key[:2]
        if self._connect_by_listener.get(listener) == key:
            self._connect_by_listener.pop(listener, None)
        return grant

    def _drop_connects_for_listener(self, subject_id: str, source_umo: str) -> None:
        listener = (subject_id, source_umo)
        key = self._connect_by_listener.pop(listener, None)
        if key is not None:
            self._grants.pop(key, None)
        for grant_key, grant in tuple(self._grants.items()):
            if (
                grant.kind == "connect"
                and grant.watch.subject_id == subject_id
                and grant.watch.source_umo == source_umo
            ):
                self._grants.pop(grant_key, None)

    async def _delete_row(self, rule_id: str, key: GrantKey) -> None:
        await self._store.delete_session_bridge_rule(rule_id)
        self._drop_memory(key)
        task = self._expiry_tasks.pop(key, None)
        current = asyncio.current_task()
        if task is not None and task is not current:
            task.cancel()
