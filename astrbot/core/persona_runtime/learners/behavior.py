from astrbot.core.db import BaseDatabase


class BehaviorLearner:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def learn(
        self,
        *,
        persona_id: str,
        scope: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        user_text = (user_text or "").strip()
        assistant_text = (assistant_text or "").strip()
        if not user_text or not assistant_text:
            return
        if user_text.endswith(("?", "？")) and assistant_text.endswith(("?", "？")):
            await self.db.upsert_persona_behavior_policy(
                persona_id=persona_id,
                scope=scope,
                situation="user question lacks enough detail",
                preferred_action="Ask one concise clarifying question before proceeding.",
                avoid_action="Do not invent missing requirements.",
                confidence=0.58,
            )
        elif len(assistant_text) <= 80:
            await self.db.upsert_persona_behavior_policy(
                persona_id=persona_id,
                scope=scope,
                situation="straightforward user request",
                preferred_action="Answer briefly and directly.",
                avoid_action="Do not over-explain simple answers.",
                confidence=0.54,
            )
