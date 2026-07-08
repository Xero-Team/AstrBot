import re

from astrbot.core.memory.models import ExtractedMemoryFact


class MemoryFactExtractor:
    _PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
        (
            re.compile(r"\b(?:i like|i love)\s+([^.!?\n]{2,80})", re.I),
            "preference",
            "User likes {value}.",
        ),
        (
            re.compile(r"\b(?:i dislike|i hate)\s+([^.!?\n]{2,80})", re.I),
            "preference",
            "User dislikes {value}.",
        ),
        (
            re.compile(r"\bmy name is\s+([^.!?\n]{2,60})", re.I),
            "identity",
            "User name is {value}.",
        ),
        (
            re.compile(r"我(?:喜欢|爱)\s*([^。！？\n]{1,40})"),
            "preference",
            "用户喜欢{value}。",
        ),
        (
            re.compile(r"我(?:讨厌|不喜欢)\s*([^。！？\n]{1,40})"),
            "preference",
            "用户不喜欢{value}。",
        ),
        (
            re.compile(r"我叫\s*([^。！？\n]{1,30})"),
            "identity",
            "用户名字是{value}。",
        ),
    )

    def extract(self, text: str) -> list[ExtractedMemoryFact]:
        facts: list[ExtractedMemoryFact] = []
        seen: set[str] = set()
        for pattern, fact_type, template in self._PATTERNS:
            for match in pattern.finditer(text or ""):
                value = match.group(1).strip(" ，,。.!?？")
                if not value:
                    continue
                fact_text = template.format(value=value)
                key = fact_text.casefold()
                if key in seen:
                    continue
                seen.add(key)
                facts.append(
                    ExtractedMemoryFact(
                        fact_text=fact_text,
                        fact_type=fact_type,
                        confidence=0.72 if fact_type == "identity" else 0.64,
                    )
                )
        return facts
