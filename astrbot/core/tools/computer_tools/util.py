import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.auth.models import INSTANCE_TOOL_ROLES, Resource, Role
from astrbot.core.computer.local_policy import (
    LocalFilesystemPolicy,
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
    build_local_network_notice,
    default_policy,
    sandbox_policy_from_config,
)
from astrbot.core.computer.process_sandbox import get_process_sandbox_status
from astrbot.core.utils.astrbot_path import (
    get_astrbot_system_tmp_path,
    get_astrbot_temp_path,
    get_astrbot_workspaces_path,
)


def normalize_umo_for_workspace(umo: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", umo.strip())
    return normalized or "unknown"


LOCAL_NETWORK_POLICY_NOTICE = build_local_network_notice(
    LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="off"),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )
)


@dataclass(frozen=True)
class LocalPermissionPolicy:
    """Resolved Local computer permissions for one caller.

    Args:
        sandbox: Complete immutable Local policy.
        execution_disabled_reason: Isolation or configuration failure that
            blocked execution, if any. The configured policy is preserved so
            file tools and diagnostics still see the requested restrictions.
    """

    sandbox: LocalSandboxPolicy
    execution_disabled_reason: str | None = None

    @property
    def allow_execution(self) -> bool:
        """Return whether Shell and Python execution is allowed."""
        return self.sandbox.allow_execution

    @property
    def allow_network(self) -> bool:
        """Return whether sandboxed network access is enabled."""
        return self.sandbox.network.enabled

    @property
    def filesystem_scope(self) -> Literal["none", "workspace", "host"]:
        """Return the resolved filesystem access scope."""
        return self.sandbox.filesystem_scope

    @property
    def network(self) -> LocalNetworkPolicy:
        """Return the resolved network policy."""
        return self.sandbox.network

    @property
    def filesystem(self) -> LocalFilesystemPolicy:
        """Return the resolved filesystem deny policy."""
        return self.sandbox.filesystem

    @property
    def unix_sockets(self) -> LocalUnixSocketPolicy:
        """Return the resolved Unix socket policy."""
        return self.sandbox.unix_sockets

    @property
    def requires_sandbox(self) -> bool:
        """Return whether execution needs operating-system isolation."""
        return self.sandbox.requires_sandbox

    @property
    def network_notice(self) -> str:
        """Return the bounded prompt notice for this policy."""
        return build_local_network_notice(self.sandbox)


def workspace_root(umo: str) -> Path:
    """Root directory for relative paths in local runtime"""
    normalized_umo = normalize_umo_for_workspace(umo)
    return (Path(get_astrbot_workspaces_path()) / normalized_umo).resolve(strict=False)


def session_temp_roots(umo: str) -> tuple[Path, ...]:
    """Per-session temp directories that other callers cannot read or write."""
    key = normalize_umo_for_workspace(umo)
    return (
        (Path(get_astrbot_system_tmp_path()) / key).resolve(strict=False),
        (Path(get_astrbot_temp_path()) / key).resolve(strict=False),
    )


def is_local_runtime(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "none"))
    return runtime == "local"


def _role_from_effective(effective: object) -> str:
    """Map an authorization role onto a Local permission matrix row."""
    if effective in INSTANCE_TOOL_ROLES or effective in {
        Role.INSTANCE_OPERATOR,
        Role.OPERATOR,
        Role.ROOT,
        "instance_operator",
        "operator",
        "root",
    }:
        return "admin"
    return "member"


def _stamp_permission_role(event: object, effective: object) -> str:
    role = _role_from_effective(effective)
    setattr(event, "_computer_permission_role", role)
    return role


def _local_permission_role(context: ContextWrapper[AstrAgentContext]) -> str:
    """Return the cached Local permission matrix row for this event."""
    stored = getattr(context.context.event, "_computer_permission_role", None)
    if stored in {"admin", "member"}:
        return stored
    return "member"


async def resolve_local_permission_role(
    context: ContextWrapper[AstrAgentContext],
) -> str:
    """Resolve the Local matrix row from authorization, not tool-call order."""
    event = context.context.event
    stored = getattr(event, "_computer_permission_role", None)
    if stored in {"admin", "member"}:
        return stored
    authorization = getattr(context.context.context, "authorization", None)
    if authorization is None or event.subject is None or event.auth_context is None:
        return "member"
    config_id = (
        event.resource.config_id
        if event.resource is not None
        else event.auth_context.config_id
    )
    decision = await authorization.authorize(
        event.subject,
        "tool.file_read",
        Resource.named("tool", "local-permission-role", config_id=config_id),
        event.auth_context,
    )
    return _stamp_permission_role(event, getattr(decision, "effective_role", None))


def get_local_permission_policy(
    context: ContextWrapper[AstrAgentContext],
    *,
    role: Literal["member", "admin"] | None = None,
) -> LocalPermissionPolicy:
    """Resolve the Local permission policy for the caller's role.

    Args:
        context: Tool call context.
        role: Role policy to inspect, or None to use the caller's role.

    Returns:
        Normalized policy. If required isolation is unavailable, execution is
        disabled without widening file access or changing the saved policy.
        Unknown roles use the member policy. Malformed persisted policies fail
        closed instead of falling back to native execution.
    """
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    role = "admin" if (role or _local_permission_role(context)) == "admin" else "member"

    permissions = provider_settings.get("computer_use_local_permissions")
    role_policy = permissions.get(role) if isinstance(permissions, dict) else None
    if role_policy is None:
        sandbox = default_policy(role)
        validation_errors: list[str] = []
    else:
        sandbox, validation_errors = sandbox_policy_from_config(
            role_policy,
            role=role,
        )

    if validation_errors:
        return LocalPermissionPolicy(
            sandbox=sandbox.without_execution(),
            execution_disabled_reason=(
                "The saved Local permission policy is invalid and execution was "
                "blocked. Fix the Local Permission Policies configuration in "
                "AstrBot WebUI. Validation errors: " + "; ".join(validation_errors[:4])
            ),
        )

    policy = LocalPermissionPolicy(sandbox=sandbox)
    if (
        provider_settings.get("computer_use_runtime") == "local"
        and policy.requires_sandbox
    ):
        sandbox_status = get_process_sandbox_status()
        if sandbox_status["status"] != "detected":
            backend = sandbox_status.get("backend") or "Local process isolation"
            reason = {
                "missing": f"{backend} is not installed",
                "unsupported": "Local process isolation is not supported on this platform",
                "unavailable": f"{backend} failed its startup probe",
            }.get(sandbox_status["status"], "Local process isolation is unavailable")
            if sandbox_status.get("error"):
                reason += f": {sandbox_status['error']}"
            if sandbox_status["status"] == "unsupported":
                recovery = "Run AstrBot in an environment that supports Local process isolation."
            elif sandbox_status["status"] == "missing" and backend == "bubblewrap":
                recovery = (
                    "Install bubblewrap on the AstrBot host, then restart AstrBot."
                )
            elif backend == "seatbelt":
                recovery = (
                    "Restore macOS Seatbelt (`sandbox-exec`) availability, "
                    "then restart AstrBot."
                )
            else:
                recovery = (
                    f"Fix the {backend} startup failure shown above, "
                    "then restart AstrBot."
                )
            return LocalPermissionPolicy(
                sandbox=policy.sandbox.without_execution(),
                execution_disabled_reason=(
                    "The Agent Computer Use runtime is the local environment (`local`). "
                    f"The current user role is `{role}`; its configured Local permission "
                    "policy is: code execution enabled, network mode "
                    f"`{policy.network.mode}`, "
                    f"file access scope `{policy.filesystem_scope}`, "
                    f"{len(policy.filesystem.deny_read)} read deny rules, "
                    f"{len(policy.filesystem.deny_write)} write deny rules, "
                    f"Unix socket mode `{policy.unix_sockets.mode}`. "
                    "These restrictions require Local process isolation, "
                    f"but {reason}. Code execution is blocked. "
                    "Ask an AstrBot administrator to choose:\n"
                    f"1. Keep the configured restrictions: {recovery}\n"
                    "2. Explicitly allow native execution without Local isolation by "
                    "setting file access scope to `Entire environment`, network mode "
                    "to `unrestricted`, enabling both private-network and loopback "
                    "access, clearing all filesystem deny rules, and setting Unix "
                    "socket mode to `allow_all` for this role in AstrBot WebUI -> "
                    "Config -> AI -> Capabilities -> Agent Computer Use -> "
                    "Local Permission Policies. (Warning: native execution permits "
                    "code execution with access to the entire environment and "
                    "network, without any sandbox guarantee)."
                ),
            )
    return policy


async def check_local_file_permission(
    context: ContextWrapper[AstrAgentContext],
) -> str | None:
    """Reject file tools when Local access is disabled for the caller's role.

    Args:
        context: Tool call context.

    Returns:
        A permission error, or None when the file tool may proceed.
    """
    await resolve_local_permission_role(context)
    if (
        is_local_runtime(context)
        and get_local_permission_policy(context).filesystem_scope == "none"
    ):
        return (
            "error: Permission denied. Local computer tools are disabled for this "
            "user role. Enable Local computer access for this role in AstrBot "
            "WebUI -> Config -> AI -> Capabilities -> Agent Computer Use -> "
            "Local Permission Policies."
        )
    return None


async def check_admin_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str
) -> str | None:
    """Run the final action check immediately before a sensitive operation."""

    event = context.context.event
    mapped = {
        "Shell execution": ("tool.local_exec", "shell-execution"),
        "Shell session management": ("tool.local_exec", "shell-session"),
        "Python execution": ("tool.python_exec", "python-execution"),
        "Send message to another session": ("agent.manage", "send-message"),
    }.get(operation_name)
    if mapped is None:
        raise ValueError(f"Unsupported local permission operation: {operation_name}.")
    action, resource_id = mapped
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
    _stamp_permission_role(event, getattr(decision, "effective_role", None))
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
        if policy.execution_disabled_reason:
            return policy, (
                f"error: Local isolation unavailable. {operation_name} was blocked. "
                f"{policy.execution_disabled_reason}"
            )
        if policy.filesystem_scope == "none":
            return policy, await check_local_file_permission(context)
        role = _local_permission_role(context)
        policy_location = (
            "AstrBot WebUI -> Config -> AI -> Capabilities -> "
            "Agent Computer Use -> Local Permission Policies"
        )
        instructions = (
            "Ask an AstrBot administrator to enable "
            f"`Allow code execution` for this role in {policy_location}."
        )
        if (
            role != "admin"
            and get_local_permission_policy(context, role="admin").allow_execution
        ):
            subject_id = getattr(
                getattr(context.context.event, "subject", None),
                "id",
                None,
            )
            subject_hint = (
                f"this session's Subject ID `{subject_id}`"
                if subject_id
                else "this session's Subject ID (see `/session info`)"
            )
            instructions = (
                "Ask an AstrBot administrator to either:\n"
                f"1. Grant {subject_hint} the `instance_operator` role with "
                "instance scope for this configuration profile in "
                "AstrBot WebUI -> More Features -> Authorization.\n"
                f"2. Enable `Allow code execution` for members in {policy_location}."
            )
        return policy, (
            f"error: Permission denied. {operation_name} is disabled by the "
            f"Local permission policy for this user role ({role}). {instructions}"
        )
    return policy, None
