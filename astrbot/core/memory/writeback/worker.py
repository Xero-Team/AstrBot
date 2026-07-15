import asyncio

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.memory.models import MemoryWritebackItem

from .episode_builder import MemoryEpisodeBuilder
from .fact_extractor import MemoryFactExtractor
from .profile_refresher import MemoryProfileRefresher


class MemoryWritebackWorker:
    def __init__(
        self,
        db: BaseDatabase,
        *,
        max_queue_size: int = 256,
    ) -> None:
        self.db = db
        self.extractor = MemoryFactExtractor()
        self.episode_builder = MemoryEpisodeBuilder()
        self.profile_refresher = MemoryProfileRefresher(db)
        self.queue: asyncio.Queue[MemoryWritebackItem] = asyncio.Queue(max_queue_size)
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self.run(), name="memory_writeback_worker")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, item: MemoryWritebackItem) -> bool:
        try:
            self.queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            logger.warning(
                "Memory writeback queue is full; dropping item source=%s",
                item.source_message_id,
            )
            return False

    async def run(self) -> None:
        while not self._stopping.is_set():
            item = await self.queue.get()
            try:
                await self.process(item)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Memory writeback failed for source=%s: %s",
                    item.source_message_id,
                    exc,
                    exc_info=True,
                )
            finally:
                self.queue.task_done()

    async def process(self, item: MemoryWritebackItem) -> int:
        facts = self.extractor.extract(item.user_text)
        written = 0
        for fact in facts:
            stored, created = await self.db.upsert_memory_fact(
                person_id=item.person_id,
                chat_id=item.chat_id,
                scope_id=item.scope_id,
                fact_text=fact.fact_text,
                fact_type=fact.fact_type,
                source_message_id=item.source_message_id,
                evidence_message_ids=item.evidence_message_ids
                or [item.source_message_id],
                confidence=fact.confidence,
            )
            written += 1
            await self.db.insert_memory_operation_log(
                operator="memory_writeback_worker",
                target_type="memory_fact",
                target_id=str(stored.id),
                action="create" if created else "merge",
                reason="post_turn_fact_extraction",
                payload={
                    "person_id": item.person_id,
                    "chat_id": item.chat_id,
                    "source_message_id": item.source_message_id,
                },
            )
        episode = self.episode_builder.build(
            person_id=item.person_id,
            chat_id=item.chat_id,
            user_text=item.user_text,
            assistant_text=item.assistant_text,
            source_message_id=item.source_message_id,
            facts=facts,
        )
        if episode is not None:
            stored_episode = await self.db.upsert_memory_episode(
                episode_id=episode.episode_id,
                chat_id=item.chat_id,
                scope_id=item.scope_id,
                title=episode.title,
                summary=episode.summary,
                participant_ids=episode.participant_ids,
                source_message_ids=episode.source_message_ids,
            )
            await self.db.insert_memory_operation_log(
                operator="memory_writeback_worker",
                target_type="memory_episode",
                target_id=str(stored_episode.id),
                action="upsert",
                reason="post_turn_episode_build",
                payload={
                    "chat_id": item.chat_id,
                    "scope_id": item.scope_id,
                    "source_message_id": item.source_message_id,
                },
            )
        if written:
            await self.profile_refresher.refresh(
                person_id=item.person_id,
                chat_scope=item.scope_id,
            )
        return written
