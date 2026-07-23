import uuid
from datetime import UTC, datetime
from typing import Any

from astrbot import logger
from astrbot.core.db.protocols import MemoryStore
from astrbot.core.memory.manager import MemoryManager
from astrbot.core.memory.writeback.profile_refresher import MemoryProfileRefresher
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.task_utils import create_tracked_task


class MemoryServiceError(Exception):
    pass


class MemoryService:
    def __init__(self, db: MemoryStore, memory_manager: MemoryManager) -> None:
        self.db = db
        self.memory_manager = memory_manager
        self.profile_refresher = MemoryProfileRefresher(db)
        self.refresh_tasks: dict[str, dict[str, Any]] = {}
        self._background_tasks: set = set()

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _page(page: int, page_size: int) -> tuple[int, int, int]:
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 20), 1), 200)
        return page, page_size, (page - 1) * page_size

    @staticmethod
    def _row(row) -> dict[str, Any]:
        return row.model_dump(mode="json")

    @staticmethod
    def _status_filter(status: str | None) -> str | None:
        if status in {None, "", "all"}:
            return None
        if status not in {"active", "deleted"}:
            raise MemoryServiceError("Unsupported memory fact status")
        return status

    def _scope_id(self, chat_id: str, scope_id: str | None = None) -> str:
        if scope_id:
            return scope_id
        return self.memory_manager.scope_policy.resolve(chat_id).scope_id

    async def list_facts(
        self,
        *,
        page: int,
        page_size: int,
        person_id: str | None = None,
        chat_id: str | None = None,
        scope_id: str | None = None,
        status: str | None = "active",
        query: str | None = None,
    ) -> dict[str, Any]:
        page, page_size, offset = self._page(page, page_size)
        status = self._status_filter(status)
        chat_ids = [chat_id] if chat_id else None
        items = await self.db.list_memory_facts(
            person_id=person_id,
            chat_ids=chat_ids,
            scope_id=scope_id,
            status=status,
            query=(query or "").strip() or None,
            limit=page_size,
            offset=offset,
        )
        total = await self.db.count_memory_facts(
            person_id=person_id,
            chat_ids=chat_ids,
            scope_id=scope_id,
            status=status,
            query=(query or "").strip() or None,
        )
        return {
            "items": [self._row(item) for item in items],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    async def get_fact(self, fact_id: int) -> dict[str, Any]:
        fact = await self.db.get_memory_fact(fact_id)
        if fact is None:
            raise MemoryServiceError("Memory fact not found")
        logs = await self.db.list_memory_operation_logs(
            target_type="memory_fact",
            target_id=str(fact_id),
            limit=100,
        )
        return {
            "fact": self._row(fact),
            "operation_logs": [self._row(log) for log in logs],
        }

    async def create_fact(self, data: object, *, operator: str) -> tuple[dict, str]:
        payload = self._payload(data)
        person_id = str(payload.get("person_id") or "").strip()
        chat_id = str(payload.get("chat_id") or "").strip()
        fact_text = str(payload.get("fact_text") or "").strip()
        if not person_id:
            raise MemoryServiceError("person_id is required")
        if not chat_id:
            raise MemoryServiceError("chat_id is required")
        if not fact_text:
            raise MemoryServiceError("fact_text is required")
        confidence = float(payload.get("confidence") or 0.6)
        if confidence < 0 or confidence > 1:
            raise MemoryServiceError("confidence must be between 0 and 1")
        source_message_id = (
            str(payload.get("source_message_id") or "").strip()
            or f"dashboard:{uuid.uuid4()}"
        )
        fact, created = await self.db.upsert_memory_fact(
            person_id=person_id,
            chat_id=chat_id,
            scope_id=self._scope_id(chat_id, payload.get("scope_id")),
            fact_text=fact_text,
            fact_type=str(payload.get("fact_type") or "manual").strip() or "manual",
            source_message_id=source_message_id,
            evidence_message_ids=payload.get("evidence_message_ids")
            if isinstance(payload.get("evidence_message_ids"), list)
            else [source_message_id],
            confidence=confidence,
            status="active",
        )
        await self.db.insert_memory_operation_log(
            operator=operator,
            target_type="memory_fact",
            target_id=str(fact.id),
            action="create" if created else "merge",
            reason=str(payload.get("reason") or "dashboard_create"),
            payload={
                "person_id": fact.person_id,
                "chat_id": fact.chat_id,
                "scope_id": fact.scope_id,
                "fact_text": fact.fact_text,
            },
        )
        return self._row(fact), "Memory fact saved"

    async def update_fact(
        self,
        fact_id: int,
        data: object,
        *,
        operator: str,
    ) -> tuple[dict, str]:
        payload = self._payload(data)
        updates = {
            "fact_text": payload.get("fact_text"),
            "fact_type": payload.get("fact_type"),
            "confidence": payload.get("confidence"),
        }
        if all(value is None for value in updates.values()):
            raise MemoryServiceError("At least one update field is required")
        if updates["fact_text"] is not None:
            updates["fact_text"] = str(updates["fact_text"]).strip()
            if not updates["fact_text"]:
                raise MemoryServiceError("fact_text cannot be empty")
        if updates["fact_type"] is not None:
            updates["fact_type"] = str(updates["fact_type"]).strip()
            if not updates["fact_type"]:
                raise MemoryServiceError("fact_type cannot be empty")
        if updates["confidence"] is not None:
            updates["confidence"] = float(updates["confidence"])
            if updates["confidence"] < 0 or updates["confidence"] > 1:
                raise MemoryServiceError("confidence must be between 0 and 1")
        fact = await self.db.update_memory_fact(
            fact_id,
            fact_text=updates["fact_text"],
            fact_type=updates["fact_type"],
            confidence=updates["confidence"],
            operator=operator,
            reason=str(payload.get("reason") or "dashboard_update"),
        )
        if fact is None:
            raise MemoryServiceError("Memory fact not found")
        return self._row(fact), "Memory fact updated"

    async def set_fact_status(
        self,
        fact_id: int,
        *,
        status: str,
        operator: str,
        reason: str | None = None,
    ) -> tuple[None, str]:
        fact = await self.db.get_memory_fact(fact_id)
        if fact is None:
            raise MemoryServiceError("Memory fact not found")
        ok = await self.db.update_memory_fact_status(
            fact_id,
            status=status,
            operator=operator,
            reason=reason or f"dashboard_{status}",
        )
        if not ok:
            raise MemoryServiceError("Memory fact not found")
        return (
            None,
            "Memory fact restored" if status == "active" else "Memory fact deleted",
        )

    async def list_profiles(
        self,
        *,
        page: int,
        page_size: int,
        person_id: str | None = None,
        chat_scope: str | None = None,
    ) -> dict[str, Any]:
        page, page_size, offset = self._page(page, page_size)
        profiles = await self.db.list_memory_profiles(
            person_id=person_id,
            chat_scope=chat_scope,
            limit=page_size,
            offset=offset,
        )
        total = await self.db.count_memory_profiles(
            person_id=person_id,
            chat_scope=chat_scope,
        )
        return {
            "items": [self._row(profile) for profile in profiles],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    async def _refresh_profile_task(
        self,
        task_id: str,
        *,
        person_id: str,
        chat_scope: str,
        operator: str,
    ) -> None:
        self.refresh_tasks[task_id]["status"] = "running"
        try:
            profile_text = await self.profile_refresher.refresh(
                person_id=person_id,
                chat_scope=chat_scope,
            )
            await self.db.insert_memory_operation_log(
                operator=operator,
                target_type="memory_profile",
                target_id=f"{person_id}:{chat_scope}",
                action="refresh",
                reason="dashboard_profile_refresh",
                payload={
                    "person_id": person_id,
                    "chat_scope": chat_scope,
                    "has_profile": profile_text is not None,
                },
            )
            self.refresh_tasks[task_id] = {
                "status": "completed",
                "result": {"profile_text": profile_text},
                "error": None,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Memory profile refresh failed: %s", safe_error("", exc))
            self.refresh_tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": "Memory profile refresh failed",
                "updated_at": datetime.now(UTC).isoformat(),
            }

    async def refresh_profile(
        self,
        person_id: str,
        data: object,
        *,
        operator: str,
    ) -> dict[str, Any]:
        payload = self._payload(data)
        chat_scope = str(payload.get("chat_scope") or payload.get("scope_id") or "")
        if not chat_scope:
            chat_id = str(payload.get("chat_id") or "").strip()
            if not chat_id:
                raise MemoryServiceError("chat_scope or chat_id is required")
            chat_scope = self._scope_id(chat_id)
        task_id = str(uuid.uuid4())
        self.refresh_tasks[task_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        create_tracked_task(
            self._background_tasks,
            self._refresh_profile_task(
                task_id,
                person_id=person_id,
                chat_scope=chat_scope,
                operator=operator,
            ),
            name=f"memory-profile-refresh:{task_id}",
        )
        return {"task_id": task_id, "status": "pending", "chat_scope": chat_scope}

    async def list_operations(
        self,
        *,
        page: int,
        page_size: int,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        page, page_size, offset = self._page(page, page_size)
        logs = await self.db.list_memory_operation_logs(
            target_type=target_type,
            target_id=target_id,
            limit=page_size,
            offset=offset,
        )
        total = await self.db.count_memory_operation_logs(
            target_type=target_type,
            target_id=target_id,
        )
        return {
            "items": [self._row(log) for log in logs],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    async def stats(self) -> dict[str, Any]:
        worker = self.memory_manager.writeback_worker
        task = worker._task
        return {
            "facts": await self.db.count_memory_facts(status="active"),
            "deleted_facts": await self.db.count_memory_facts(status="deleted"),
            "profiles": await self.db.count_memory_profiles(),
            "episodes": await self.db.count_memory_episodes(status="active"),
            "operations": await self.db.count_memory_operation_logs(),
            "worker": {
                "running": bool(task and not task.done()),
                "queue_size": worker.queue.qsize(),
                "queue_max_size": worker.queue.maxsize,
                "recent_profile_tasks": list(self.refresh_tasks.items())[-5:],
            },
        }


__all__ = ["MemoryService", "MemoryServiceError"]
