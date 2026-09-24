"""Runtime-owned, authorized subscriptions between message sessions."""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from time import time
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.auth.models import (
    AuthContext,
    AuthorizationValueError,
    Resource,
    Role,
    Subject,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.session_lock import SessionLockManager

from .message_delivery import plan_message_delivery
from .message_i18n import DEFAULT_LOCALE, localize, localize_kind, normalize_locale
from .message_media import materialize_message_media
from .message_projection import envelope_from_send_event
from .message_protocol import (
    ContentKind,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    PortablePart,
)
from .message_renderers import render_source_header
from .message_session import MessageSession
from .send_result import DeliveryAttempt, DeliveryReceipt, PlatformSendResult
from .session_bridge_filter import (
    FILTER_SIDES,
    append_filter_value,
    coerce_filter_side,
    compact_filter_side,
    evaluate_filter,
    has_filter_constraints,
    portable_text,
    validate_filter_value,
)
from .session_bridge_state import (
    PAIR_AMBIGUOUS,
    PAIR_OCCUPIED,
    PAIR_UNLINK_REFUSED,
    GrantKey,
    SessionBridgeState,
    SessionWatch,
    WatchGrant,
    incomplete_pair_rule_ids,
)

MIN_WATCH_TTL_SECONDS = 1
DEFAULT_WATCH_TTL_SECONDS = 12 * 60 * 60
MAX_WATCH_TTL_SECONDS = 10 * 24 * 60 * 60
DEFAULT_MAX_PAIRS_PER_SUBJECT = 8
MAX_FORWARD_ATTEMPTS = 3
FORWARD_RETRY_DELAY_SECONDS = 0.25
MAX_DELIVERIES_KEPT = 8192
DELIVERY_RETENTION_SECONDS = 3 * 24 * 60 * 60
MAX_RULE_ERRORS_KEPT = 64


@dataclass(frozen=True, slots=True)
class SessionBridgeQuota:
    """Live usage and configured cap for one session-bridge kind."""

    current: int
    limit: int


@dataclass(frozen=True, slots=True)
class SessionBridgeRuleHealth:
    """Bounded last-error record for one failing session-bridge rule."""

    rule_id: str
    source_umo: str
    target_umo: str
    failures: int
    last_status: str
    last_error: str
    last_error_at: float


@dataclass(frozen=True, slots=True)
class SessionBridgeHealth:
    """Read-only snapshot of this runtime's session-bridge forwarding health.

    Counters are cumulative since the manager was created. Per-rule errors are
    bounded so a burst of failures cannot grow memory without limit.
    """

    started_at: float
    accepted: int
    partial: int
    failed: int
    unknown: int
    skipped: int
    skipped_filtered: int
    skipped_duplicate: int
    skipped_inactive: int
    skipped_unavailable: int
    authorization_denied: int
    expiry_notice_failures: int
    ledger_failures: int
    restore_failures: int
    pending_forwards: int
    last_success_at: float | None
    last_error_at: float | None
    rule_errors: tuple[SessionBridgeRuleHealth, ...]


@dataclass(slots=True)
class _DeliveryHealth:
    """Mutable delivery-health accumulator owned by one manager."""

    started_at: float = field(default_factory=time)
    accepted: int = 0
    partial: int = 0
    failed: int = 0
    unknown: int = 0
    skipped: int = 0
    skipped_filtered: int = 0
    skipped_duplicate: int = 0
    skipped_inactive: int = 0
    skipped_unavailable: int = 0
    authorization_denied: int = 0
    expiry_notice_failures: int = 0
    ledger_failures: int = 0
    restore_failures: int = 0
    last_success_at: float | None = None
    last_error_at: float | None = None
    rule_errors: OrderedDict[str, SessionBridgeRuleHealth] = field(
        default_factory=OrderedDict
    )


@dataclass(frozen=True, slots=True)
class _EdgeJob:
    """One queued forward for a single origin→listener bridge edge."""

    key: GrantKey
    envelope: MessageEnvelope
    done: asyncio.Future[None]


if TYPE_CHECKING:
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.db.po.session_bridge import SessionBridgeRule
    from astrbot.core.db.protocols import SessionBridgeStore
    from astrbot.core.file_token_service import FileTokenService

    from .astr_message_event import AstrMessageEvent


class SessionBridgeManager:
    """Manage bounded watches, rechecking authority before every delivery."""

    def __init__(
        self,
        send_message: Callable[
            [MessageSession, MessageChain], Awaitable[PlatformSendResult]
        ],
        get_capabilities: Callable[[str], MessageDeliveryCapabilities],
        *,
        authorization: AuthorizationService | None = None,
        get_config_id: Callable[[str], str] | None = None,
        file_token_service: FileTokenService | None = None,
        get_callback_base: Callable[[str], str] | None = None,
        get_locale: Callable[[str], Awaitable[str]] | None = None,
        get_platform_family: Callable[[str], str] | None = None,
        get_self_id: Callable[[str], str | None] | None = None,
        store: SessionBridgeStore,
        default_ttl_seconds: int = DEFAULT_WATCH_TTL_SECONDS,
        max_watches_per_subject: int = 16,
        max_pairs_per_subject: int = DEFAULT_MAX_PAIRS_PER_SUBJECT,
    ) -> None:
        self._send_message = send_message
        self._get_capabilities = get_capabilities
        self._authorization = authorization
        self._get_config_id = get_config_id
        self._file_token_service = file_token_service
        self._get_callback_base = get_callback_base
        self._get_locale = get_locale
        self._get_platform_family = get_platform_family
        self._get_self_id = get_self_id
        self._default_ttl_seconds = min(
            MAX_WATCH_TTL_SECONDS, max(MIN_WATCH_TTL_SECONDS, default_ttl_seconds)
        )
        self._max_watches_per_subject = max(1, max_watches_per_subject)
        self._max_pairs_per_subject = max(1, max_pairs_per_subject)
        self._state = SessionBridgeState(store)
        self._forwarded: OrderedDict[tuple[str, str, str], None] = OrderedDict()
        self._message_ids: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self._lock = asyncio.Lock()
        self._delivery_locks = SessionLockManager()
        self._edge_queues: dict[tuple[str, str], asyncio.Queue[_EdgeJob]] = {}
        self._edge_workers: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._health = _DeliveryHealth()

    @staticmethod
    def _actor(event: AstrMessageEvent) -> tuple[Subject, AuthContext]:
        if event.subject is None or event.auth_context is None:
            raise PermissionError("Authorization context is unavailable")
        if event.subject.id != event.auth_context.subject.id:
            raise PermissionError("Authorization subject mismatch")
        return event.subject, replace(event.auth_context, metadata={})

    async def _authorize(
        self, subject: Subject, context: AuthContext, umo: str, action: str
    ) -> None:
        session = MessageSession.from_str(umo)
        if not session.platform_id or not session.session_id:
            raise ValueError("Invalid session origin")
        if self._authorization is None or self._get_config_id is None:
            raise PermissionError("Authorization context is unavailable")
        config_id = self._get_config_id(umo)
        resource = Resource.session(config_id, umo)
        decision = await self._authorization.authorize(
            subject, action, resource, context
        )
        if not decision.allowed:
            raise PermissionError("Session operation is not authorized")

    def _config_id(self, umo: str) -> str:
        if self._get_config_id is None:
            raise PermissionError("Authorization context is unavailable")
        return self._get_config_id(umo)

    def _ttl_seconds(self, ttl_seconds: int | None) -> int:
        if ttl_seconds is None:
            return self._default_ttl_seconds
        ttl = int(ttl_seconds)
        if ttl < MIN_WATCH_TTL_SECONDS or ttl > MAX_WATCH_TTL_SECONDS:
            raise ValueError("Invalid watch duration")
        return ttl

    async def watch(
        self,
        event: AstrMessageEvent,
        target_umo: str,
        *,
        source_umo: str | None = None,
        ttl_seconds: int | None = None,
    ) -> SessionWatch:
        """Create a watch after checking both sessions using the trusted actor."""
        listener = (source_umo or event.unified_msg_origin).strip()
        target = target_umo.strip()
        if listener == target:
            raise ValueError("Source and target sessions must differ")
        ttl = self._ttl_seconds(ttl_seconds)
        subject, context = self._actor(event)
        await self._authorize(subject, context, listener, "session.watch")
        await self._authorize(subject, context, target, "session.watch")
        if not self._get_capabilities(target).available:
            raise ValueError("Target adapter is unavailable")
        if not self._get_capabilities(listener).proactive:
            raise ValueError("Source adapter cannot receive forwarded messages")
        now = time()
        key = (subject.id, listener, target)
        async with self._lock:
            expired = await self._state.purge(now)
            grant = await self._state.save_watch(
                subject=subject,
                context=context,
                source_umo=listener,
                target_umo=target,
                source_config_id=self._config_id(listener),
                target_config_id=self._config_id(target),
                expires_at=math.ceil(now + ttl),
                max_per_subject=self._max_watches_per_subject,
            )
            self._state.arm_expiry(key, grant, self._expire_watch)
        await self._notify_expired_watches(expired)
        return grant.watch

    async def unwatch(
        self,
        event: AstrMessageEvent,
        target_umo: str,
        *,
        source_umo: str | None = None,
    ) -> bool:
        """Allow a trusted owner to cancel even after their role is revoked."""
        subject, _ = self._actor(event)
        listener = (source_umo or event.unified_msg_origin).strip()
        key = (subject.id, listener, target_umo.strip())
        async with self._lock:
            return await self._state.drop_watch(subject.id, key[1], key[2])

    async def list_watches(
        self,
        event: AstrMessageEvent,
        *,
        source_umo: str | None = None,
    ) -> tuple[SessionWatch, ...]:
        subject, _ = self._actor(event)
        listener = (source_umo or event.unified_msg_origin).strip()
        async with self._lock:
            expired = await self._state.purge(time())
            items = self._state.watches_for(subject.id, listener)
        await self._notify_expired_watches(expired)
        return items

    async def connect(
        self,
        event: AstrMessageEvent,
        target_umo: str,
    ) -> SessionWatch:
        """Create an unbounded 1:1 link from the current session to the target."""
        listener = event.unified_msg_origin.strip()
        target = target_umo.strip()
        if listener == target:
            raise ValueError("Source and target sessions must differ")
        subject, context = self._actor(event)
        await self._authorize(subject, context, listener, "session.watch")
        await self._authorize(subject, context, target, "session.watch")
        if not self._get_capabilities(target).available:
            raise ValueError("Target adapter is unavailable")
        if not self._get_capabilities(listener).proactive:
            raise ValueError("Source adapter cannot receive forwarded messages")
        async with self._lock:
            grant = await self._state.save_connect(
                subject=subject,
                context=context,
                source_umo=listener,
                target_umo=target,
                source_config_id=self._config_id(listener),
                target_config_id=self._config_id(target),
                max_per_subject=self._max_watches_per_subject,
            )
        return grant.watch

    async def disconnect(self, event: AstrMessageEvent) -> bool:
        """Remove the unbounded link owned by the current actor in this session."""
        subject, _ = self._actor(event)
        listener = event.unified_msg_origin.strip()
        async with self._lock:
            return await self._state.drop_connect(subject.id, listener)

    async def connection(self, event: AstrMessageEvent) -> SessionWatch | None:
        """Return the unbounded link for the current actor in this session."""
        subject, _ = self._actor(event)
        listener = event.unified_msg_origin.strip()
        async with self._lock:
            grant = self._state.connect_for(subject.id, listener)
        return grant.watch if grant is not None else None

    async def quota_usage(
        self, event: AstrMessageEvent
    ) -> dict[str, SessionBridgeQuota]:
        """Return per-kind usage and cap for the event's trusted subject."""
        subject, _ = self._actor(event)
        async with self._lock:
            return {
                "watch": SessionBridgeQuota(
                    self._state.count_kind(subject.id, "watch"),
                    self._max_watches_per_subject,
                ),
                "connect": SessionBridgeQuota(
                    self._state.count_kind(subject.id, "connect"),
                    self._max_watches_per_subject,
                ),
                "pair": SessionBridgeQuota(
                    self._state.count_pairs(subject.id),
                    self._max_pairs_per_subject,
                ),
            }

    def _note_skip(self, reason: str) -> None:
        """Count one forwarding that was intentionally not delivered."""
        state = self._health
        state.skipped += 1
        if reason == "filtered":
            state.skipped_filtered += 1
        elif reason == "duplicate":
            state.skipped_duplicate += 1
        elif reason == "inactive":
            state.skipped_inactive += 1
        elif reason == "unavailable":
            state.skipped_unavailable += 1

    def _note_rule_error(
        self,
        watch: SessionWatch,
        status: str,
        summary: str,
        *,
        now: float | None = None,
    ) -> None:
        """Record a bounded, most-recent-first error for one rule."""
        state = self._health
        at = time() if now is None else now
        state.last_error_at = at
        previous = state.rule_errors.pop(watch.rule_id, None)
        state.rule_errors[watch.rule_id] = SessionBridgeRuleHealth(
            rule_id=watch.rule_id,
            source_umo=watch.source_umo,
            target_umo=watch.target_umo,
            failures=(previous.failures if previous is not None else 0) + 1,
            last_status=status,
            last_error=summary,
            last_error_at=at,
        )
        while len(state.rule_errors) > MAX_RULE_ERRORS_KEPT:
            state.rule_errors.popitem(last=False)

    def _note_delivery(self, watch: SessionWatch, receipt: DeliveryReceipt) -> None:
        """Count one completed delivery outcome and its per-rule failure."""
        state = self._health
        now = time()
        status = receipt.status
        if status == "accepted":
            state.accepted += 1
            state.last_success_at = now
            return
        if status == "partial":
            state.partial += 1
        elif status == "failed":
            state.failed += 1
        elif status == "unknown":
            state.unknown += 1
        else:
            state.skipped += 1
        if status in {"partial", "failed", "unknown"}:
            self._note_rule_error(
                watch, status, receipt.error_summary or f"Delivery {status}"
            )

    def _note_unexpected_failure(self) -> None:
        """Count an edge worker failure that carried no usable rule record."""
        self._health.failed += 1
        self._health.last_error_at = time()

    def health(self) -> SessionBridgeHealth:
        """Return a read-only snapshot of this manager's delivery health."""
        state = self._health
        return SessionBridgeHealth(
            started_at=state.started_at,
            accepted=state.accepted,
            partial=state.partial,
            failed=state.failed,
            unknown=state.unknown,
            skipped=state.skipped,
            skipped_filtered=state.skipped_filtered,
            skipped_duplicate=state.skipped_duplicate,
            skipped_inactive=state.skipped_inactive,
            skipped_unavailable=state.skipped_unavailable,
            authorization_denied=state.authorization_denied,
            expiry_notice_failures=state.expiry_notice_failures,
            ledger_failures=state.ledger_failures,
            restore_failures=state.restore_failures,
            pending_forwards=sum(queue.qsize() for queue in self._edge_queues.values()),
            last_success_at=state.last_success_at,
            last_error_at=state.last_error_at,
            rule_errors=tuple(state.rule_errors.values()),
        )

    async def health_for(self, event: AstrMessageEvent) -> SessionBridgeHealth:
        """Return health with per-rule errors limited to visible rules."""
        visible = await self.list_links(event)
        visible_ids = {watch.rule_id for watch, _ in visible}
        snapshot = self.health()
        return replace(
            snapshot,
            rule_errors=tuple(
                item for item in snapshot.rule_errors if item.rule_id in visible_ids
            ),
        )

    def _require_loaded_proactive(self, umo: str) -> None:
        capabilities = self._get_capabilities(umo)
        if not capabilities.available:
            raise ValueError("Target adapter is unavailable")
        if not capabilities.proactive:
            raise ValueError("Source adapter cannot receive forwarded messages")

    async def pair(
        self, event: AstrMessageEvent, target_umo: str
    ) -> tuple[SessionWatch, SessionWatch]:
        """Create two reverse edges between the current session and target."""
        listener = event.unified_msg_origin.strip()
        target = target_umo.strip()
        if listener == target:
            raise ValueError("Source and target sessions must differ")
        subject, context = self._actor(event)
        await self._authorize(subject, context, listener, "session.watch")
        await self._authorize(subject, context, target, "session.watch")
        self._require_loaded_proactive(listener)
        self._require_loaded_proactive(target)
        async with self._lock:
            left, right = await self._state.save_pair(
                subject=subject,
                context=context,
                source_umo=listener,
                target_umo=target,
                source_config_id=self._config_id(listener),
                target_config_id=self._config_id(target),
                max_pairs_per_subject=self._max_pairs_per_subject,
            )
        return left.watch, right.watch

    async def unpair(
        self, event: AstrMessageEvent, target_umo: str | None = None
    ) -> bool:
        """Remove both edges that share a pair id owned by the current actor."""
        subject, _ = self._actor(event)
        listener = event.unified_msg_origin.strip()
        target = None if target_umo is None else target_umo.strip()
        async with self._lock:
            pair_id = await self._pair_id_for_unpair(subject.id, listener, target)
            if pair_id is None:
                return False
            return await self._state.drop_pair(subject.id, pair_id)

    async def _pair_id_for_unpair(
        self, subject_id: str, listener: str, target: str | None
    ) -> str | None:
        if target:
            row = await self._state.stored_rule_by_direction(
                subject_id, listener, target
            )
            if row is None:
                row = await self._state.stored_rule_by_direction(
                    subject_id, target, listener
                )
            if row is None or row.kind != "pair" or not row.pair_id:
                return None
            return row.pair_id
        rows = [
            row
            for row in await self._state.stored_rules_by_subject(subject_id)
            if row.kind == "pair"
            and row.pair_id
            and listener in {row.source_umo, row.target_umo}
        ]
        pair_ids = list(dict.fromkeys(row.pair_id for row in rows if row.pair_id))
        if not pair_ids:
            return None
        if len(pair_ids) > 1:
            raise ValueError(PAIR_AMBIGUOUS)
        return pair_ids[0]

    async def list_links(
        self, event: AstrMessageEvent
    ) -> tuple[tuple[SessionWatch, str], ...]:
        """List watch, connect, and pair edges visible to the current actor."""
        subject, _ = self._actor(event)
        role = await self._operator_role(event)
        current_config = self._config_id(event.unified_msg_origin)
        now = time()
        async with self._lock:
            expired = await self._state.purge(now)
        await self._notify_expired_watches(expired)
        own = await self._state.stored_rules_by_subject(subject.id)
        if role in {Role.ROOT, Role.OPERATOR}:
            rows = await self._state.list_stored_rules()
        elif role is Role.INSTANCE_OPERATOR:
            extra = await self._state.stored_rules_touching_config(current_config)
            merged = {row.rule_id: row for row in own}
            merged.update({row.rule_id: row for row in extra})
            rows = list(merged.values())
        else:
            rows = own
        items: list[tuple[SessionWatch, str]] = []
        for row in rows:
            if row.kind not in {"watch", "connect", "pair"}:
                continue
            if (
                row.kind == "watch"
                and row.expires_at is not None
                and row.expires_at <= now
            ):
                continue
            items.append((self._watch_from_row(row), row.kind))
        return tuple(items)

    async def unlink(self, event: AstrMessageEvent, rule_id: str) -> bool:
        """Remove a watch or connect by public id under creator or operator rules."""
        subject, _ = self._actor(event)
        stored = await self._state.stored_rule(rule_id)
        if stored is None or stored.kind == "pair":
            if stored is not None:
                raise ValueError(PAIR_UNLINK_REFUSED)
            return False
        if stored.subject_id != subject.id:
            role = await self._operator_role(event)
            current_config = self._config_id(event.unified_msg_origin)
            allowed = role in {Role.ROOT, Role.OPERATOR} or (
                role is Role.INSTANCE_OPERATOR
                and current_config in {stored.source_config_id, stored.target_config_id}
            )
            if not allowed:
                raise PermissionError("Session operation is not authorized")
        async with self._lock:
            await self._state.delete_rule(rule_id)
        return True

    async def get_filter(
        self, event: AstrMessageEvent, rule_id: str
    ) -> tuple[dict, dict] | None:
        """Return match/except for a rule visible like ``list_links``."""
        row = await self._accessible_rule(event, rule_id)
        if row is None:
            return None
        return coerce_filter_side(row.match), coerce_filter_side(row.except_)

    async def append_filter(
        self,
        event: AstrMessageEvent,
        rule_id: str,
        side: str,
        dimension: str,
        value: str,
    ) -> tuple[dict, dict] | None:
        """Append one match or except value onto a directed edge."""
        stored = validate_filter_value(dimension, value)
        if side not in FILTER_SIDES:
            raise ValueError("Invalid filter arguments")
        if await self._accessible_rule(event, rule_id) is None:
            return None
        async with self._lock:
            fresh = await self._state.stored_rule(rule_id)
            if fresh is None:
                return None
            match = coerce_filter_side(fresh.match)
            except_ = coerce_filter_side(fresh.except_)
            if side == "match":
                match = append_filter_value(match, dimension, stored)
            else:
                except_ = append_filter_value(except_, dimension, stored)
            return await self._commit_filters(fresh, match, except_)

    async def clear_filter(
        self, event: AstrMessageEvent, rule_id: str, side: str
    ) -> tuple[dict, dict] | None:
        """Clear match, except, or both sides of one edge."""
        if side not in {*FILTER_SIDES, "all"}:
            raise ValueError("Invalid filter arguments")
        if await self._accessible_rule(event, rule_id) is None:
            return None
        async with self._lock:
            fresh = await self._state.stored_rule(rule_id)
            if fresh is None:
                return None
            match = coerce_filter_side(fresh.match)
            except_ = coerce_filter_side(fresh.except_)
            if side in {"match", "all"}:
                match = {}
            if side in {"except", "all"}:
                except_ = {}
            return await self._commit_filters(fresh, match, except_)

    async def _accessible_rule(
        self, event: AstrMessageEvent, rule_id: str
    ) -> SessionBridgeRule | None:
        stored = await self._state.stored_rule(rule_id)
        if stored is None:
            return None
        subject, _ = self._actor(event)
        if stored.subject_id == subject.id:
            return stored
        role = await self._operator_role(event)
        current_config = self._config_id(event.unified_msg_origin)
        allowed = role in {Role.ROOT, Role.OPERATOR} or (
            role is Role.INSTANCE_OPERATOR
            and current_config in {stored.source_config_id, stored.target_config_id}
        )
        if not allowed:
            raise PermissionError("Session operation is not authorized")
        return stored

    async def _commit_filters(
        self,
        row: SessionBridgeRule,
        match: dict,
        except_: dict,
    ) -> tuple[dict, dict] | None:
        """Write compacted filters. Caller must hold ``self._lock``."""
        match = compact_filter_side(match)
        except_ = compact_filter_side(except_)
        updated = await self._state.persist_filters(row.rule_id, match, except_)
        if updated is None:
            return None
        grant = self._state.refresh_grant_filters(updated, match, except_)
        if grant is not None:
            self._state.arm_expiry(
                self._state.store_key(grant.watch), grant, self._expire_watch
            )
        return match, except_

    def _watch_from_row(self, row: SessionBridgeRule) -> SessionWatch:
        expires_at = None if row.expires_at is None else float(row.expires_at)
        return SessionWatch(
            row.source_umo,
            row.target_umo,
            row.subject_id,
            expires_at,
            row.rule_id,
            row.pair_id,
        )

    async def _operator_role(self, event: AstrMessageEvent) -> Role | None:
        if self._authorization is None:
            return None
        subject, context = self._actor(event)
        umo = event.unified_msg_origin.strip()
        decision = await self._authorization.authorize(
            subject,
            "session.watch",
            Resource.session(self._config_id(umo), umo),
            context,
        )
        if not decision.allowed:
            return None
        return decision.effective_role

    async def send(
        self,
        event: AstrMessageEvent,
        target_umo: str,
        *,
        target_in_header: bool = True,
    ) -> DeliveryReceipt:
        """Send the command's ordered rich content under target authorization."""
        subject, context = self._actor(event)
        await self._authorize(
            subject, context, event.unified_msg_origin, "session.send"
        )
        await self._authorize(subject, context, target_umo, "session.send")
        if not self._get_capabilities(target_umo).proactive:
            raise ValueError("Target adapter does not support proactive delivery")
        envelope = envelope_from_send_event(
            event, target_umo, target_in_header=target_in_header
        )
        if not envelope.content:
            raise ValueError("A message or attachment is required")

        async def check_authority() -> None:
            await self._authorize(
                subject, context, event.unified_msg_origin, "session.send"
            )
            await self._authorize(subject, context, target_umo, "session.send")

        return await self._deliver(
            target_umo,
            envelope,
            check_authority,
            locale=await self._locale_for(target_umo),
        )

    def _store_key(self, watch: SessionWatch) -> GrantKey:
        return self._state.store_key(watch)

    def _grant_active(self, key: GrantKey, grant: WatchGrant, now: float) -> bool:
        return self._state.grant_active(key, grant, now)

    async def _check_watch(self, grant: WatchGrant) -> None:
        watch = grant.watch
        key = self._store_key(watch)
        if not self._grant_active(key, grant, time()):
            raise PermissionError("Watch is no longer active")
        await self._authorize(
            grant.subject, grant.context, watch.source_umo, "session.watch"
        )
        await self._authorize(
            grant.subject, grant.context, watch.target_umo, "session.watch"
        )

    async def observe(self, envelope: MessageEnvelope) -> None:
        """Forward ingress snapshots, removing expired or revoked watches.

        Jobs are enqueued on a per-edge FIFO before the first ``await`` so
        arrival order is pinned: a later ingress task cannot overtake an earlier
        one while asynchronous authorization or filter work runs.
        """
        if envelope.is_self_message:
            return
        origin = envelope.source_umo
        # The snapshot is read before any await, so no other coroutine can
        # mutate the grant index during this synchronous span.
        watches = self._state.grants_observing(origin)
        pending = self._enqueue_edge_jobs(origin, watches, envelope)
        async with self._lock:
            expired = await self._state.purge(time())
        await self._notify_expired_watches(expired)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _enqueue_edge_jobs(
        self,
        origin: str,
        watches: tuple[tuple[GrantKey, WatchGrant], ...],
        envelope: MessageEnvelope,
    ) -> list[asyncio.Future[None]]:
        """Queue one job per edge in synchronous arrival order."""
        loop = asyncio.get_running_loop()
        pending: list[asyncio.Future[None]] = []
        for key, grant in watches:
            queue = self._edge_queue((origin, grant.watch.source_umo))
            done: asyncio.Future[None] = loop.create_future()
            queue.put_nowait(_EdgeJob(key, envelope, done))
            pending.append(done)
        return pending

    def _edge_queue(self, edge: tuple[str, str]) -> asyncio.Queue[_EdgeJob]:
        """Return the live FIFO for one edge, starting its worker on demand."""
        worker = self._edge_workers.get(edge)
        if worker is not None and not worker.done():
            return self._edge_queues[edge]
        queue: asyncio.Queue[_EdgeJob] = asyncio.Queue()
        task = asyncio.get_running_loop().create_task(
            self._drain_edge(edge, queue),
            name=f"session-bridge-edge:{edge[0]}->{edge[1]}",
        )
        self._edge_queues[edge] = queue
        self._edge_workers[edge] = task
        return queue

    async def _drain_edge(
        self, edge: tuple[str, str], queue: asyncio.Queue[_EdgeJob]
    ) -> None:
        """Deliver one edge's queued jobs in order, then retire when idle."""
        try:
            while True:
                job = await queue.get()
                try:
                    grant = self._state.get(job.key)
                    if grant is not None:
                        await self._forward_to_watch(job.key, grant, job.envelope)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._note_unexpected_failure()
                    logger.warning("Session bridge delivery failed")
                finally:
                    if not job.done.done():
                        job.done.set_result(None)
                    queue.task_done()
                if queue.empty():
                    break
        finally:
            while not queue.empty():
                queued = queue.get_nowait()
                if not queued.done.done():
                    queued.done.cancel()
            if self._edge_queues.get(edge) is queue:
                self._edge_queues.pop(edge, None)
                self._edge_workers.pop(edge, None)

    async def _forward_to_watch(
        self, key: GrantKey, grant: WatchGrant, envelope: MessageEnvelope
    ) -> None:
        """Deliver one envelope to one watch, leasing the dedup key for it."""
        watch = grant.watch
        origin = envelope.source_umo
        claim: tuple[str, str, str] | None = None
        try:
            if not self._get_capabilities(watch.source_umo).available:
                self._note_skip("unavailable")
                return
            await self._authorize(
                grant.subject, grant.context, watch.source_umo, "session.watch"
            )
            await self._authorize(
                grant.subject, grant.context, watch.target_umo, "session.watch"
            )
            if not await self._passes_filter(grant, envelope):
                self._note_skip("filtered")
                return
            async with self._lock:
                if not self._grant_active(key, grant, time()):
                    self._note_skip("inactive")
                    return
                if envelope.source_message_id:
                    claim = (watch.source_umo, origin, envelope.source_message_id)
                    if claim in self._forwarded:
                        self._note_skip("duplicate")
                        return
                    self._forwarded[claim] = None
                    if len(self._forwarded) > 8192:
                        self._forwarded.popitem(last=False)
            locale = await self._locale_for(watch.source_umo)
            content = (
                PortablePart(
                    ContentKind.TEXT,
                    render_source_header(
                        envelope,
                        self._platform_family(watch.source_umo),
                        locale,
                    ),
                ),
                *envelope.content,
            )
            forwarded = replace(envelope, content=content)
            receipt = await self._forward_with_retry(watch, grant, forwarded, locale)
            if not receipt.accepted_attempts:
                await self._release_forward(claim)
            elif claim is not None:
                # The claim becomes a durable delivery record so the dedup
                # key survives a restart even when the platform returns no
                # message id; a returned id also restores quote resolution.
                dest_message_id = (
                    receipt.message_ids[0] if receipt.message_ids else None
                )
                await self._persist_delivery(claim, dest_message_id)
            self._note_delivery(watch, receipt)
            if receipt.status != "accepted":
                logger.warning("Session bridge submission status: %s", receipt.status)
        except PermissionError:
            self._health.authorization_denied += 1
            self._note_rule_error(watch, "denied", "Authorization revoked")
            await self._release_forward(claim)
            async with self._lock:
                await self._state.delete_rule(grant.watch.rule_id)
        except asyncio.CancelledError:
            await self._release_forward(claim)
            raise
        except Exception:
            # Transport exceptions may contain credentials or private URLs.
            self._health.failed += 1
            self._note_rule_error(watch, "failed", "Delivery failed")
            await self._release_forward(claim)
            logger.warning("Session bridge delivery failed")

    async def _forward_with_retry(
        self,
        watch: SessionWatch,
        grant: WatchGrant,
        envelope: MessageEnvelope,
        locale: str,
    ) -> DeliveryReceipt:
        """Retry transient platform failures without duplicating the claim."""
        receipt = await self._deliver(
            watch.source_umo,
            envelope,
            lambda: self._check_watch(grant),
            locale=locale,
        )
        attempt = 1
        while (
            attempt < MAX_FORWARD_ATTEMPTS
            and not receipt.accepted_attempts
            and receipt.status in {"failed", "unknown"}
        ):
            await asyncio.sleep(FORWARD_RETRY_DELAY_SECONDS * attempt)
            receipt = await self._deliver(
                watch.source_umo,
                envelope,
                lambda: self._check_watch(grant),
                locale=locale,
            )
            attempt += 1
        return receipt

    async def _release_forward(self, claim: tuple[str, str, str] | None) -> None:
        """Drop an undelivered dedup claim so a later observe can retry."""
        if claim is None:
            return
        async with self._lock:
            self._forwarded.pop(claim, None)

    async def _persist_delivery(
        self, claim: tuple[str, str, str], dest_message_id: str | None
    ) -> None:
        """Write one successful delivery to the durable ledger.

        A ledger failure must never turn an accepted delivery into an error:
        only the in-memory dedup and quote maps decide live behavior.
        """
        dest_umo, origin, source_message_id = claim
        try:
            await self._state.store.insert_session_bridge_delivery(
                dest_umo=dest_umo,
                origin_umo=origin,
                source_message_id=source_message_id,
                dest_message_id=dest_message_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._health.ledger_failures += 1
            logger.warning("Session bridge delivery ledger write failed")

    async def _passes_filter(
        self, grant: WatchGrant, envelope: MessageEnvelope
    ) -> bool:
        match = coerce_filter_side(grant.match)
        except_ = coerce_filter_side(grant.except_)
        if not has_filter_constraints(match) and not has_filter_constraints(except_):
            return True
        needs_subjects = bool(match.get("subjects") or except_.get("subjects"))
        needs_roles = bool(match.get("roles") or except_.get("roles"))
        subject_id = self._sender_subject_id(envelope) if needs_subjects else None
        role = Role.GUEST.value
        if needs_roles:
            role = (await self._sender_role(envelope)).value
        return evaluate_filter(
            match,
            except_,
            subject_id=subject_id,
            has_sender=envelope.sender is not None,
            role=role,
            text=portable_text(envelope.content),
        )

    def _bot_account_id(self, envelope: MessageEnvelope) -> str:
        metadata_id = envelope.metadata.get("bot_account_id")
        if isinstance(metadata_id, str) and metadata_id:
            return metadata_id
        if self._get_self_id is None:
            return ""
        return self._get_self_id(envelope.source_route.platform_id) or ""

    def _sender_subject_id(self, envelope: MessageEnvelope) -> str | None:
        if envelope.sender is None:
            return None
        bot_account_id = self._bot_account_id(envelope)
        if not bot_account_id:
            return None
        try:
            return Subject.im(
                platform_instance=envelope.source_route.platform_id,
                bot_account_id=bot_account_id,
                sender_id=envelope.sender.id,
            ).id
        except AuthorizationValueError, ValueError:
            return None

    async def _sender_role(self, envelope: MessageEnvelope) -> Role:
        subject_id = self._sender_subject_id(envelope)
        if (
            subject_id is None
            or self._authorization is None
            or self._get_config_id is None
        ):
            return Role.GUEST
        try:
            subject = Subject.from_id(subject_id)
            origin = envelope.source_umo
            config_id = self._config_id(origin)
            resource = Resource.session(config_id, origin)
            context = AuthContext(
                subject=subject,
                source="im",
                config_id=config_id,
                authenticated=True,
                origin_session_resource_id=resource.id,
            )
            decision = await self._authorization.authorize(
                subject, "session.read", resource, context
            )
        except AuthorizationValueError, PermissionError, ValueError:
            return Role.GUEST
        except asyncio.CancelledError:
            raise
        except Exception:
            return Role.GUEST
        return decision.effective_role or Role.GUEST

    def _platform_family(self, umo: str) -> str:
        if self._get_platform_family is None:
            return umo.split(":", 1)[0]
        return self._get_platform_family(umo)

    async def _locale_for(self, umo: str) -> str:
        if self._get_locale is None:
            return DEFAULT_LOCALE
        try:
            return normalize_locale(await self._get_locale(umo))
        except asyncio.CancelledError:
            raise
        except Exception:
            return DEFAULT_LOCALE

    async def _deliver(
        self,
        target_umo: str,
        envelope: MessageEnvelope,
        check_authority: Callable[[], Awaitable[None]],
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> DeliveryReceipt:
        """Serialize delivery per destination while other targets stay parallel.

        The destination lock is held across media materialization so per-target
        arrival order is preserved; unrelated destinations never wait on it.
        """
        async with self._delivery_locks.acquire_lock(target_umo):
            await check_authority()
            return await self._materialize_and_submit(
                target_umo, envelope, check_authority, locale=locale
            )

    async def _materialize_and_submit(
        self,
        target_umo: str,
        envelope: MessageEnvelope,
        check_authority: Callable[[], Awaitable[None]],
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> DeliveryReceipt:
        session = MessageSession.from_str(target_umo)
        capabilities = self._get_capabilities(target_umo)
        if not capabilities.proactive:
            return DeliveryReceipt.aggregate(
                [DeliveryAttempt(status="failed")],
                platform_id=session.platform_id,
                target=target_umo,
            )
        async with materialize_message_media(
            envelope, capabilities, locale=locale
        ) as materialized:
            if capabilities.public_media_urls:
                materialized = await self._publish_media(
                    target_umo, materialized, locale=locale
                )
            return await self._submit(
                target_umo, materialized, check_authority, locale=locale
            )

    async def _publish_media(
        self,
        target_umo: str,
        envelope: MessageEnvelope,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> MessageEnvelope:
        from .message_protocol import MediaReference

        base = (
            self._get_callback_base(target_umo).rstrip("/")
            if self._get_callback_base
            else ""
        )
        content = []
        for part in envelope.content:
            if isinstance(part, PortablePart) and isinstance(
                part.value, MediaReference
            ):
                if not base.startswith("https://") or self._file_token_service is None:
                    part = PortablePart(
                        ContentKind.TEXT,
                        localize(
                            locale,
                            "astrbot.msg.public_media_unavailable",
                            label=localize_kind(locale, part.kind.value),
                        ),
                    )
                else:
                    token = await self._file_token_service.register_snapshot(
                        part.value.uri
                    )
                    part = replace(
                        part,
                        value=replace(
                            part.value, uri=f"{base}/api/v1/files/tokens/{token}"
                        ),
                    )
            content.append(part)
        return replace(envelope, content=tuple(content))

    async def _resolve_quote_preview(
        self,
        envelope: MessageEnvelope,
    ) -> MessageEnvelope:
        """Fill an unmapped cross-session quote with readable preview text."""
        quote = envelope.quote
        if quote is None or quote.preview or quote.resolve_preview is None:
            return envelope
        try:
            preview = await quote.resolve_preview()
        except Exception:
            return envelope
        if not preview:
            return envelope
        return replace(envelope, quote=replace(quote, preview=preview))

    async def _submit(
        self,
        target_umo: str,
        envelope: MessageEnvelope,
        check_authority: Callable[[], Awaitable[None]],
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> DeliveryReceipt:
        session = MessageSession.from_str(target_umo)
        capabilities = self._get_capabilities(target_umo)
        quote_id = None
        if envelope.quote:
            quote_origin = envelope.quote.source_route.as_origin()
            if quote_origin == target_umo:
                quote_id = envelope.quote.message_id
            else:
                quote_id = self._message_ids.get(
                    (quote_origin, envelope.quote.message_id, target_umo)
                )
        if quote_id is None:
            envelope = await self._resolve_quote_preview(envelope)
        attempts: list[DeliveryAttempt] = []
        for chain in plan_message_delivery(
            envelope,
            capabilities,
            quote_id=quote_id,
            target_umo=target_umo,
            locale=locale,
        ):
            try:
                await check_authority()
            except PermissionError:
                if not attempts:
                    raise
                attempts.append(
                    DeliveryAttempt(
                        status="failed", error_summary="Authorization revoked"
                    )
                )
                break
            try:
                result = await self._send_message(session, chain)
                attempts.extend(
                    result.to_delivery_attempts(semantic_text=chain.get_plain_text())
                )
                if not result.success:
                    break
            except asyncio.CancelledError:
                raise
            except Exception:
                attempts.append(
                    DeliveryAttempt(
                        status="unknown", error_summary="Platform submission failed"
                    )
                )
                break
        receipt = DeliveryReceipt.aggregate(
            attempts, platform_id=session.platform_id, target=target_umo
        )
        if envelope.source_message_id and receipt.message_ids:
            source = envelope.source_route.as_origin()
            self._message_ids[(source, envelope.source_message_id, target_umo)] = (
                receipt.message_ids[0]
            )
            for message_id in receipt.message_ids:
                self._message_ids[(target_umo, message_id, source)] = (
                    envelope.source_message_id
                )
            while len(self._message_ids) > 8192:
                self._message_ids.popitem(last=False)
        return receipt

    async def _expire_watch(self, key: GrantKey, grant: WatchGrant) -> None:
        expires_at = grant.watch.expires_at
        if expires_at is None:
            return
        delay = max(0.0, expires_at - time())
        await asyncio.sleep(delay)
        async with self._lock:
            if self._state.get(key) is not grant:
                return
            await self._state.delete_rule(grant.watch.rule_id)
        await self._notify_expired(grant)

    async def _notify_expired_watches(self, expired: tuple[WatchGrant, ...]) -> None:
        for grant in expired:
            await self._notify_expired(grant)

    async def _notify_expired(self, grant: WatchGrant) -> None:
        locale = await self._locale_for(grant.watch.source_umo)
        text = localize(locale, "astrbot.msg.watch.expired", umo=grant.watch.target_umo)
        try:
            session = MessageSession.from_str(grant.watch.source_umo)
            chain = MessageChain().message(text).use_markdown(False)
            chain.use_t2i_ = False
            await self._send_message(session, chain)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._health.expiry_notice_failures += 1
            logger.warning("Session watch expiry notice failed")

    async def restore(self) -> None:
        """Reload persisted rules and delivery records, dropping stale rows.

        The delivery ledger restores the dedup keys and quote-id map so a
        restart neither duplicates accepted forwards nor breaks reply links.
        """
        await self._restore_deliveries()
        rows = await self._state.list_stored_rules()
        now = time()
        expired: list[WatchGrant] = []
        orphan_ids = incomplete_pair_rule_ids(rows)
        async with self._lock:
            for row in rows:
                if row.rule_id in orphan_ids:
                    await self._state.discard_stored_rule(row.rule_id)
                    continue
                if row.kind not in {"watch", "connect", "pair"}:
                    continue
                if (
                    row.kind == "watch"
                    and row.expires_at is not None
                    and row.expires_at <= now
                ):
                    await self._state.discard_stored_rule(row.rule_id)
                    try:
                        expired.append(self._grant_for_notice(row))
                    except ValueError:
                        logger.warning("Session watch expiry notice skipped")
                    continue
                grant = await self._restore_row(row)
                if grant is None:
                    continue
                if grant.kind == "connect":
                    existing = self._state.connect_for(
                        grant.watch.subject_id, grant.watch.source_umo
                    )
                    if (
                        existing is not None
                        and existing.watch.rule_id != grant.watch.rule_id
                    ):
                        await self._state.delete_rule(existing.watch.rule_id)
                self._state.index_grant(grant)
                self._state.arm_expiry(
                    self._state.store_key(grant.watch), grant, self._expire_watch
                )
        await self._notify_expired_watches(tuple(expired))

    async def _restore_deliveries(self) -> None:
        """Reload recent deliveries and prune stale or beyond-cap rows."""
        try:
            await self._state.store.prune_session_bridge_deliveries(
                keep=MAX_DELIVERIES_KEPT,
                retention_seconds=DELIVERY_RETENTION_SECONDS,
            )
            rows = await self._state.store.list_session_bridge_deliveries(
                MAX_DELIVERIES_KEPT
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._health.ledger_failures += 1
            logger.warning("Session bridge delivery ledger read failed")
            return
        for row in reversed(rows):
            self._forwarded[(row.dest_umo, row.origin_umo, row.source_message_id)] = (
                None
            )
            if row.dest_message_id is None:
                continue
            self._message_ids[(row.origin_umo, row.source_message_id, row.dest_umo)] = (
                row.dest_message_id
            )
            self._message_ids[(row.dest_umo, row.dest_message_id, row.origin_umo)] = (
                row.source_message_id
            )

    def _grant_for_notice(self, row: SessionBridgeRule) -> WatchGrant:
        subject = Subject.from_id(row.subject_id)
        context = AuthContext(subject=subject, source="im", authenticated=True)
        return self._state.grant_from_row(row, subject, context)

    async def _restore_row(self, row: SessionBridgeRule) -> WatchGrant | None:
        try:
            subject = Subject.from_id(row.subject_id)
            source = "webchat" if subject.kind == "dashboard-account" else "im"
            source_config_id = self._config_id(row.source_umo)
            target_config_id = self._config_id(row.target_umo)
            context = AuthContext(
                subject=subject,
                source=source,
                config_id=source_config_id,
                authenticated=True,
                origin_session_resource_id=Resource.session(
                    source_config_id, row.source_umo
                ).id,
            )
            await self._authorize(subject, context, row.source_umo, "session.watch")
            context = AuthContext(
                subject=subject,
                source=source,
                config_id=target_config_id,
                authenticated=True,
                origin_session_resource_id=Resource.session(
                    source_config_id, row.source_umo
                ).id,
            )
            await self._authorize(subject, context, row.target_umo, "session.watch")
            row = await self._state.persist_config_ids(
                row, source_config_id, target_config_id
            )
        except PermissionError, ValueError:
            await self._state.discard_stored_rule(row.rule_id)
            return None
        except Exception:
            self._health.restore_failures += 1
            logger.warning("Session bridge restore skipped a rule")
            return None
        grant_context = AuthContext(
            subject=subject,
            source=source,
            config_id=source_config_id,
            authenticated=True,
            origin_session_resource_id=Resource.session(
                source_config_id, row.source_umo
            ).id,
        )
        return self._state.grant_from_row(row, subject, grant_context)

    async def terminate(self) -> None:
        """Cancel expiry tasks and edge workers, then drop in-memory state.

        The delivery ledger rows survive: rules stay durable on purpose, and
        dropping them would reintroduce the restart issues from issue #245.
        """
        async with self._lock:
            tasks = self._state.take_expiry_tasks()
            self._state.clear_grants()
            self._forwarded.clear()
            self._message_ids.clear()
            for queue in self._edge_queues.values():
                while not queue.empty():
                    job = queue.get_nowait()
                    if not job.done.done():
                        job.done.cancel()
            workers = list(self._edge_workers.values())
            self._edge_queues.clear()
            self._edge_workers.clear()
        pending = [*tasks, *workers]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


__all__ = [
    "DEFAULT_MAX_PAIRS_PER_SUBJECT",
    "DEFAULT_WATCH_TTL_SECONDS",
    "MAX_WATCH_TTL_SECONDS",
    "MIN_WATCH_TTL_SECONDS",
    "PAIR_AMBIGUOUS",
    "PAIR_OCCUPIED",
    "PAIR_UNLINK_REFUSED",
    "SessionBridgeManager",
    "SessionWatch",
]
