import re
from collections import Counter

from astrbot.core.db import BaseDatabase


class JargonLearner:
    _TERM_RE = re.compile(
        r"(?:#([A-Za-z0-9_\-\u4e00-\u9fff]{2,32})|`([^`]{2,32})`|「([^」]{2,32})」)"
    )

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def learn(
        self,
        *,
        persona_id: str,
        scope: str,
        user_text: str,
        source_message_id: str,
    ) -> None:
        terms: list[str] = []
        for match in self._TERM_RE.finditer(user_text or ""):
            term = next(group for group in match.groups() if group)
            terms.append(term.strip())
        for term, count in Counter(terms).items():
            if count < 2:
                continue
            await self.db.upsert_persona_jargon_asset(
                persona_id=persona_id,
                scope=scope,
                term=term,
                meaning=None,
                source_message_id=source_message_id,
                score=min(0.5 + count * 0.1, 0.9),
                approved=False,
            )
