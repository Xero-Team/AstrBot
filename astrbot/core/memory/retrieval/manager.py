from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import MemoryEpisode, MemoryFact, MemoryProfile
from astrbot.core.memory.policy import MemoryScopePolicy, ScopeResolution

from .ranker import score_text


class MemoryRetrievalManager:
    def __init__(
        self,
        db: BaseDatabase,
        scope_policy: MemoryScopePolicy | None = None,
    ) -> None:
        self.db = db
        self.scope_policy = scope_policy or MemoryScopePolicy()

    async def resolve_scope(self, chat_id: str) -> ScopeResolution:
        scope = self.scope_policy.resolve(chat_id)
        policies = await self.db.list_memory_scope_policies(
            owner_scope_id=scope.scope_id,
            enabled=True,
        )
        allowed_chat_ids = list(scope.allowed_chat_ids)
        for policy in policies:
            if policy.sharing_mode not in {"group-shared", "global-shared"}:
                continue
            if not policy.target_scope_id.startswith("isolated:"):
                continue
            target_chat_id = policy.target_scope_id.removeprefix("isolated:")
            if target_chat_id not in allowed_chat_ids:
                allowed_chat_ids.append(target_chat_id)
        return ScopeResolution(
            scope_id=scope.scope_id,
            allowed_chat_ids=allowed_chat_ids,
            sharing_mode=scope.sharing_mode,
        )

    async def search(
        self,
        *,
        person_id: str,
        chat_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryFact]:
        scope = await self.resolve_scope(chat_id)
        facts = await self.db.list_memory_facts(
            person_id=person_id,
            chat_ids=scope.allowed_chat_ids,
            limit=max(limit * 3, limit),
        )
        if query:
            scored = [
                (score_text(query, fact.fact_text), fact)
                for fact in facts
                if score_text(query, fact.fact_text) > 0
            ]
            scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
            facts = [fact for _, fact in scored]
        return facts[:limit]

    async def get_profile(
        self,
        *,
        person_id: str,
        chat_id: str,
    ) -> MemoryProfile | None:
        scope = self.scope_policy.resolve(chat_id)
        return await self.db.get_memory_profile(person_id, scope.scope_id)

    async def search_episodes(
        self,
        *,
        chat_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryEpisode]:
        scope = await self.resolve_scope(chat_id)
        episodes = await self.db.list_memory_episodes(
            chat_ids=scope.allowed_chat_ids,
            limit=max(limit * 3, limit),
        )
        if query:
            scored = [
                (score_text(query, f"{episode.title} {episode.summary}"), episode)
                for episode in episodes
                if score_text(query, f"{episode.title} {episode.summary}") > 0
            ]
            scored.sort(key=lambda item: (item[0], item[1].end_at), reverse=True)
            episodes = [episode for _, episode in scored]
        return episodes[:limit]
