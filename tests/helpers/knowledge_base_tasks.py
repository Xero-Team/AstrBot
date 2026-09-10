from datetime import UTC, datetime
from types import SimpleNamespace


class InMemoryKnowledgeBaseTaskStore:
    """Minimal durable-store double for knowledge-base service tests."""

    def __init__(self) -> None:
        self.tasks: dict[str, SimpleNamespace] = {}

    async def create_knowledge_base_task(self, *, task_id, operation_kind, kb_id):
        task = SimpleNamespace(
            task_id=task_id,
            operation_kind=operation_kind,
            kb_id=kb_id,
            status="pending",
            progress={},
            result=None,
            error=None,
            updated_at=datetime.now(UTC),
        )
        self.tasks[task_id] = task
        return task

    async def get_knowledge_base_task(self, task_id):
        return self.tasks.get(task_id)

    async def update_knowledge_base_task(
        self, *, task_id, status, progress=None, result=None, error=None
    ):
        task = self.tasks.get(task_id)
        if task is None:
            task = await self.create_knowledge_base_task(
                task_id=task_id, operation_kind="test", kb_id="kb-1"
            )
        task.status = status
        if progress is not None:
            task.progress = progress
        if result is not None:
            task.result = result
        task.error = error
        task.updated_at = datetime.now(UTC)
        return task

    async def interrupt_active_knowledge_base_tasks(self):
        active = [
            task
            for task in self.tasks.values()
            if task.status in {"pending", "processing"}
        ]
        for task in active:
            task.status = "interrupted"
            task.error = "Knowledge base task interrupted"
        return len(active)

    async def prune_knowledge_base_tasks(self, *, older_than, max_records):
        terminal_tasks = [
            (task_id, task)
            for task_id, task in self.tasks.items()
            if task.status in {"completed", "failed", "interrupted"}
        ]
        delete_ids = {
            task_id for task_id, task in terminal_tasks if task.updated_at < older_than
        }
        retained = sorted(
            (
                (task_id, task)
                for task_id, task in terminal_tasks
                if task_id not in delete_ids
            ),
            key=lambda item: item[1].updated_at,
            reverse=True,
        )
        delete_ids.update(task_id for task_id, _task in retained[max(max_records, 0) :])
        for task_id in delete_ids:
            del self.tasks[task_id]
        return len(delete_ids)
