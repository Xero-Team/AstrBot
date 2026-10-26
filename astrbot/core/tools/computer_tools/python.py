import platform
from dataclasses import dataclass, field
from typing import Any, cast

import mcp

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext, AstrMessageEvent
from astrbot.core.computer.process_sandbox import SandboxSpec
from astrbot.core.message.message_event_result import MessageChain

from ..registry import builtin_tool
from .fs import _read_allowed_roots, _write_allowed_roots
from .util import (
    check_local_execution_permission,
    workspace_root,
)

_OS_NAME = platform.system()
_LOCAL_PYTHON_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "local",
}

param_schema = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "The Python code to execute.",
        },
        "silent": {
            "type": "boolean",
            "description": "Whether to suppress the output of the code execution.",
            "default": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Optional timeout in seconds for code execution.",
            "default": 30,
        },
    },
    "required": ["code"],
}


async def handle_result(
    result: dict, event: AstrMessageEvent
) -> mcp.types.CallToolResult:
    data = result.get("data", {})
    output = data.get("output", {})
    error = data.get("error", "")
    images: list[dict] = output.get("images", [])
    text: str = output.get("text", "")

    resp = mcp.types.CallToolResult(content=[])

    if error:
        resp.content.append(mcp.types.TextContent(type="text", text=f"error: {error}"))

    if images:
        for img in images:
            resp.content.append(
                mcp.types.ImageContent(
                    type="image", data=img["image/png"], mime_type="image/png"
                )
            )

            if event.get_platform_name() == "webchat":
                await event.send(message=MessageChain().base64_image(img["image/png"]))
    if text:
        resp.content.append(mcp.types.TextContent(type="text", text=text))

    violations = data.get("violations") or []
    if violations:
        details = "; ".join(
            f"{violation.get('kind', 'policy')}: {violation.get('reason', '')}"
            + (f" ({violation['target']})" if violation.get("target") else "")
            for violation in violations
        )
        resp.content.append(
            mcp.types.TextContent(type="text", text=f"sandbox denials: {details}")
        )

    if not resp.content:
        resp.content.append(mcp.types.TextContent(type="text", text="No output."))

    return resp


@builtin_tool(config=_LOCAL_PYTHON_TOOL_CONFIG, required_actions=("tool.python_exec",))
@dataclass
class LocalPythonTool(FunctionTool):
    name: str = "astrbot_execute_python"
    description: str = (
        f"Execute codes in a Python environment. Current OS: {_OS_NAME}. "
        "Use system-compatible commands. Restricted Linux and macOS calls run "
        "inside an operating-system sandbox."
    )

    parameters: dict = field(default_factory=lambda: param_schema)

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs: Any,
    ) -> ToolExecResult:
        code: str = kwargs["code"]
        silent: bool = kwargs.get("silent", False)
        timeout_seconds: int = kwargs.get("timeout_seconds", 30)
        local_policy, permission_error = await check_local_execution_permission(
            context,
            "Python execution",
        )
        if permission_error:
            return permission_error
        if local_policy is None:
            return "Error executing code: only local runtime is supported."
        sandboxed = local_policy.requires_sandbox
        sb = context.context.context.computer_runtime.get_local_booter()
        requested_timeout = kwargs.get("timeout")
        if requested_timeout is None:
            requested_timeout = timeout_seconds
        effective_timeout = (
            min(requested_timeout, context.tool_call_timeout)
            if requested_timeout > 0
            else context.tool_call_timeout
        )
        if sandboxed:
            effective_timeout = min(effective_timeout, 300)
        try:
            current_workspace_root = workspace_root(
                context.context.event.unified_msg_origin
            )
            current_workspace_root.mkdir(parents=True, exist_ok=True)
            python_component = cast(Any, sb.python)
            spec = None
            if sandboxed:
                umo = context.context.event.unified_msg_origin
                spec = SandboxSpec(
                    workspace=current_workspace_root,
                    policy=local_policy.sandbox,
                    readable_roots=(
                        _read_allowed_roots(umo)
                        if local_policy.filesystem_scope == "workspace"
                        else ()
                    ),
                    writable_roots=(
                        _write_allowed_roots(umo)
                        if local_policy.filesystem_scope == "workspace"
                        else ()
                    ),
                )
            result = await python_component.exec(
                code,
                timeout_seconds=effective_timeout,
                silent=silent,
                cwd=str(current_workspace_root),
                spec=spec,
            )
            return await handle_result(result, context.context.event)
        except Exception as e:
            return f"Error executing code: {str(e)}"
