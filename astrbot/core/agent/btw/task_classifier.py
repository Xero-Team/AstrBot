"""Rule-based task classification for the BTW prototype."""

import re
from collections.abc import Mapping

from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .types import TaskType

DEFAULT_WORK_KEYWORDS = (
    "写代码",
    "生成代码",
    "修改代码",
    "重构",
    "创建文件",
    "修改文件",
    "读取文件",
    "执行命令",
    "运行命令",
    "代码代理",
    "编程代理",
    "write code",
    "generate code",
    "refactor",
    "create file",
    "modify file",
    "run command",
    "claude code",
    "claudecode",
    "codex",
    "opencode",
    "coding agent",
    "vibe coding",
    "hapi",
)

# CJK has no whitespace word boundaries, so only latin/digit keywords get
# token-boundary matching; CJK keywords still use substring matching.
_LATIN_KEYWORD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _keyword_matches(keyword: str, message: str) -> bool:
    """Match one keyword against the lowercased message.

    Latin/ASCII keywords require a word boundary so that e.g. ``search`` does
    not fire inside ``research``.  CJK keywords (no whitespace boundaries)
    fall back to substring matching.
    """
    if re.fullmatch(r"[\W一-鿿]+", keyword, re.ASCII) is None:
        # keyword contains at least one ASCII letter/digit: boundary match
        pattern = _LATIN_KEYWORD_RE_CACHE.get(keyword)
        if pattern is None:
            pattern = re.compile(
                r"(?<![0-9a-z])" + re.escape(keyword) + r"(?![0-9a-z])"
            )
            _LATIN_KEYWORD_RE_CACHE[keyword] = pattern
        return pattern.search(message) is not None
    return keyword in message


class TaskClassifier:
    """Classify a request without an additional model call.

    The prototype deliberately uses deterministic rules.  A future classifier
    may replace this implementation behind the same interface without changing
    the conversation-loop entry point.  Classification is opt-in on every
    layer: when ``btw.enabled``, ``btw.classifier.enabled``, or
    ``btw.work_loop.enabled`` is false, the classifier never assigns work.
    """

    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config

    async def classify(self, event: AstrMessageEvent) -> TaskType:
        """Return the loop appropriate for an event.

        Args:
            event: The incoming message event.

        Returns:
            The selected task type.
        """
        btw = self.config.get("btw", {})
        if not isinstance(btw, Mapping) or not btw.get("enabled", False):
            return TaskType.CONVERSATION

        work_loop = btw.get("work_loop", {})
        if not isinstance(work_loop, Mapping) or not work_loop.get("enabled", False):
            return TaskType.CONVERSATION

        message = (event.message_str or "").strip().lower()
        if message.startswith("/work"):
            return TaskType.WORK

        classifier = btw.get("classifier", {})
        if not isinstance(classifier, Mapping) or not classifier.get("enabled", False):
            return TaskType.CONVERSATION
        keywords = classifier.get("work_keywords", DEFAULT_WORK_KEYWORDS)
        if not isinstance(keywords, list | tuple):
            keywords = DEFAULT_WORK_KEYWORDS
        if any(
            isinstance(keyword, str)
            and keyword.strip()
            and _keyword_matches(keyword.strip(), message)
            for keyword in keywords
        ):
            return TaskType.WORK
        return TaskType.CONVERSATION
