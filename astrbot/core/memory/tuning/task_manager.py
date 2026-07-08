import hashlib

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import MemoryTuningTask
from astrbot.core.memory.retrieval import MemoryRetrievalManager


class MemoryTuningTaskManager:
    def __init__(
        self,
        db: BaseDatabase,
        retrieval: MemoryRetrievalManager,
    ) -> None:
        self.db = db
        self.retrieval = retrieval

    async def run_retrieval_probe(
        self,
        *,
        person_id: str,
        chat_id: str,
        queries: list[str],
        limit: int = 5,
    ) -> MemoryTuningTask:
        clean_queries = [query.strip() for query in queries if query.strip()]
        scope = await self.retrieval.resolve_scope(chat_id)
        digest = hashlib.sha256(
            f"{person_id}:{chat_id}:{'|'.join(clean_queries)}:{limit}".encode()
        ).hexdigest()[:24]
        if not clean_queries:
            return await self.db.upsert_memory_tuning_task(
                task_id=digest,
                task_type="retrieval_probe",
                target_scope=scope.scope_id,
                candidate_config={
                    "limit": limit,
                    "allowed_chat_ids": scope.allowed_chat_ids,
                },
                evaluation_result={
                    "query_count": 0,
                    "queries_with_results": 0,
                    "returned_count": 0,
                    "coverage": 0.0,
                },
                status="completed",
            )

        returned_count = 0
        queries_with_results = 0
        samples: list[dict] = []
        for query in clean_queries:
            facts = await self.retrieval.search(
                person_id=person_id,
                chat_id=chat_id,
                query=query,
                limit=limit,
            )
            returned_count += len(facts)
            if facts:
                queries_with_results += 1
            samples.append(
                {
                    "query": query,
                    "returned": len(facts),
                    "top_fact": facts[0].fact_text if facts else None,
                }
            )

        return await self.db.upsert_memory_tuning_task(
            task_id=digest,
            task_type="retrieval_probe",
            target_scope=scope.scope_id,
            candidate_config={
                "limit": limit,
                "allowed_chat_ids": scope.allowed_chat_ids,
            },
            evaluation_result={
                "query_count": len(clean_queries),
                "queries_with_results": queries_with_results,
                "returned_count": returned_count,
                "coverage": queries_with_results / len(clean_queries),
                "samples": samples,
            },
            status="completed",
        )
