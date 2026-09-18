"""Delegate write work from the BTW work loop to a local coding agent.

The work loop reads and plans; the tools that would let it write are removed
from its catalog.  This tool is what replaces them: the work loop describes a
complete task, a coding agent CLI carries it out inside its own task folder,
and the work loop gets back a report it can turn into an answer.
"""

from pathlib import Path

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot import logger
from astrbot.core.agent.btw import coding_runner, runtime_registry
from astrbot.core.agent.btw.coding_agents import select_coding_agent
from astrbot.core.agent.btw.types import stop_requested
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.registry import builtin_tool
from astrbot.core.utils.error_redaction import safe_error

DELEGATE_CODING_TASK_TOOL_NAME = "delegate_coding_task"

NO_AGENT_REPLY = (
    "error: no coding agent is available for this work loop, so nothing can "
    "write files here. Delegation needs an enabled entry under "
    "btw.work_loop.coding_agents and a work loop whose Computer Use runtime is "
    "local; a sandboxed work loop runs its work in the sandbox, so it delegates "
    "to nothing. Answer from what you can read instead, and tell the user that "
    "a coding agent has to be configured for work that changes files."
)


def _relative_artifacts(workspace: Path, root: Path, artifacts: list[str]) -> list[str]:
    """Return the run's artifacts relative to the configured workspace root.

    The report this list ends up in is delivered to the user, so it must not
    spell out where AstrBot keeps its data on this host.  The task folder's own
    place inside the root is kept, because that is the part the user needs to
    find the files.
    """
    relative: list[str] = []
    for artifact in artifacts:
        path = workspace / artifact
        try:
            relative.append(path.relative_to(root).as_posix())
        except ValueError:
            # A ``project_dir`` outside the workspace root has no relative name
            # inside it; the file's own name is still worth reporting.
            relative.append(Path(artifact).as_posix())
    return relative


def _format_report(result: coding_runner.CodingTaskResult, agent, root: Path) -> str:
    """Return the report the work loop reads back as the tool's result."""
    lines = [
        f"status: {result.status}",
        f"agent: {agent.get('name')} ({agent.get('id')})",
        f"folder: {result.workspace.name}",
    ]
    if result.exit_code is not None:
        lines.append(f"exit_code: {result.exit_code}")
    if result.detail:
        lines.append(f"detail: {result.detail}")
    if result.artifacts:
        lines.append(f"artifacts ({len(result.artifacts)}):")
        lines.extend(
            f"- {path}"
            for path in _relative_artifacts(result.workspace, root, result.artifacts)
        )
    else:
        lines.append("artifacts: none reported")
    if result.output:
        lines.append("")
        lines.append("final message from the coding agent:")
        lines.append(result.output)
    return "\n".join(lines)


@builtin_tool(
    config={"btw.work_loop.enabled": True},
    # A delegated run executes a local process that writes files, so it asks
    # for exactly what a local executor asks for.  Declaring the weaker
    # ``agent.manage`` would let a session owner reach the host through a
    # coding agent that the computer-use boundary is meant to gate.
    required_actions=("tool.local_exec", "tool.file_write"),
)
@dataclass
class DelegateCodingTaskTool(FunctionTool[AstrAgentContext]):
    """Hand one self-contained write task to a local coding agent."""

    name: str = DELEGATE_CODING_TASK_TOOL_NAME
    description: str = (
        "Carry out a task that must create or change files by handing it to a "
        "coding agent on this host. The agent runs in its own task folder with "
        "write access there, so `task` must be complete on its own: state the "
        "goal, every input it needs, and the outputs you expect. This call "
        "returns when the agent finishes, and its reply names the folder and "
        "the artifacts it produced. Reading and searching, do yourself."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "The complete task for the coding agent: goal, inputs, "
                        "and expected outputs."
                    ),
                },
                "agent_id": {
                    "type": "string",
                    "description": (
                        "Which configured coding agent to use. Leave empty to "
                        "use the first enabled one."
                    ),
                },
            },
            "required": ["task"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        task: str = "",
        agent_id: str = "",
        **_: object,
    ) -> ToolExecResult:
        event = context.context.event
        execution_context = context.context.context
        profile = execution_context.get_config(umo=event.unified_msg_origin)
        agent = select_coding_agent(profile, agent_id)
        if agent is None:
            return NO_AGENT_REPLY
        task_text = task.strip()
        if not task_text:
            return "error: the task was empty; pass the complete task to carry out."
        session_id = event.get_extra("btw_work_session_id") or event.unified_msg_origin
        root = coding_runner.workspace_root(profile)
        workspace = coding_runner.task_workspace(
            root,
            str(session_id),
            str(agent["id"]),
        )
        try:
            result = await coding_runner.run_coding_task(
                agent,
                workspace=workspace,
                task=task_text,
                stop_requested=lambda: stop_requested(event),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Delegated coding task failed: %s", safe_error("", exc))
            return (
                f"error: the coding agent could not be run in {workspace.name}. "
                "Report the task as failed and say so."
            )
        await runtime_registry.record_work_artifacts(
            event, _relative_artifacts(workspace, root, result.artifacts)
        )
        return _format_report(result, agent, root)
