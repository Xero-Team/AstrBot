from astrbot.core.db import BaseDatabase


class ExpressionLearner:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def learn(
        self,
        *,
        persona_id: str,
        scope: str,
        user_text: str,
        assistant_text: str,
        source_message_id: str,
    ) -> None:
        text = (assistant_text or "").strip()
        if not text:
            return

        trigger_scene = (
            "question" if user_text.rstrip().endswith(("?", "？")) else "general"
        )
        if len(text) <= 80:
            await self.db.upsert_persona_expression_asset(
                persona_id=persona_id,
                scope=scope,
                trigger_scene=trigger_scene,
                style_text="Prefer concise direct replies in similar scenes.",
                source_message_id=source_message_id,
                score=0.58,
            )
        if "\n" in text or any(marker in text for marker in ("- ", "1. ")):
            await self.db.upsert_persona_expression_asset(
                persona_id=persona_id,
                scope=scope,
                trigger_scene="explanation",
                style_text="Use structured multi-line replies when explaining steps.",
                source_message_id=source_message_id,
                score=0.62,
            )
