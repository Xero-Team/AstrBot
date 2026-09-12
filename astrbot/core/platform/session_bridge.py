"""Runtime-owned, authorized subscriptions between message sessions."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from time import monotonic
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.message.message_event_result import MessageChain

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

MIN_WATCH_TTL_SECONDS = 60
DEFAULT_WATCH_TTL_SECONDS = 12 * 60 * 60
MAX_WATCH_TTL_SECONDS = 10 * 24 * 60 * 60

if TYPE_CHECKING:
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.file_token_service import FileTokenService

    from .astr_message_event import AstrMessageEvent


@dataclass(frozen=True, slots=True)
class SessionWatch:
    """One expiring watch owned by a trusted authorization subject."""

    source_umo: str
    target_umo: str
    subject_id: str
    expires_at: float

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.expires_at - monotonic()))


@dataclass(frozen=True, slots=True)
class _WatchGrant:
    watch: SessionWatch
    subject: Subject
    context: AuthContext


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
        default_ttl_seconds: int = DEFAULT_WATCH_TTL_SECONDS,
        max_watches_per_subject: int = 16,
    ) -> None:
        self._send_message = send_message
        self._get_capabilities = get_capabilities
        self._authorization = authorization
        self._get_config_id = get_config_id
        self._file_token_service = file_token_service
        self._get_callback_base = get_callback_base
        self._get_locale = get_locale
        self._get_platform_family = get_platform_family
        self._default_ttl_seconds = min(
            MAX_WATCH_TTL_SECONDS, max(MIN_WATCH_TTL_SECONDS, default_ttl_seconds)
        )
        self._max_watches_per_subject = max(1, max_watches_per_subject)
        self._watches: dict[tuple[str, str, str], _WatchGrant] = {}
        self._expiry_tasks: dict[tuple[str, str, str], asyncio.Task] = {}
        self._forwarded: OrderedDict[tuple[str, str, str], None] = OrderedDict()
        self._message_ids: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self._lock = asyncio.Lock()
        self._delivery_lock = asyncio.Lock()

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
        now = monotonic()
        key = (subject.id, listener, target)
        async with self._lock:
            expired = self._purge(now)
            owned_count = sum(item[0] == subject.id for item in self._watches)
            if (
                key not in self._watches
                and owned_count >= self._max_watches_per_subject
            ):
                raise ValueError("Watch limit exceeded")
            if key not in self._watches and len(self._watches) >= 1024:
                raise ValueError("Runtime watch limit exceeded")
            previous = self._expiry_tasks.pop(key, None)
            if previous is not None:
                previous.cancel()
            watch = SessionWatch(listener, target, subject.id, now + ttl)
            grant = _WatchGrant(watch, subject, context)
            self._watches[key] = grant
            self._arm_expiry(key, grant)
        await self._notify_expired_watches(expired)
        return watch

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
            removed = self._watches.pop(key, None) is not None
            task = self._expiry_tasks.pop(key, None)
        if task is not None:
            task.cancel()
        return removed

    async def list_watches(self, event: AstrMessageEvent) -> tuple[SessionWatch, ...]:
        subject, _ = self._actor(event)
        async with self._lock:
            expired = self._purge(monotonic())
            items = tuple(
                grant.watch
                for key, grant in self._watches.items()
                if key[:2] == (subject.id, event.unified_msg_origin)
            )
        await self._notify_expired_watches(expired)
        return items

    async def send(self, event: AstrMessageEvent, target_umo: str) -> DeliveryReceipt:
        """Send the command's ordered rich content under target authorization."""
        subject, context = self._actor(event)
        await self._authorize(
            subject, context, event.unified_msg_origin, "session.send"
        )
        await self._authorize(subject, context, target_umo, "session.send")
        if not self._get_capabilities(target_umo).proactive:
            raise ValueError("Target adapter does not support proactive delivery")
        envelope = envelope_from_send_event(event, target_umo)
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

    async def _check_watch(self, grant: _WatchGrant) -> None:
        watch = grant.watch
        key = (watch.subject_id, watch.source_umo, watch.target_umo)
        if self._watches.get(key) is not grant or watch.expires_at <= monotonic():
            raise PermissionError("Watch is no longer active")
        await self._authorize(
            grant.subject, grant.context, watch.source_umo, "session.watch"
        )
        await self._authorize(
            grant.subject, grant.context, watch.target_umo, "session.watch"
        )

    async def observe(self, envelope: MessageEnvelope) -> None:
        """Forward ingress snapshots, removing expired or revoked watches."""
        if envelope.is_self_message:
            return
        origin = envelope.source_umo
        async with self._lock:
            expired = self._purge(monotonic())
            watches = tuple(
                (key, grant)
                for key, grant in self._watches.items()
                if grant.watch.target_umo == origin
            )
        await self._notify_expired_watches(expired)
        for key, grant in watches:
            watch = grant.watch
            try:
                await self._authorize(
                    grant.subject, grant.context, watch.source_umo, "session.watch"
                )
                await self._authorize(
                    grant.subject, grant.context, watch.target_umo, "session.watch"
                )
                async with self._lock:
                    if (
                        self._watches.get(key) is not grant
                        or watch.expires_at <= monotonic()
                    ):
                        continue
                    dedup = (watch.source_umo, origin, envelope.source_message_id or "")
                    if envelope.source_message_id:
                        if dedup in self._forwarded:
                            continue
                        self._forwarded[dedup] = None
                        if len(self._forwarded) > 8192:
                            self._forwarded.popitem(last=False)
                locale = await self._locale_for(watch.source_umo)
                forwarded = replace(
                    envelope,
                    content=(
                        PortablePart(
                            ContentKind.TEXT,
                            render_source_header(
                                envelope,
                                self._platform_family(watch.source_umo),
                                locale,
                            ),
                        ),
                        *envelope.content,
                    ),
                )
                receipt = await self._deliver(
                    watch.source_umo,
                    forwarded,
                    lambda: self._check_watch(grant),
                    locale=locale,
                )
                if receipt.status != "accepted":
                    logger.warning(
                        "Session bridge submission status: %s", receipt.status
                    )
            except PermissionError:
                async with self._lock:
                    if self._watches.get(key) is grant:
                        self._watches.pop(key)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Transport exceptions may contain credentials or private URLs.
                logger.warning("Session bridge delivery failed")

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
        async with self._delivery_lock:
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

    def _purge(self, now: float) -> tuple[_WatchGrant, ...]:
        expired: list[_WatchGrant] = []
        for key, grant in tuple(self._watches.items()):
            if grant.watch.expires_at <= now:
                self._watches.pop(key)
                expired.append(grant)
        return tuple(expired)

    def _arm_expiry(self, key: tuple[str, str, str], grant: _WatchGrant) -> None:
        previous = self._expiry_tasks.pop(key, None)
        if previous is not None:
            previous.cancel()
        task = asyncio.create_task(
            self._expire_watch(key, grant),
            name=f"session-watch-expire:{key[1]}:{key[2]}",
        )
        self._expiry_tasks[key] = task

        def _done(done: asyncio.Task) -> None:
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

    async def _expire_watch(
        self, key: tuple[str, str, str], grant: _WatchGrant
    ) -> None:
        delay = max(0.0, grant.watch.expires_at - monotonic())
        await asyncio.sleep(delay)
        async with self._lock:
            if self._watches.get(key) is not grant:
                return
            self._watches.pop(key, None)
        await self._notify_expired(grant)

    async def _notify_expired_watches(self, expired: tuple[_WatchGrant, ...]) -> None:
        for grant in expired:
            await self._notify_expired(grant)

    async def _notify_expired(self, grant: _WatchGrant) -> None:
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
            logger.warning("Session watch expiry notice failed")

    async def terminate(self) -> None:
        """Cancel expiry tasks and drop in-memory watches."""
        async with self._lock:
            tasks = list(self._expiry_tasks.values())
            self._expiry_tasks.clear()
            self._watches.clear()
            self._forwarded.clear()
            self._message_ids.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = [
    "DEFAULT_WATCH_TTL_SECONDS",
    "MAX_WATCH_TTL_SECONDS",
    "MIN_WATCH_TTL_SECONDS",
    "SessionBridgeManager",
    "SessionWatch",
]
