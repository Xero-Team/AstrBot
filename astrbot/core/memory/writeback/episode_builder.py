import hashlib

from astrbot.core.memory.models import ExtractedMemoryFact, MemoryEpisodeCandidate


class MemoryEpisodeBuilder:
    def build(
        self,
        *,
        person_id: str,
        chat_id: str,
        user_text: str,
        assistant_text: str,
        source_message_id: str,
        facts: list[ExtractedMemoryFact],
    ) -> MemoryEpisodeCandidate | None:
        text = " ".join(part.strip() for part in [user_text, assistant_text] if part)
        if len(text) < 12 and not facts:
            return None
        digest = hashlib.sha256(f"{chat_id}:{source_message_id}".encode()).hexdigest()
        title = facts[0].fact_text if facts else text[:80]
        summary_parts = []
        if user_text:
            summary_parts.append(f"User: {user_text[:180]}")
        if assistant_text:
            summary_parts.append(f"Assistant: {assistant_text[:180]}")
        if facts:
            summary_parts.append(
                "Facts: " + "; ".join(fact.fact_text for fact in facts[:3])
            )
        return MemoryEpisodeCandidate(
            episode_id=digest[:32],
            title=title[:255],
            summary="\n".join(summary_parts),
            participant_ids=[person_id],
            source_message_ids=[source_message_id],
        )
