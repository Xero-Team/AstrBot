import asyncio
import json
import os
import shlex
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.booters.local import LocalShellComponent
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path

from ..registry import builtin_tool
from .fs import _read_allowed_roots, _write_allowed_roots
from .util import (
    check_local_execution_permission,
    get_local_permission_policy,
    is_local_runtime,
    workspace_root,
)

_LOCAL_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "local",
}


def _quote_redirect_path(path: str, *, local_runtime: bool) -> str:
    if local_runtime and os.name == "nt":
        escaped_path = path.replace('"', '""')
    else:
        escaped_path = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped_path}"'


def _build_background_output_path() -> str:
    file_name = f"astrbot_shell_stdout_{uuid.uuid4().hex[:8]}.log"
    output_dir = Path(get_astrbot_system_tmp_path()) / "shell"
    output_dir.mkdir(parents=True, exist_ok=True)
    return str((output_dir / file_name).resolve(strict=False))


def _redirect_background_stdout_command(
    command: str,
    *,
    output_path: str,
    local_runtime: bool,
) -> str:
    return f"({command}) > {_quote_redirect_path(output_path, local_runtime=local_runtime)} 2>&1"


@builtin_tool(config=_LOCAL_RUNTIME_TOOL_CONFIG, required_actions=("tool.local_exec",))
@dataclass
class ExecuteShellTool(FunctionTool):
    name: str = "astrbot_execute_shell"
    description: str = "Execute a command in the shell."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute in the current runtime shell (for example, cmd.exe on Windows). Equal to 'cd {working_dir} && {your_command}'.",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run the command in the background. Use the file read tool to read the output later. For long running commands, using this option.",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in seconds for the command execution.",
                    "default": 300,
                },
                "yield_time_ms": {
                    "type": "integer",
                    "description": "Maximum time to wait before returning a managed local session.",
                    "default": 10000,
                    "minimum": 0,
                    "maximum": 300000,
                },
                "env": {
                    "type": "object",
                    "description": "Optional environment variables to set.",
                    "additionalProperties": {"type": "string"},
                    "default": {},
                },
            },
            "required": ["command"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs: Any,
    ) -> ToolExecResult:
        command: str = kwargs["command"]
        background: bool = kwargs.get("background", False)
        timeout_seconds: int | None = kwargs.get("timeout")
        env: dict[str, Any] | None = kwargs.get("env", None)
        yield_time_ms: int = kwargs.get("yield_time_ms", 10_000)
        local_policy, permission_error = await check_local_execution_permission(
            context,
            "Shell execution",
        )
        if permission_error:
            return permission_error
        if not is_local_runtime(context):
            return "Error executing command: only local runtime is supported."
        sandboxed = bool(local_policy and local_policy.requires_sandbox)
        sb = context.context.context.computer_runtime.get_local_booter()
        try:
            current_workspace_root = workspace_root(
                context.context.event.unified_msg_origin
            )
            current_workspace_root.mkdir(parents=True, exist_ok=True)
            cwd = str(current_workspace_root)

            shell_component = sb.shell
            if not isinstance(shell_component, LocalShellComponent):
                return "Error executing command: local shell component is unavailable."
            creator_id = str(context.context.event.get_sender_id())
            creator_is_admin = (
                get_local_permission_policy(context).filesystem_scope == "host"
                or local_policy is not None
                and local_policy.allow_network
                and not local_policy.requires_sandbox
            )
            umo = context.context.event.unified_msg_origin
            workspace_scope = (
                local_policy is not None
                and local_policy.filesystem_scope == "workspace"
            )
            requested_timeout = timeout_seconds
            result = await shell_component.exec_managed(
                command,
                owner_id=context.context.event.unified_msg_origin,
                runtime_id="local",
                sender_id=creator_id,
                creator_is_admin=creator_is_admin,
                sandboxed=sandboxed,
                permission_check=lambda: (
                    is_local_runtime(context)
                    and get_local_permission_policy(context) == local_policy
                ),
                allow_network=(local_policy.allow_network if local_policy else True),
                filesystem_scope=(
                    local_policy.filesystem_scope if local_policy else "host"
                ),
                cwd=cwd,
                env=dict(env or {}),
                timeout=(
                    min(requested_timeout or 300, 300)
                    if sandboxed
                    else requested_timeout
                ),
                yield_time_ms=0 if background else yield_time_ms,
                allowed_root=str(current_workspace_root),
                readable_roots=_read_allowed_roots(umo) if workspace_scope else (),
                writable_roots=_write_allowed_roots(umo) if workspace_scope else (),
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error executing command: {detail}"


@builtin_tool(config=_LOCAL_RUNTIME_TOOL_CONFIG, required_actions=("tool.local_exec",))
@dataclass
class ShellSessionTool(FunctionTool):
    """Manage sessions created by the local shell execution tool."""

    name: str = "astrbot_shell_session"
    description: str = (
        "List, poll, write raw text or complete lines to, interrupt, or terminate "
        "managed shell sessions "
        "owned by the current conversation."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "poll",
                        "write",
                        "write_line",
                        "interrupt",
                        "terminate",
                    ],
                },
                "session_id": {"type": "string"},
                "chars": {"type": "string", "default": ""},
                "cursor": {"type": "integer", "minimum": 0},
                "yield_time_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 300_000,
                    "default": 5_000,
                },
                "max_output_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100_000,
                    "default": 10_000,
                },
            },
            "required": ["action"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        **kwargs: Any,
    ) -> ToolExecResult:
        action: str = kwargs["action"]
        session_id: str | None = kwargs.get("session_id", None)
        chars: str = kwargs.get("chars", "")
        cursor: int | None = kwargs.get("cursor", None)
        yield_time_ms: int = kwargs.get("yield_time_ms", 5_000)
        max_output_chars: int = kwargs.get("max_output_chars", 10_000)
        _, permission_error = await check_local_execution_permission(
            context,
            "Shell session management",
        )
        if permission_error and action != "terminate":
            return permission_error
        if not is_local_runtime(context) and action != "terminate":
            return "Error managing shell session: only local runtime is supported."
        owner_id = context.context.event.unified_msg_origin
        sender_id = str(context.context.event.get_sender_id())
        try:
            booter = context.context.context.computer_runtime.get_local_booter()
            if not isinstance(booter.shell, LocalShellComponent):
                return "Error managing shell session: local shell component is unavailable."
            shell = booter.shell
            if action == "list":
                result = await shell.list_sessions(owner_id, sender_id=sender_id)
            else:
                if not session_id:
                    return "Error managing shell session: session_id is required."
                if action in {"poll", "write", "write_line"}:
                    written = None
                    if action in {"write", "write_line"}:
                        if yield_time_ms < 0 or yield_time_ms > 300_000:
                            raise ValueError(
                                "`yield_time_ms` must be between 0 and 300000."
                            )
                        if max_output_chars < 1:
                            raise ValueError(
                                "`max_output_chars` must be greater than 0."
                            )
                        if cursor is not None and cursor < 0:
                            raise ValueError(
                                "`cursor` must be greater than or equal to 0."
                            )
                        written = await shell.write_session(
                            owner_id=owner_id,
                            session_id=session_id,
                            chars=f"{chars}\n" if action == "write_line" else chars,
                            sender_id=sender_id,
                        )
                    result = await shell.poll_session(
                        owner_id=owner_id,
                        session_id=session_id,
                        cursor=cursor,
                        yield_time_ms=yield_time_ms,
                        max_output_chars=max_output_chars,
                        sender_id=sender_id,
                    )
                    if written is not None:
                        result["written_chars"] = written["written_chars"]
                elif action == "interrupt":
                    result = await shell.interrupt_session(
                        owner_id=owner_id,
                        session_id=session_id,
                        yield_time_ms=yield_time_ms,
                        max_output_chars=max_output_chars,
                        sender_id=sender_id,
                    )
                elif action == "terminate":
                    result = await shell.terminate_session(
                        owner_id=owner_id,
                        session_id=session_id,
                        max_output_chars=max_output_chars,
                        sender_id=sender_id,
                    )
                else:
                    return f"Error managing shell session: unsupported action {action}."
            return json.dumps(result, ensure_ascii=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            return f"Error managing shell session: {detail}"


def _is_self_detached_command(command: str) -> bool:
    lex = shlex.shlex(command, posix=False)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return False
    comment_index = next(
        (index for index, token in enumerate(tokens) if token.startswith("#")),
        None,
    )
    if comment_index is not None:
        tokens = tokens[:comment_index]
    if not tokens:
        return False

    first = tokens[0].lower()
    if first in {"nohup", "setsid", "disown", "start", "start-process"}:
        return True
    return tokens[-1] == "&"
