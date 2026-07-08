from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.db.po import MemoryFact
from astrbot.core.tools.registry import builtin_tool


def _format_fact(fact: MemoryFact) -> str:
    return (
        f"- [fact_id={fact.id} status={fact.status} "
        f"confidence={float(fact.confidence):.2f}] {fact.fact_text}"
    )


@builtin_tool
@dataclass
class SearchMemoryTool(FunctionTool[AstrAgentContext]):
    name: str = "search_memory"
    description: str = (
        "Search long-term memory facts for the current user in the current chat scope. "
        "Use concise keywords. Memories are isolated by default."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise memory search query.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum facts to return.",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        memory_manager = getattr(context.context.context, "memory_manager", None)
        if memory_manager is None:
            return "Memory manager is not initialized."
        event = context.context.event
        person_id = memory_manager.resolve_person_id(event)
        facts = await memory_manager.retrieval.search(
            person_id=person_id,
            chat_id=event.unified_msg_origin,
            query=str(kwargs.get("query", "")),
            limit=int(kwargs.get("limit", 5) or 5),
        )
        if not facts:
            return "No matching memory found."
        return "\n".join(_format_fact(fact) for fact in facts)


@builtin_tool
@dataclass
class GetPersonProfileTool(FunctionTool[AstrAgentContext]):
    name: str = "get_person_profile"
    description: str = "Get the aggregated long-term memory profile for the current user in the current chat scope."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        memory_manager = getattr(context.context.context, "memory_manager", None)
        if memory_manager is None:
            return "Memory manager is not initialized."
        event = context.context.event
        profile = await memory_manager.retrieval.get_profile(
            person_id=memory_manager.resolve_person_id(event),
            chat_id=event.unified_msg_origin,
        )
        if not profile:
            return "No memory profile found."
        return profile.profile_text


@builtin_tool
@dataclass
class QueryEpisodeTool(FunctionTool[AstrAgentContext]):
    name: str = "query_episode"
    description: str = (
        "Search compact long-term memory episodes for the current chat scope. "
        "Use this for event-style recall such as what happened last time."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise episode search query.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum episodes to return.",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        memory_manager = getattr(context.context.context, "memory_manager", None)
        if memory_manager is None:
            return "Memory manager is not initialized."
        event = context.context.event
        episodes = await memory_manager.retrieval.search_episodes(
            chat_id=event.unified_msg_origin,
            query=str(kwargs.get("query", "")),
            limit=int(kwargs.get("limit", 3) or 3),
        )
        if not episodes:
            return "No matching episode found."
        return "\n".join(
            f"- {episode.title}: {episode.summary}" for episode in episodes
        )


@builtin_tool
@dataclass
class MaintainMemoryTool(FunctionTool[AstrAgentContext]):
    name: str = "maintain_memory"
    description: str = (
        "Preview, soft-delete, or restore a long-term memory fact for the current user in the current chat scope. "
        "Preview can search by query or target_text without changing data. Delete and restore require fact_id."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "fact_id": {
                    "type": "integer",
                    "description": "The memory fact ID returned by memory search or management UI.",
                    "minimum": 1,
                },
                "action": {
                    "type": "string",
                    "enum": ["preview", "delete", "restore"],
                    "description": "Maintenance action to perform.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for preview candidates.",
                },
                "target_text": {
                    "type": "string",
                    "description": "Target memory text to preview before deleting.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum preview candidates to return.",
                    "minimum": 1,
                    "maximum": 10,
                },
                "reason": {
                    "type": "string",
                    "description": "Short reason for audit log.",
                },
            },
            "required": ["action"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs,
    ) -> ToolExecResult:
        memory_manager = getattr(context.context.context, "memory_manager", None)
        if memory_manager is None:
            return "Memory manager is not initialized."
        event = context.context.event
        action = str(kwargs.get("action", ""))
        if action not in {"preview", "delete", "restore"}:
            return "error: action must be preview, delete, or restore."
        person_id = memory_manager.resolve_person_id(event)
        if action == "preview":
            query = str(kwargs.get("query") or kwargs.get("target_text") or "").strip()
            if not query:
                return "error: query or target_text is required for preview."
            limit = min(max(int(kwargs.get("limit", 5) or 5), 1), 10)
            facts = await memory_manager.retrieval.db.list_memory_facts(
                person_id=person_id,
                chat_ids=[event.unified_msg_origin],
                query=query,
                status=None,
                limit=limit,
            )
            if not facts:
                return "No matching memory candidate found."
            return "\n".join(_format_fact(fact) for fact in facts)

        fact_id = int(kwargs.get("fact_id", 0) or 0)
        if fact_id <= 0:
            return "error: fact_id is required for delete or restore."
        fact = await memory_manager.retrieval.db.get_memory_fact(fact_id)
        if fact is None:
            return "Memory fact not found."
        if fact.person_id != person_id or fact.chat_id != event.unified_msg_origin:
            return "Memory fact is outside the current user's isolated memory scope."
        ok = await memory_manager.retrieval.db.update_memory_fact_status(
            fact_id,
            status="deleted" if action == "delete" else "active",
            operator="maintain_memory_tool",
            reason=str(kwargs.get("reason", "") or action),
        )
        if not ok:
            return "Memory fact not found."
        return f"Memory fact {fact_id} {action}d."
