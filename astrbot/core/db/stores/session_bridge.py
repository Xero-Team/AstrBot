import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select, update

from astrbot.core.db.po import SessionBridgeRule
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session

_RULE_ID_ATTEMPTS = 8
_RULE_FIELD_NOT_SET = object()


class SessionBridgeStoreMixin(DatabaseStoreMixin):
    async def insert_session_bridge_rule(
        self,
        *,
        subject_id: str,
        source_umo: str,
        target_umo: str,
        source_config_id: str,
        target_config_id: str,
        kind: str,
        expires_at: int | None = None,
        header: bool = True,
        pair_id: str | None = None,
        match: dict | None = None,
        except_: dict | None = None,
        rule_id: str | None = None,
    ) -> SessionBridgeRule:
        """Insert one directed session-bridge edge, allocating a rule id if needed.

        Args:
            subject_id: Authorization subject that owns the edge.
            source_umo: Listening session that receives forwarded messages.
            target_umo: Observed session whose inbound traffic is forwarded.
            source_config_id: Config id of the listening session at write time.
            target_config_id: Config id of the observed session at write time.
            kind: Edge kind. Writes ``watch``, ``connect``, or ``pair``.
            expires_at: Wall-clock UTC unix seconds, or None for unbounded edges.
            header: Whether deliveries include a source header. Pair writes True.
            pair_id: Shared 12-hex id for a pair. Watch and connect write None.
            match: Inclusive filter document. S1 writes ``{}``.
            except_: Exclusive filter document. S1 writes ``{}``.
            rule_id: Optional 12-hex id. Allocated on collision retry when omitted.

        Returns:
            The inserted row.

        Raises:
            IntegrityError: Direction uniqueness failed, or a caller-supplied
                ``rule_id`` collided.
            RuntimeError: An id could not be allocated after retries.
        """
        match_payload = {} if match is None else match
        except_payload = {} if except_ is None else except_
        last_error: IntegrityError | None = None
        for _ in range(_RULE_ID_ATTEMPTS):
            allocated = rule_id or secrets.token_hex(6)
            try:
                async with store_session(self) as session:
                    session: AsyncSession
                    async with session.begin():
                        row = SessionBridgeRule(
                            rule_id=allocated,
                            subject_id=subject_id,
                            source_umo=source_umo,
                            target_umo=target_umo,
                            source_config_id=source_config_id,
                            target_config_id=target_config_id,
                            kind=kind,
                            expires_at=expires_at,
                            header=header,
                            pair_id=pair_id,
                            match=match_payload,
                            except_=except_payload,
                        )
                        session.add(row)
                        await session.flush()
                        await session.refresh(row)
                        return row
            except IntegrityError as exc:
                last_error = exc
                if rule_id is not None:
                    raise
                orig = str(getattr(exc, "orig", exc))
                if "rule_id" not in orig:
                    raise
        raise RuntimeError(
            "Unable to allocate a session bridge rule id"
        ) from last_error

    async def insert_session_bridge_pair(
        self,
        *,
        subject_id: str,
        source_umo: str,
        target_umo: str,
        source_config_id: str,
        target_config_id: str,
        pair_id: str,
        drop_rule_ids: tuple[str, ...] = (),
    ) -> tuple[SessionBridgeRule, SessionBridgeRule]:
        """Replace optional occupying edges and insert both pair rows atomically.

        Args:
            subject_id: Authorization subject that owns both edges.
            source_umo: Listening session for the forward edge.
            target_umo: Observed session for the forward edge.
            source_config_id: Config id of the forward listening session.
            target_config_id: Config id of the forward observed session.
            pair_id: Shared 12-hex id written on both edges.
            drop_rule_ids: Existing rule ids on those two directions to delete
                in the same transaction.

        Returns:
            The inserted forward and reverse rows.

        Raises:
            IntegrityError: Direction uniqueness failed after the drops.
            RuntimeError: A pair of ids could not be allocated after retries.
        """
        unique_drops = tuple(dict.fromkeys(drop_rule_ids))
        last_error: IntegrityError | None = None
        for _ in range(_RULE_ID_ATTEMPTS):
            left_id = secrets.token_hex(6)
            right_id = secrets.token_hex(6)
            if left_id == right_id:
                continue
            try:
                async with store_session(self) as session:
                    session: AsyncSession
                    async with session.begin():
                        if unique_drops:
                            await session.execute(
                                delete(SessionBridgeRule).where(
                                    col(SessionBridgeRule.rule_id).in_(unique_drops)
                                )
                            )
                        left = SessionBridgeRule(
                            rule_id=left_id,
                            subject_id=subject_id,
                            source_umo=source_umo,
                            target_umo=target_umo,
                            source_config_id=source_config_id,
                            target_config_id=target_config_id,
                            kind="pair",
                            expires_at=None,
                            header=True,
                            pair_id=pair_id,
                            match={},
                            except_={},
                        )
                        right = SessionBridgeRule(
                            rule_id=right_id,
                            subject_id=subject_id,
                            source_umo=target_umo,
                            target_umo=source_umo,
                            source_config_id=target_config_id,
                            target_config_id=source_config_id,
                            kind="pair",
                            expires_at=None,
                            header=True,
                            pair_id=pair_id,
                            match={},
                            except_={},
                        )
                        session.add(left)
                        session.add(right)
                        await session.flush()
                        await session.refresh(left)
                        await session.refresh(right)
                        return left, right
            except IntegrityError as exc:
                last_error = exc
                orig = str(getattr(exc, "orig", exc))
                if "rule_id" not in orig:
                    raise
        raise RuntimeError(
            "Unable to allocate a session bridge rule id"
        ) from last_error

    async def get_session_bridge_rule(self, rule_id: str) -> SessionBridgeRule | None:
        """Return one rule by public id."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(SessionBridgeRule).where(
                    col(SessionBridgeRule.rule_id) == rule_id
                )
            )
            return result.scalar_one_or_none()

    async def get_session_bridge_rule_by_direction(
        self,
        subject_id: str,
        source_umo: str,
        target_umo: str,
    ) -> SessionBridgeRule | None:
        """Return the edge for one owner and direction, if any."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(SessionBridgeRule).where(
                    col(SessionBridgeRule.subject_id) == subject_id,
                    col(SessionBridgeRule.source_umo) == source_umo,
                    col(SessionBridgeRule.target_umo) == target_umo,
                )
            )
            return result.scalar_one_or_none()

    async def list_session_bridge_rules(self) -> list[SessionBridgeRule]:
        """Return every persisted session-bridge edge."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(SessionBridgeRule).order_by(
                    col(SessionBridgeRule.created_at),
                    col(SessionBridgeRule.rule_id),
                )
            )
            return list(result.scalars().all())

    async def list_session_bridge_rules_by_subject(
        self, subject_id: str
    ) -> list[SessionBridgeRule]:
        """Return edges owned by one authorization subject."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(SessionBridgeRule)
                .where(col(SessionBridgeRule.subject_id) == subject_id)
                .order_by(
                    col(SessionBridgeRule.created_at),
                    col(SessionBridgeRule.rule_id),
                )
            )
            return list(result.scalars().all())

    async def list_session_bridge_connects_for_listener(
        self, subject_id: str, source_umo: str
    ) -> list[SessionBridgeRule]:
        """Return connect edges for one owner and listening session."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(SessionBridgeRule)
                .where(
                    col(SessionBridgeRule.subject_id) == subject_id,
                    col(SessionBridgeRule.source_umo) == source_umo,
                    col(SessionBridgeRule.kind) == "connect",
                )
                .order_by(
                    col(SessionBridgeRule.created_at),
                    col(SessionBridgeRule.rule_id),
                )
            )
            return list(result.scalars().all())

    async def list_session_bridge_rules_touching_config(
        self, config_id: str
    ) -> list[SessionBridgeRule]:
        """Return edges whose source or target config id equals ``config_id``."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(SessionBridgeRule)
                .where(
                    (col(SessionBridgeRule.source_config_id) == config_id)
                    | (col(SessionBridgeRule.target_config_id) == config_id)
                )
                .order_by(
                    col(SessionBridgeRule.created_at),
                    col(SessionBridgeRule.rule_id),
                )
            )
            return list(result.scalars().all())

    async def update_session_bridge_rule(
        self,
        rule_id: str,
        *,
        expires_at: int | None | object = _RULE_FIELD_NOT_SET,
        kind: str | None | object = _RULE_FIELD_NOT_SET,
        target_umo: str | None | object = _RULE_FIELD_NOT_SET,
        source_config_id: str | None | object = _RULE_FIELD_NOT_SET,
        target_config_id: str | None | object = _RULE_FIELD_NOT_SET,
        header: bool | None | object = _RULE_FIELD_NOT_SET,
        pair_id: str | None | object = _RULE_FIELD_NOT_SET,
        match: dict | None | object = _RULE_FIELD_NOT_SET,
        except_: dict | None | object = _RULE_FIELD_NOT_SET,
    ) -> SessionBridgeRule | None:
        """Patch selected columns on one rule.

        Args:
            rule_id: Public edge id.
            expires_at: Wall-clock expiry, or None to clear.
            kind: Replacement kind.
            target_umo: Replacement observed session.
            source_config_id: Replacement listener config id.
            target_config_id: Replacement observed-session config id.
            header: Replacement header flag.
            pair_id: Replacement pair id.
            match: Replacement inclusive filter document.
            except_: Replacement exclusive filter document.

        Returns:
            The updated row, or None when ``rule_id`` is missing.
        """
        updates: dict = {}
        for key, val in {
            "expires_at": expires_at,
            "kind": kind,
            "target_umo": target_umo,
            "source_config_id": source_config_id,
            "target_config_id": target_config_id,
            "header": header,
            "pair_id": pair_id,
            "match": match,
            "except_": except_,
        }.items():
            if val is _RULE_FIELD_NOT_SET:
                continue
            updates[key] = val
        if not updates:
            return await self.get_session_bridge_rule(rule_id)
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(SessionBridgeRule)
                    .where(col(SessionBridgeRule.rule_id) == rule_id)
                    .values(**updates)
                    .execution_options(synchronize_session="fetch")
                )
                result = await session.execute(
                    select(SessionBridgeRule).where(
                        col(SessionBridgeRule.rule_id) == rule_id
                    )
                )
                return result.scalar_one_or_none()

    async def delete_session_bridge_rule(self, rule_id: str) -> None:
        """Delete one rule by public id."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(SessionBridgeRule).where(
                        col(SessionBridgeRule.rule_id) == rule_id
                    )
                )

    async def delete_session_bridge_connects_for_listener(
        self, subject_id: str, source_umo: str
    ) -> None:
        """Delete every connect edge for one owner and listening session."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(SessionBridgeRule).where(
                        col(SessionBridgeRule.subject_id) == subject_id,
                        col(SessionBridgeRule.source_umo) == source_umo,
                        col(SessionBridgeRule.kind) == "connect",
                    )
                )
