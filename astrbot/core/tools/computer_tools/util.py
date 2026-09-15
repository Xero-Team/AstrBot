import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.auth.models import INSTANCE_TOOL_ROLES, Resource, Role
from astrbot.core.computer.process_sandbox import create_process_sandbox
from astrbot.core.config.default import get_local_permission_defaults
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path


def normalize_umo_for_workspace(umo: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", umo.strip())
    return normalized or "unknown"

LOCAL_NETWORK_POLICY_NOTICE = (
    "Sandbox policy: Network access is disabled for local Shell/Python execution. "
    "Do not retry the same network operation with another command, Python, "
    "HTTP/HTTPS, or disabled certificate verification; these do not change the policy. "
    "Local offline operations are still allowed."
)


@dataclass(frozen=True)
class LocalPermissionPolicy:
    """Resolved Local computer permissions for one caller.

    Args:
        allow_execution: Whether Shell and Python execution is allowed.
        allow_network: Whether the execution environment may use the network.
        filesystem_scope: Host or workspace access, or none to disable Local tools.
    """

    allow_execution: bool
    allow_network: bool
    filesystem_scope: Literal["none", "workspace", "host"]

    @property
    def requires_sandbox(self) -> bool:
        """Return whether execution needs operating-system isolation."""
        return not self.allow_network or self.filesystem_scope != "host"


def workspace_root(umo: str) -> Path:
    """Root directory for relative paths in local runtime"""
    normalized_umo = normalize_umo_for_workspace(umo)
    return (Path(get_astrbot_workspaces_path()) / normalized_umo).resolve(strict=False)


def is_local_runtime(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "none"))
    return runtime == "local"


def _local_permission_role(context: ContextWrapper[AstrAgentContext]) -> str:
    """Map the caller to the Local permission matrix row.

    Production events no longer expose ``event.role``. Instance operators and
    above use the administrator policy; everyone else uses the member policy.
    Tests may still set ``event.role == "admin"``.
    """
    event = context.context.event
    if getattr(event, "role", None) == "admin":
        return "admin"
    stored = getattr(event, "_computer_permission_role", None)
    if stored in {"admin", "member"}:
        return stored
    return "member"


def get_local_permission_policy(
    context: ContextWrapper[AstrAgentContext],
) -> LocalPermissionPolicy:
    """Resolve the Local permission policy for the caller's role.

    Args:
        context: Tool call context.

    Returns:
        Normalized policy. Unknown roles use the member policy.
    """
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    role = _local_permission_role(context)
    defaults = get_local_permission_defaults()[role]

    permissions = provider_settings.get("computer_use_local_permissions")
    role_policy = permissions.get(role) if isinstance(permissions, dict) else None
    if not isinstance(role_policy, dict):
        role_policy = {}

    filesystem_scope = role_policy.get("filesystem_scope", defaults["filesystem_scope"])
    if filesystem_scope not in {"none", "workspace", "host"}:
        filesystem_scope = defaults["filesystem_scope"]
    allow_execution = (
        filesystem_scope != "none"
        and role_policy.get("allow_execution", defaults["allow_execution"]) is True
    )
    allow_network = (
        allow_execution
        and role_policy.get("allow_network", defaults["allow_network"]) is True
    )
    return LocalPermissionPolicy(
        allow_execution=allow_execution,
        allow_network=allow_network,
        filesystem_scope=filesystem_scope,
    )


def check_local_file_permission(
    context: ContextWrapper[AstrAgentContext],
) -> str | None:
    """Reject file tools when Local access is disabled for the caller's role.

    Args:
        context: Tool call context.

    Returns:
        A permission error, or None when the file tool may proceed.
    """
    if (
        is_local_runtime(context)
        and get_local_permission_policy(context).filesystem_scope == "none"
    ):
        return (
            "error: Permission denied. Local computer tools are disabled for this "
            "user role. Enable Local computer access for this role in AstrBot "
            "WebUI -> Config -> Agent Computer Use -> Local Permission Policies."
        )
    return None


async def check_admin_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str
) -> str | None:
    """Run the final action check immediately before a sensitive operation."""

    event = context.context.event
    action, resource_id = {
        "Shell execution": ("tool.local_exec", "shell-execution"),
        "Shell session management": ("tool.local_exec", "shell-session"),
        "Python execution": ("tool.python_exec", "python-execution"),
        "File upload/download": ("tool.file_write", "file-transfer"),
        "Taking CUA screenshots": ("tool.computer_use", "cua-screenshot"),
        "Using CUA mouse": ("tool.computer_use", "cua-mouse"),
        "Using CUA keyboard": ("tool.computer_use", "cua-keyboard"),
        "Using browser tools": ("tool.browser_control", "browser"),
        "Using skill lifecycle tools": ("extension.manage", "skill-lifecycle"),
        "Send a poke to another user": ("agent.manage", "send-poke"),
        "Send message to another session": ("agent.manage", "send-message"),
    }.get(operation_name, ("tool.local_exec", "sensitive-operation"))
    authorization = getattr(context.context.context, "authorization", None)
    if authorization is None or event.subject is None or event.auth_context is None:
        return "error: Permission denied. Authorization context is unavailable."
    config_id = (
        event.resource.config_id
        if event.resource is not None
        else event.auth_context.config_id
    )
    decision = await authorization.authorize(
        event.subject,
        action,
        Resource.named("tool", resource_id, config_id=config_id),
        event.auth_context,
    )
    effective = getattr(decision, "effective_role", None)
    if effective in INSTANCE_TOOL_ROLES or effective in {
        Role.INSTANCE_OPERATOR,
        Role.OPERATOR,
        Role.ROOT,
        "instance_operator",
        "operator",
        "root",
    }:
        event._computer_permission_role = "admin"
    else:
        event._computer_permission_role = "member"
    if not decision.allowed:
        return (
            f"error: Permission denied. {operation_name} requires an authorized action. "
            f"User's ID is: {event.get_sender_id()}."
        )
    return None


async def check_local_execution_permission(
    context: ContextWrapper[AstrAgentContext],
    operation_name: str,
) -> tuple[LocalPermissionPolicy | None, str | None]:
    """Resolve whether an execution tool needs an operating-system sandbox.

    Args:
        context: Tool call context.
        operation_name: User-facing name included in permission errors.

    Returns:
        Resolved Local policy and an optional error. Non-Local runtimes return
        no policy because their existing authorization gate is unchanged.
    """
    if permission_error := await check_admin_permission(context, operation_name):
        return None, permission_error
    if not is_local_runtime(context):
        return None, None
    policy = get_local_permission_policy(context)
    if not policy.allow_execution:
        return policy, (
            f"error: Permission denied. {operation_name} is disabled by the "
            "Local permission policy for this user role. Enable Local computer "
            "access and `Execute code` "
            "for this role in AstrBot WebUI -> Config -> Agent Computer Use -> "
            "Local Permission Policies."
        )
    if policy.requires_sandbox:
        try:
            create_process_sandbox()
        except RuntimeError as exc:
            return policy, (
                "error: Permission denied. Restricted Local execution is unavailable: "
                f"{exc} Select `Third-party sandbox` under AstrBot WebUI -> Config -> "
                "Agent Computer Use -> Computer Use Runtime."
            )
    return policy, None
