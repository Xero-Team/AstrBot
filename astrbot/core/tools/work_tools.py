"""Hand an explicit task from the conversation loop to the BTW work loop."""

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.btw.submission import submit_work_task
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.registry import builtin_tool

SUBMIT_WORK_TASK_TOOL_NAME = "submit_work_task"


@builtin_tool(
    config={"btw.work_loop.enabled": True},
    required_actions=("agent.manage",),
)
@dataclass
class SubmitWorkTaskTool(FunctionTool[AstrAgentContext]):
    """Submit one self-contained task to the work loop."""

    name: str = SUBMIT_WORK_TASK_TOOL_NAME
    description: str = (
        "Hand a self-contained task to the work loop. It runs in the "
        "background with its own tools and reports the result to the user in "
        "this session later, so this call returns before the task is done. "
        "`prompt` is the complete task: the work loop does not read this "
        "conversation, so include every detail it needs. Use `send_message_to_user` "
        "instead when the user only wants a reply from you."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The complete task for the work loop to carry out.",
                },
            },
            "required": ["prompt"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        prompt: str = "",
        **_: object,
    ) -> ToolExecResult:
        event = context.context.event
        session = await submit_work_task(
            context.context.context,
            event,
            prompt,
        )
        if session is None:
            return (
                "error: no work loop is available for this profile, or the task "
                "was empty. Answer the user directly instead."
            )
        return (
            "Work task submitted. The work loop runs it in the background and "
            "reports the result to the user in this session when it finishes."
        )
