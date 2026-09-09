from datetime import UTC, datetime, timedelta

import pytest

from astrbot.core.db.po import KnowledgeBaseTask
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_knowledge_base_task_store_round_trip_and_interruption(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.create_knowledge_base_task(
        task_id="task-pending",
        operation_kind="upload",
        kb_id="kb-1",
    )
    assert created.status == "pending"
    updated = await temp_db.update_knowledge_base_task(
        task_id="task-pending",
        status="processing",
        progress={"current": 5, "total": 10},
    )
    assert updated is not None
    assert updated.progress == {"current": 5, "total": 10}
    await temp_db.create_knowledge_base_task(
        task_id="task-completed", operation_kind="import", kb_id="kb-1"
    )
    await temp_db.update_knowledge_base_task(
        task_id="task-completed", status="completed", result={"ok": True}
    )

    assert await temp_db.interrupt_active_knowledge_base_tasks() == 1
    interrupted = await temp_db.get_knowledge_base_task("task-pending")
    completed = await temp_db.get_knowledge_base_task("task-completed")
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.error == "Knowledge base task interrupted"
    assert completed is not None
    assert completed.status == "completed"
    assert completed.result == {"ok": True}


@pytest.mark.asyncio
async def test_knowledge_base_task_pruning_keeps_active_and_recent_records(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    for index, status, updated_at in (
        ("old", "completed", now - timedelta(days=8)),
        ("recent-1", "completed", now - timedelta(hours=2)),
        ("recent-2", "failed", now - timedelta(hours=1)),
        ("active", "processing", now - timedelta(days=30)),
    ):
        await temp_db.create_knowledge_base_task(
            task_id=f"task-{index}", operation_kind="upload", kb_id="kb-1"
        )
        await temp_db.update_knowledge_base_task(task_id=f"task-{index}", status=status)
        async with temp_db.get_db() as session:
            stored = await temp_db.get_knowledge_base_task(f"task-{index}")
            assert stored is not None
            task = await session.get(KnowledgeBaseTask, stored.id)
            assert task is not None
            task.updated_at = updated_at
            await session.commit()

    assert (
        await temp_db.prune_knowledge_base_tasks(
            older_than=now - timedelta(days=7), max_records=1
        )
        == 2
    )
    assert await temp_db.get_knowledge_base_task("task-old") is None
    assert await temp_db.get_knowledge_base_task("task-recent-1") is None
    assert await temp_db.get_knowledge_base_task("task-recent-2") is not None
    active = await temp_db.get_knowledge_base_task("task-active")
    assert active is not None
    assert active.status == "processing"
