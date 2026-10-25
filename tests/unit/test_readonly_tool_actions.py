from astrbot.core.auth.models import Role
from astrbot.core.auth.registry import ACTION_POLICIES, ROLE_TO_RELATION
from astrbot.core.memory.tools.memory_tools import QueryEpisodeTool, SearchMemoryTool
from astrbot.core.tools.knowledge_base_tools import KnowledgeBaseQueryTool
from astrbot.core.tools.registry import BUILTIN_TOOL_DECLARATION_ATTR


def _declared_actions(tool_cls):
    return getattr(tool_cls, BUILTIN_TOOL_DECLARATION_ATTR).required_actions


def test_knowledge_base_query_tool_declares_read_action():
    assert _declared_actions(KnowledgeBaseQueryTool) == ("tool.kb_read",)


def test_memory_search_tools_declare_read_action():
    assert _declared_actions(SearchMemoryTool) == ("tool.memory_read",)
    assert _declared_actions(QueryEpisodeTool) == ("tool.memory_read",)


def test_kb_read_action_is_available_to_members():
    policy = ACTION_POLICIES["tool.kb_read"]

    assert ROLE_TO_RELATION[Role.MEMBER] in policy.relations
