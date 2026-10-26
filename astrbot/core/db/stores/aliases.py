from datetime import UTC, datetime

from sqlalchemy import func, or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.core.db.po import UmoAlias, UmoSender
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class UmoAliasStoreMixin(DatabaseStoreMixin):
    async def upsert_umo_alias(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str | None,
        user_alias: str | None,
    ) -> UmoAlias:
        """Create or update alias metadata for a UMO."""
        now = datetime.now(UTC)
        statement = sqlite_insert(UmoAlias).values(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=user_alias,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoAlias.umo],
            set_={
                "creator_sender_id": statement.excluded.creator_sender_id,
                "auto_name": statement.excluded.auto_name,
                "user_alias": statement.excluded.user_alias,
                "updated_at": now,
            },
        )
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)
                result = await session.execute(
                    select(UmoAlias).where(col(UmoAlias.umo) == umo)
                )
                return result.scalar_one()

    async def upsert_umo_auto_name(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str,
    ) -> None:
        """Persist an automatic UMO name without changing its manual alias."""
        now = datetime.now(UTC)
        statement = sqlite_insert(UmoAlias).values(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=None,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoAlias.umo],
            set_={
                "auto_name": statement.excluded.auto_name,
                "updated_at": now,
            },
            where=col(UmoAlias.auto_name).is_distinct_from(
                statement.excluded.auto_name
            ),
        )
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)

    async def get_umo_alias(self, umo: str) -> UmoAlias | None:
        """Get alias metadata for one UMO."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(UmoAlias).where(col(UmoAlias.umo) == umo)
            )
            return result.scalar_one_or_none()

    async def get_umo_aliases(self, umos: list[str] | None = None) -> list[UmoAlias]:
        """Get alias metadata, optionally restricted to a UMO list."""
        if umos is not None and not umos:
            return []

        async with store_session(self) as session:
            session: AsyncSession
            query = select(UmoAlias)
            if umos is not None:
                query = query.where(col(UmoAlias.umo).in_(umos))
            result = await session.execute(query)
            return list(result.scalars().all())

    async def upsert_umo_sender(
        self, umo: str, sender_id: str, sender_name: str
    ) -> None:
        """Insert a sender or update a changed, nonempty name."""
        if not sender_id:
            return
        now = datetime.now(UTC)
        statement = sqlite_insert(UmoSender).values(
            umo=umo,
            sender_id=sender_id,
            sender_name=sender_name,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoSender.umo, UmoSender.sender_id],
            set_={"sender_name": statement.excluded.sender_name, "updated_at": now},
            where=(statement.excluded.sender_name != "")
            & col(UmoSender.sender_name).is_distinct_from(
                statement.excluded.sender_name
            ),
        )
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)

    async def get_umo_senders(
        self,
        search: str = "",
        limit: int = 50,
        sender_ids: list[str] | None = None,
        offset: int = 0,
    ) -> list[tuple[UmoSender, UmoAlias | None]]:
        """Search sender metadata joined to session aliases."""
        query = select(UmoSender, UmoAlias).outerjoin(
            UmoAlias, col(UmoSender.umo) == col(UmoAlias.umo)
        )
        if sender_ids is not None:
            if not sender_ids:
                return []
            query = query.where(col(UmoSender.sender_id).in_(sender_ids))
        if search:
            query = query.where(
                or_(
                    *(
                        column.icontains(search, autoescape=True)
                        for column in (
                            col(UmoSender.sender_id),
                            col(UmoSender.sender_name),
                            col(UmoSender.umo),
                            col(UmoAlias.auto_name),
                            col(UmoAlias.user_alias),
                        )
                    )
                )
            )
        platform_id = func.substr(
            UmoSender.umo, 1, func.instr(col(UmoSender.umo) + ":", ":") - 1
        )
        ranked = query.with_only_columns(
            col(UmoSender.id),
            func.row_number()
            .over(
                partition_by=(
                    [UmoSender.sender_id]
                    if sender_ids is not None
                    else [platform_id, UmoSender.sender_id]
                ),
                order_by=(col(UmoSender.updated_at).desc(), col(UmoSender.id).desc()),
            )
            .label("rank"),
        ).subquery()
        query = query.where(
            col(UmoSender.id).in_(select(ranked.c.id).where(ranked.c.rank == 1))
        )
        query = (
            query.order_by(col(UmoSender.updated_at).desc(), col(UmoSender.id).desc())
            .offset(offset)
            .limit(limit)
        )
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(query)
            return [(sender, alias) for sender, alias in result.all()]
