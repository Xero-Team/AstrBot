from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from astrbot import logger
from astrbot.core.agent.btw.loop_routes import route_is_available_in_loop
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.auth.models import WEBCHAT_INSTANCE_TOOL_ACTIONS
from astrbot.core.skills._skill_snapshot import SkillSnapshot

READ_SKILL_TOOL_NAME = "read_skill"
READ_SKILL_MODEL_NAME = "read_skill"

CatalogSurface = Literal[
    "im",
    "webchat",
    "webchat_authenticated",
    "plugin",
    "agent",
    "api_key",
]

SOCIAL_SURFACES: frozenset[str] = frozenset(
    {"im", "webchat", "plugin", "agent", "api_key"}
)

MEMORY_BASELINE_TOOLS: tuple[str, ...] = (
    "search_memory",
    "get_person_profile",
    "query_episode",
    "maintain_memory",
)

LOCAL_COMPUTER_TOOLS: tuple[str, ...] = (
    "astrbot_execute_shell",
    "astrbot_shell_session",
    "astrbot_execute_python",
    "astrbot_file_read_tool",
    "astrbot_file_write_tool",
    "astrbot_file_edit_tool",
    "astrbot_grep_tool",
)

SANDBOX_BASE_COMPUTER_TOOLS: tuple[str, ...] = (
    "astrbot_execute_shell",
    "astrbot_execute_ipython",
    "astrbot_upload_file",
    "astrbot_download_file",
    "astrbot_file_read_tool",
    "astrbot_file_write_tool",
    "astrbot_file_edit_tool",
    "astrbot_grep_tool",
)

SANDBOX_BROWSER_TOOLS: tuple[str, ...] = (
    "astrbot_execute_browser",
    "astrbot_execute_browser_batch",
    "astrbot_run_browser_skill",
)

NEO_LIFECYCLE_TOOLS: tuple[str, ...] = (
    "astrbot_get_execution_history",
    "astrbot_annotate_execution",
    "astrbot_create_skill_payload",
    "astrbot_get_skill_payload",
    "astrbot_create_skill_candidate",
    "astrbot_list_skill_candidates",
    "astrbot_evaluate_skill_candidate",
    "astrbot_promote_skill_candidate",
    "astrbot_list_skill_releases",
    "astrbot_rollback_skill_release",
    "astrbot_sync_skill_release",
)

CUA_COMPUTER_TOOLS: tuple[str, ...] = (
    "astrbot_cua_screenshot",
    "astrbot_cua_mouse_click",
    "astrbot_cua_keyboard_type",
)

COMPUTER_TOOL_NAMES: frozenset[str] = frozenset(
    LOCAL_COMPUTER_TOOLS
    + SANDBOX_BASE_COMPUTER_TOOLS
    + SANDBOX_BROWSER_TOOLS
    + NEO_LIFECYCLE_TOOLS
    + CUA_COMPUTER_TOOLS
)
COMPUTER_TOOL_ACTIONS: frozenset[str] = frozenset(
    {
        "tool.local_exec",
        "tool.python_exec",
        "tool.file_read",
        "tool.file_write",
        "tool.browser_control",
        "tool.computer_use",
    }
)

WORKSPACE_FILE_READ_TOOLS: frozenset[str] = frozenset(
    {"astrbot_file_read_tool", "astrbot_grep_tool"}
)

WEB_SEARCH_PROVIDER_TOOLS: Mapping[str, tuple[str, ...]] = {
    "tavily": ("web_search_tavily", "tavily_extract_web_page"),
    "bocha": ("web_search_bocha",),
    "brave": ("web_search_brave",),
    "firecrawl": ("web_search_firecrawl", "firecrawl_extract_web_page"),
    "baidu_ai_search": ("web_search_baidu",),
    "exa": ("web_search_exa", "exa_get_contents"),
    "anysearch": ("web_search_anysearch",),
}


class PluginLookup(Protocol):
    """The narrow plugin capability required for tool activation."""

    def get_by_module(self, module_path: str | None) -> object | None:
        """Return the plugin registered for ``module_path``."""


@dataclass(frozen=True, slots=True)
class ToolCatalogInputs:
    snapshot: SkillSnapshot
    persona_tools: Sequence[str] | None
    surface: CatalogSurface
    computer_use_runtime: str
    plugin_names: Sequence[str] | None
    registered_tools: Mapping[str, FunctionTool]
    session_tool_names: frozenset[str] = frozenset()
    memory_enabled: bool = False
    web_search_enabled: bool = False
    web_search_provider: str = "tavily"
    group_history_enabled: bool = False
    proactive_messaging: bool = False
    kb_agentic_mode: bool = False
    add_cron_tools: bool = False
    sandbox_booter: str = "shipyard_neo"
    sandbox_capabilities: Sequence[str] | None = None
    elevated_instance_tool_actions: frozenset[str] = frozenset()
    allow_computer_tools: bool = True
    plugins: PluginLookup | None = None
    btw_config: Mapping[str, object] | None = None
    loop_mode: str = "conversation"
    work_loop_submission: bool = False


def assemble_tool_catalog(inputs: ToolCatalogInputs) -> ToolSet:
    """Assemble one request-scoped ToolSet from the four candidate layers."""
    names = assemble_tool_catalog_names(inputs)
    toolset = ToolSet()
    for name in names:
        tool = inputs.registered_tools.get(name)
        if tool is None or not getattr(tool, "active", True):
            continue
        toolset.add_tool(tool)
    return toolset


def assemble_tool_catalog_names(inputs: ToolCatalogInputs) -> tuple[str, ...]:
    candidates = _candidate_union(inputs)
    after_persona = _apply_persona_tools(
        candidates,
        persona_tools=inputs.persona_tools,
        snapshot=inputs.snapshot,
    )
    after_plugin = _apply_plugin_filter(
        after_persona,
        plugin_names=inputs.plugin_names,
        registered_tools=inputs.registered_tools,
        plugins=inputs.plugins,
    )
    after_visibility = _apply_visibility(
        after_plugin,
        inputs=inputs,
    )
    after_strip = _apply_surface_strip(
        after_visibility,
        inputs=inputs,
    )
    return tuple(sorted(after_strip))


def local_computer_tool_names() -> tuple[str, ...]:
    return LOCAL_COMPUTER_TOOLS


def sandbox_computer_tool_names(
    *,
    booter: str = "shipyard_neo",
    capabilities: Sequence[str] | None = None,
) -> tuple[str, ...]:
    names = list(SANDBOX_BASE_COMPUTER_TOOLS)
    if booter == "shipyard_neo":
        if capabilities is None or "browser" in capabilities:
            names.extend(SANDBOX_BROWSER_TOOLS)
        names.extend(NEO_LIFECYCLE_TOOLS)
    if booter == "cua":
        names.extend(CUA_COMPUTER_TOOLS)
    return tuple(names)


def resolve_catalog_surface(
    *,
    source: str | None,
    authenticated: bool = False,
    subject_kind: str | None = None,
) -> CatalogSurface:
    if source == "api_key":
        return "api_key"
    if source == "plugin":
        return "plugin"
    if source == "agent":
        return "agent"
    if source == "webchat":
        if authenticated and subject_kind == "dashboard-account":
            return "webchat_authenticated"
        return "webchat"
    return "im"


def tool_required_actions(tool: FunctionTool) -> tuple[str, ...]:
    """Classify a tool from its type, name, and declared actions."""
    from astrbot.core.agent.handoff import HandoffTool

    if isinstance(tool, HandoffTool):
        return ("agent.manage",)
    if isinstance(tool, MCPTool):
        annotations = getattr(tool, "annotations", {}) or {}
        if isinstance(annotations, dict):
            read_only_hint = annotations.get("readOnlyHint")
            if read_only_hint is None:
                read_only_hint = annotations.get("read_only_hint")
        else:
            read_only_hint = getattr(annotations, "readOnlyHint", None)
            if read_only_hint is None:
                read_only_hint = getattr(annotations, "read_only_hint", None)
        is_read_only = bool(read_only_hint)
        return ("tool.mcp_read" if is_read_only else "tool.mcp_write",)
    name = str(getattr(tool, "name", ""))
    if name == "read_skill":
        return ("skill.read",)
    if name in {"astrbot_execute_shell", "astrbot_shell_session"}:
        return ("tool.local_exec",)
    if name in {"astrbot_execute_ipython", "astrbot_execute_python"}:
        return ("tool.python_exec",)
    if name in {
        "astrbot_file_write_tool",
        "astrbot_file_edit_tool",
        "astrbot_upload_file",
        "astrbot_download_file",
    }:
        return ("tool.file_write",)
    if name in {"astrbot_file_read_tool", "astrbot_grep_tool"}:
        return ("tool.file_read",)
    if name.startswith("astrbot_cua_"):
        return ("tool.computer_use",)
    if "browser" in name:
        return ("tool.browser_control",)
    if "skill" in name and name.startswith("astrbot_"):
        return ("extension.manage",)
    if name in {"send_message_to_user", "send_poke_to_user"}:
        return ("agent.manage",)
    if "history" in name or name.startswith("get_"):
        return ("session.read",)
    declared = getattr(tool, "required_actions", ())
    if (
        isinstance(declared, tuple)
        and declared
        and all(isinstance(action, str) and action for action in declared)
    ):
        return declared
    return ()


def merge_existing_tools(
    inputs: ToolCatalogInputs,
    existing: Iterable[FunctionTool],
) -> ToolCatalogInputs:
    """Re-ingest request tools through the same catalog surface."""
    registered = dict(inputs.registered_tools)
    session_names = set(inputs.session_tool_names)
    for tool in existing:
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or not name:
            continue
        registered[name] = tool
        session_names.add(name)
    return replace(
        inputs,
        registered_tools=registered,
        session_tool_names=frozenset(session_names),
    )


def _candidate_union(inputs: ToolCatalogInputs) -> set[str]:
    names: set[str] = set()
    names.update(_platform_baseline(inputs))
    names.update(_session_plugin_mcp_tools(inputs))
    names.update(_skill_declared_tools(inputs))
    names.update(_on_demand_computer_tools(inputs))
    return names


def _platform_baseline(inputs: ToolCatalogInputs) -> set[str]:
    names: set[str] = set()
    if inputs.snapshot.skills:
        names.add(READ_SKILL_TOOL_NAME)
    if inputs.memory_enabled:
        names.update(MEMORY_BASELINE_TOOLS)
    if inputs.web_search_enabled:
        names.update(WEB_SEARCH_PROVIDER_TOOLS.get(inputs.web_search_provider, ()))
    if inputs.group_history_enabled:
        names.add("get_group_message_history")
    if inputs.proactive_messaging:
        names.add("send_message_to_user")
    if inputs.kb_agentic_mode:
        names.add("astr_kb_search")
    if inputs.add_cron_tools:
        names.add("future_task")
    if inputs.work_loop_submission:
        names.add("submit_work_task")
    return names


def _session_plugin_mcp_tools(inputs: ToolCatalogInputs) -> set[str]:
    names: set[str] = set()
    session_names = inputs.session_tool_names
    for name, tool in inputs.registered_tools.items():
        if session_names and name not in session_names:
            continue
        if not getattr(tool, "active", True):
            continue
        if isinstance(tool, MCPTool):
            names.add(name)
            continue
        if session_names:
            names.add(name)
            continue
        module_path = getattr(tool, "handler_module_path", None)
        if isinstance(module_path, str) and module_path:
            names.add(name)
    return names


def _skill_declared_tools(inputs: ToolCatalogInputs) -> set[str]:
    names: set[str] = set()
    for skill in inputs.snapshot.skills:
        for tool_name in skill.declared_tools:
            if tool_name in {READ_SKILL_TOOL_NAME, READ_SKILL_MODEL_NAME}:
                continue
            if tool_name not in inputs.registered_tools:
                logger.warning(
                    "Ignoring unknown Skill tool %s declared by %s",
                    tool_name,
                    skill.name,
                )
                continue
            names.add(tool_name)
    return names


def _on_demand_computer_tools(inputs: ToolCatalogInputs) -> set[str]:
    runtime = inputs.computer_use_runtime
    if runtime == "local":
        return set(local_computer_tool_names())
    if runtime == "sandbox":
        return set(
            sandbox_computer_tool_names(
                booter=inputs.sandbox_booter,
                capabilities=inputs.sandbox_capabilities,
            )
        )
    return set()


def _apply_persona_tools(
    candidates: set[str],
    *,
    persona_tools: Sequence[str] | None,
    snapshot: SkillSnapshot,
) -> set[str]:
    keep_read_skill = bool(snapshot.skills) and READ_SKILL_TOOL_NAME in candidates
    if persona_tools is None:
        names = set(candidates)
    elif not persona_tools:
        names = set()
    else:
        allowed = set(persona_tools)
        names = {name for name in candidates if name in allowed}
    if keep_read_skill:
        names.add(READ_SKILL_TOOL_NAME)
    elif not snapshot.skills:
        names.discard(READ_SKILL_TOOL_NAME)
    return names


def _apply_plugin_filter(
    names: set[str],
    *,
    plugin_names: Sequence[str] | None,
    registered_tools: Mapping[str, FunctionTool],
    plugins: PluginLookup | None,
) -> set[str]:
    if plugin_names is None:
        return set(names)
    allowed = set(plugin_names)
    kept: set[str] = set()
    for name in names:
        tool = registered_tools.get(name)
        if tool is None:
            continue
        if isinstance(tool, MCPTool) or not getattr(tool, "handler_module_path", None):
            kept.add(name)
            continue
        plugin = None
        if plugins is not None:
            plugin = plugins.get_by_module(tool.handler_module_path)
        if plugin is None:
            kept.add(name)
            continue
        plugin_name = getattr(plugin, "name", None)
        reserved = bool(getattr(plugin, "reserved", False))
        if plugin_name in allowed or reserved:
            kept.add(name)
    return kept


def tool_is_available_in_loop(
    tool: FunctionTool,
    *,
    btw_config: Mapping[str, object] | None,
    loop_mode: str,
    plugins: PluginLookup | None,
) -> bool:
    """Apply the same BTW capability assignment in the catalog and handoffs."""
    if not btw_config or not btw_config.get("enabled", False):
        return True
    raw_tool = getattr(tool, "_wrapped", tool)
    if isinstance(raw_tool, MCPTool):
        return route_is_available_in_loop(
            btw_config.get("mcp_routes"),
            route_key="server_name",
            route_id=raw_tool.mcp_server_name,
            loop_mode=loop_mode,
            default_loop="work",
        )
    module_path = getattr(raw_tool, "handler_module_path", None)
    plugin = plugins.get_by_module(module_path) if plugins and module_path else None
    if plugin is None or getattr(plugin, "reserved", False):
        return True
    plugin_id = getattr(plugin, "root_dir_name", None) or getattr(plugin, "name", "")
    return route_is_available_in_loop(
        btw_config.get("plugin_routes"),
        route_key="plugin_id",
        route_id=plugin_id,
        loop_mode=loop_mode,
        default_loop="work",
    )


def _apply_visibility(names: set[str], *, inputs: ToolCatalogInputs) -> set[str]:
    visible: set[str] = set()
    computer_names = _on_demand_computer_tools(inputs)
    for name in names:
        tool = inputs.registered_tools.get(name)
        if tool is None or not getattr(tool, "active", True):
            continue
        if not tool_is_available_in_loop(
            tool,
            btw_config=inputs.btw_config,
            loop_mode=inputs.loop_mode,
            plugins=inputs.plugins,
        ):
            continue
        actions = tool_required_actions(tool)
        if not inputs.allow_computer_tools and (
            name in COMPUTER_TOOL_NAMES or COMPUTER_TOOL_ACTIONS.intersection(actions)
        ):
            continue
        if name in WORKSPACE_FILE_READ_TOOLS and name not in computer_names:
            continue
        if inputs.computer_use_runtime == "none" and _is_computer_capability_action(
            actions
        ):
            continue
        visible.add(name)
    return visible


def elevated_instance_tool_actions_from_metadata(
    metadata: Mapping[str, object] | None,
) -> frozenset[str]:
    """Return the instance-tool actions this request may mount.

    WebChat contributes current step-up token keys. IM contributes the
    full ``WEBCHAT_INSTANCE_TOOL_ACTIONS`` set when waking check already
    confirmed instance_operator or above. Unknown actions are dropped so
    metadata cannot widen the group.
    """

    actions: set[str] = set()
    payload = metadata or {}
    tokens = payload.get("webchat_step_up_tokens")
    if isinstance(tokens, Mapping):
        actions.update(str(key) for key in tokens)
    raw = payload.get("elevated_instance_tool_actions")
    if isinstance(raw, list | tuple | set | frozenset):
        actions.update(str(item) for item in raw)
    return frozenset(actions) & WEBCHAT_INSTANCE_TOOL_ACTIONS


def tool_is_surface_stripped(
    actions: Iterable[str],
    *,
    surface: CatalogSurface,
    elevated_instance_tool_actions: frozenset[str] = frozenset(),
) -> bool:
    """Return True when a tool must stay out of the catalog for this surface."""
    blocked = set(actions) & WEBCHAT_INSTANCE_TOOL_ACTIONS
    if not blocked:
        return False
    elevated = elevated_instance_tool_actions & WEBCHAT_INSTANCE_TOOL_ACTIONS
    if surface in {"im", "webchat_authenticated"}:
        return not blocked <= elevated
    if surface in SOCIAL_SURFACES:
        return True
    return False


def _apply_surface_strip(names: set[str], *, inputs: ToolCatalogInputs) -> set[str]:
    kept: set[str] = set()
    elevated = inputs.elevated_instance_tool_actions & WEBCHAT_INSTANCE_TOOL_ACTIONS
    for name in names:
        tool = inputs.registered_tools.get(name)
        if tool is None:
            continue
        if tool_is_surface_stripped(
            tool_required_actions(tool),
            surface=inputs.surface,
            elevated_instance_tool_actions=elevated,
        ):
            continue
        kept.add(name)
    return kept


def _is_computer_capability_action(actions: Iterable[str]) -> bool:
    return bool(
        set(actions)
        & {
            "tool.local_exec",
            "tool.python_exec",
            "tool.file_write",
            "tool.browser_control",
            "tool.computer_use",
        }
    )
