"""Rule-based task classification for the BTW prototype."""

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
    "搜索",
    "查询",
    "调研",
    "代码代理",
    "编程代理",
    "write code",
    "generate code",
    "refactor",
    "create file",
    "modify file",
    "run command",
    "search",
    "research",
    "claude code",
    "claudecode",
    "codex",
    "opencode",
    "coding agent",
    "vibe coding",
    "hapi",
)


class TaskClassifier:
    """Classify a request without an additional model call.

    The prototype deliberately uses deterministic rules.  A future classifier
    may replace this implementation behind the same interface without changing
    the conversation-loop entry point.
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
        if not isinstance(btw, Mapping) or not btw.get("enabled", True):
            return TaskType.CONVERSATION

        work_loop = btw.get("work_loop", {})
        if not isinstance(work_loop, Mapping) or not work_loop.get("enabled", True):
            return TaskType.CONVERSATION

        message = (event.message_str or "").strip().lower()
        if message.startswith("/work"):
            return TaskType.WORK

        classifier = btw.get("classifier", {})
        if not isinstance(classifier, Mapping) or not classifier.get("enabled", True):
            return TaskType.CONVERSATION
        keywords = classifier.get("work_keywords", DEFAULT_WORK_KEYWORDS)
        if not isinstance(keywords, list | tuple):
            keywords = DEFAULT_WORK_KEYWORDS
        if any(
            isinstance(keyword, str) and keyword.strip() in message
            for keyword in keywords
        ):
            return TaskType.WORK
        return TaskType.CONVERSATION
