from astrbot.core.db.protocols import MemoryStore


class MemoryProfileRefresher:
    def __init__(self, db: MemoryStore) -> None:
        self.db = db

    async def refresh(self, *, person_id: str, chat_scope: str) -> str | None:
        chat_id = chat_scope.removeprefix("isolated:")
        facts = await self.db.list_memory_facts(
            person_id=person_id,
            chat_ids=[chat_id],
            limit=20,
        )
        if not facts:
            await self.db.upsert_memory_profile(
                person_id=person_id,
                chat_scope=chat_scope,
                profile_text="",
            )
            return None
        lines = [f"- {fact.fact_text}" for fact in facts[:8]]
        profile_text = "Known user profile in this isolated chat:\n" + "\n".join(lines)
        await self.db.upsert_memory_profile(
            person_id=person_id,
            chat_scope=chat_scope,
            profile_text=profile_text,
        )
        return profile_text
