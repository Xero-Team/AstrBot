from types import SimpleNamespace

import pytest

from astrbot.core.agent.btw.task_classifier import TaskClassifier
from astrbot.core.agent.btw.types import TaskType


@pytest.mark.asyncio
async def test_task_classifier_selects_work_for_keywords_and_conversation_otherwise():
    # Keyword heuristics are opt-in: nothing is enabled by default.
    disabled = TaskClassifier(
        {"btw": {"enabled": True, "work_loop": {"enabled": True}}}
    )
    assert (
        await disabled.classify(SimpleNamespace(message_str="帮我修改代码"))
        is TaskType.CONVERSATION
    )
    assert (
        await disabled.classify(SimpleNamespace(message_str="continue with Codex"))
        is TaskType.CONVERSATION
    )

    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": True},
                "work_loop": {"enabled": True},
            }
        }
    )

    assert (
        await classifier.classify(SimpleNamespace(message_str="你好"))
        is TaskType.CONVERSATION
    )
    assert (
        await classifier.classify(SimpleNamespace(message_str="帮我修改代码"))
        is TaskType.WORK
    )
    assert (
        await classifier.classify(
            SimpleNamespace(message_str="让 Claude Code 处理这个仓库")
        )
        is TaskType.WORK
    )
    assert (
        await classifier.classify(SimpleNamespace(message_str="continue with Codex"))
        is TaskType.WORK
    )


@pytest.mark.asyncio
async def test_task_classifier_defaults_exclude_everyday_queries_and_honor_word_boundaries():
    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": True},
                "work_loop": {"enabled": True},
            }
        }
    )

    # Broad everyday keywords (search/搜索/查询/research) are not in the
    # default set — they classify ordinary questions as conversation.
    assert (
        await classifier.classify(
            SimpleNamespace(message_str="search for a restaurant")
        )
        is TaskType.CONVERSATION
    )
    assert (
        await classifier.classify(
            SimpleNamespace(message_str="what is the research paper about")
        )
        is TaskType.CONVERSATION
    )
    assert (
        await classifier.classify(SimpleNamespace(message_str="帮我搜索一下附近餐厅"))
        is TaskType.CONVERSATION
    )
    # Word boundaries still hold for the keywords that remain: a keyword
    # never fires inside another word.
    assert (
        await classifier.classify(
            SimpleNamespace(message_str="search refactor helper in the codebase")
        )
        is TaskType.WORK
    )


@pytest.mark.asyncio
async def test_task_classifier_respects_disabled_work_loop():
    classifier = TaskClassifier(
        {"btw": {"enabled": True, "work_loop": {"enabled": False}}}
    )

    assert (
        await classifier.classify(SimpleNamespace(message_str="帮我修改代码"))
        is TaskType.CONVERSATION
    )


@pytest.mark.asyncio
async def test_task_classifier_does_not_treat_work_command_text_as_work():
    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": False},
                "work_loop": {"enabled": True},
            }
        }
    )

    assert (
        await classifier.classify(SimpleNamespace(message_str="/work 重构项目"))
        is TaskType.CONVERSATION
    )
    assert (
        await classifier.classify(SimpleNamespace(message_str="work 重构项目"))
        is TaskType.CONVERSATION
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("please REFACTOR this module", TaskType.WORK),
        ("refactoring is a useful technique", TaskType.CONVERSATION),
        ("precodexsuffix", TaskType.CONVERSATION),
        ("codex2", TaskType.CONVERSATION),
        ("please use (Codex)", TaskType.WORK),
        ("请修改代码以修复问题", TaskType.WORK),
        ("", TaskType.CONVERSATION),
        (None, TaskType.CONVERSATION),
        ("/work hello", TaskType.CONVERSATION),
    ],
)
async def test_task_classifier_preserves_boundaries_and_command_independence(
    message, expected
):
    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": True},
                "work_loop": {"enabled": True},
            }
        }
    )

    assert await classifier.classify(SimpleNamespace(message_str=message)) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "btw_config",
    [
        None,
        True,
        {"enabled": False, "classifier": {"enabled": True}},
        {"enabled": True, "classifier": {"enabled": True}},
        {
            "enabled": True,
            "classifier": {"enabled": True},
            "work_loop": {"enabled": False},
        },
        {"enabled": True, "classifier": True, "work_loop": {"enabled": True}},
        {
            "enabled": True,
            "classifier": {"enabled": False},
            "work_loop": {"enabled": True},
        },
    ],
)
async def test_task_classifier_requires_all_three_enabled_states(btw_config):
    classifier = TaskClassifier({"btw": btw_config})

    assert (
        await classifier.classify(SimpleNamespace(message_str="refactor this module"))
        is TaskType.CONVERSATION
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("keywords", [["  deploy  ", None, "", 1], ("deploy",)])
async def test_task_classifier_accepts_custom_keyword_sequences(keywords):
    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": True, "work_keywords": keywords},
                "work_loop": {"enabled": True},
            }
        }
    )

    assert (
        await classifier.classify(SimpleNamespace(message_str="deploy this service"))
        is TaskType.WORK
    )
    assert (
        await classifier.classify(SimpleNamespace(message_str="write code"))
        is TaskType.CONVERSATION
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("keywords", [None, True, "deploy", {}])
async def test_task_classifier_uses_defaults_for_invalid_keyword_config(keywords):
    classifier = TaskClassifier(
        {
            "btw": {
                "enabled": True,
                "classifier": {"enabled": True, "work_keywords": keywords},
                "work_loop": {"enabled": True},
            }
        }
    )

    assert (
        await classifier.classify(SimpleNamespace(message_str="write code"))
        is TaskType.WORK
    )
