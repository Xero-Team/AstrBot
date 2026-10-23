from datetime import UTC, datetime

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, desc, select

from astrbot.core.db.po import KnowledgeBaseTask
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session

_ACTIVE_TASK_STATUSES = ("pending", "processing")
_TERMINAL_TASK_STATUSES = ("completed", "failed", "interrupted")


class KnowledgeBaseTaskStoreMixin(DatabaseStoreMixin):
    """Persist knowledge-base ingestion task state in the main database."""

    async def create_knowledge_base_task(
        self,
        *,
        task_id: str,
        operation_kind: str,
        kb_id: str,
    ) -> KnowledgeBaseTask:
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                task = KnowledgeBaseTask(
                    task_id=task_id,
                    operation_kind=operation_kind,
                    kb_id=kb_id,
                )
                session.add(task)
                await session.flush()
                await session.refresh(task)
                return task

    async def get_knowledge_base_task(self, task_id: str) -> KnowledgeBaseTask | None:
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(KnowledgeBaseTask).where(
                    col(KnowledgeBaseTask.task_id) == task_id
                )
            )
            return result.scalar_one_or_none()

    async def update_knowledge_base_task(
        self,
        *,
        task_id: str,
        status: str,
        progress: dict | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> KnowledgeBaseTask | None:
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                values: dict[str, object] = {
                    "status": status,
                    "error": error,
                    "updated_at": datetime.now(UTC),
                }
                if progress is not None:
                    values["progress"] = progress
                if result is not None:
                    values["result"] = result
                statement = update(KnowledgeBaseTask).where(
                    col(KnowledgeBaseTask.task_id) == task_id
                )
                if status in _ACTIVE_TASK_STATUSES:
                    statement = statement.where(
                        col(KnowledgeBaseTask.status).in_(_ACTIVE_TASK_STATUSES)
                    )
                await session.execute(statement.values(**values))
                query_result = await session.execute(
                    select(KnowledgeBaseTask).where(
                        col(KnowledgeBaseTask.task_id) == task_id
                    )
                )
                return query_result.scalar_one_or_none()

    async def interrupt_active_knowledge_base_tasks(self) -> int:
        """Mark abandoned active tasks as interrupted without replaying work."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(KnowledgeBaseTask).where(
                        col(KnowledgeBaseTask.status).in_(_ACTIVE_TASK_STATUSES)
                    )
                )
                tasks = list(result.scalars().all())
                now = datetime.now(UTC)
                for task in tasks:
                    task.status = "interrupted"
                    task.error = "Knowledge base task interrupted"
                    task.updated_at = now
                return len(tasks)

    async def prune_knowledge_base_tasks(
        self,
        *,
        older_than: datetime,
        max_records: int,
    ) -> int:
        """Delete stale terminal tasks and cap retained terminal history."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                terminal = col(KnowledgeBaseTask.status).in_(_TERMINAL_TASK_STATUSES)
                stale = await session.execute(
                    select(KnowledgeBaseTask.id).where(
                        terminal,
                        col(KnowledgeBaseTask.updated_at) < older_than,
                    )
                )
                delete_ids = {task_id for task_id in stale.scalars().all() if task_id}
                retained = await session.execute(
                    select(KnowledgeBaseTask.id)
                    .where(terminal, col(KnowledgeBaseTask.updated_at) >= older_than)
                    .order_by(
                        desc(KnowledgeBaseTask.updated_at), desc(KnowledgeBaseTask.id)
                    )
                    .offset(max(max_records, 0))
                )
                delete_ids.update(
                    task_id for task_id in retained.scalars().all() if task_id
                )
                if not delete_ids:
                    return 0
                await session.execute(
                    delete(KnowledgeBaseTask).where(
                        col(KnowledgeBaseTask.id).in_(delete_ids)
                    )
                )
                return len(delete_ids)
