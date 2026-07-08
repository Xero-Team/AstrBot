import hashlib

from astrbot.core.agent.message import TextPart
from astrbot.core.db import BaseDatabase
from astrbot.core.memory.models import MemoryWritebackItem
from astrbot.core.memory.policy import MemoryScopePolicy
from astrbot.core.memory.retrieval import MemoryRetrievalManager
from astrbot.core.memory.tuning import MemoryTuningTaskManager
from astrbot.core.memory.writeback import MemoryWritebackWorker
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest


class MemoryManager:
    def __init__(self, db: BaseDatabase) -> None:
        self.scope_policy = MemoryScopePolicy()
        self.retrieval = MemoryRetrievalManager(db, self.scope_policy)
        self.tuning = MemoryTuningTaskManager(db, self.retrieval)
        self.writeback_worker = MemoryWritebackWorker(db)

    async def initialize(self) -> None:
        await self.writeback_worker.start()

    async def terminate(self) -> None:
        await self.writeback_worker.stop()

    def resolve_person_id(self, event: AstrMessageEvent) -> str:
        sender = getattr(getattr(event, "message_obj", None), "sender", None)
        return str(getattr(sender, "user_id", "") or event.unified_msg_origin)

    async def enqueue_turn(
        self,
        *,
        event: AstrMessageEvent,
        conversation_id: str | None,
        assistant_text: str,
    ) -> bool:
        scope = self.scope_policy.resolve(event.unified_msg_origin)
        digest = hashlib.sha256(
            f"{event.unified_msg_origin}\n{event.message_str or ''}\n{assistant_text}".encode()
        ).hexdigest()[:24]
        source_message_id = f"{conversation_id or event.unified_msg_origin}:{digest}"
        return await self.writeback_worker.enqueue(
            MemoryWritebackItem(
                person_id=self.resolve_person_id(event),
                chat_id=event.unified_msg_origin,
                scope_id=scope.scope_id,
                user_text=event.message_str or "",
                assistant_text=assistant_text,
                source_message_id=source_message_id,
                evidence_message_ids=[source_message_id],
            )
        )

    async def inject_context(
        self,
        *,
        req: ProviderRequest,
        event: AstrMessageEvent,
        query: str | None = None,
    ) -> None:
        person_id = self.resolve_person_id(event)
        profile = await self.retrieval.get_profile(
            person_id=person_id,
            chat_id=event.unified_msg_origin,
        )
        facts = await self.retrieval.search(
            person_id=person_id,
            chat_id=event.unified_msg_origin,
            query=query or "",
            limit=3,
        )
        episodes = await self.retrieval.search_episodes(
            chat_id=event.unified_msg_origin,
            query=query or "",
            limit=1,
        )
        if not profile and not facts and not episodes:
            return
        sections: list[str] = ["<memory_context>"]
        if profile:
            sections.append(profile.profile_text)
        if facts:
            sections.append("Relevant facts:")
            sections.extend(f"- {fact.fact_text}" for fact in facts)
        if episodes:
            sections.append("Relevant episode:")
            sections.extend(
                f"- {episode.title}: {episode.summary}" for episode in episodes
            )
        sections.append(
            "Use these memories as transient internal context only. Do not quote them verbatim."
        )
        sections.append("</memory_context>")
        req.extra_user_content_parts.append(
            TextPart(text="\n".join(sections)).mark_as_temp()
        )
