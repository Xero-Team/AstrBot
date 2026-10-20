from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.loop_policy import (
    btw_config as btw_config_for,
)
from astrbot.core.agent.loop_policy import (
    is_work_loop_enabled,
    loop_mode_of,
    work_loop_is_read_only,
)
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.astr_main_agent_resources import (
    LLM_SAFETY_MODE_SYSTEM_PROMPT,
    SANDBOX_MODE_PROMPT,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.skills._skill_snapshot import (
    PROMPT_TOOLS_EXTRA_KEY,
    SKILL_SNAPSHOT_EXTRA_KEY,
    SkillSnapshot,
)
from astrbot.core.tool_catalog import (
    ToolCatalogInputs,
    assemble_tool_catalog,
    elevated_instance_tool_actions_from_metadata,
    merge_existing_tools,
    resolve_catalog_surface,
)
from astrbot.core.tools.computer_tools import (
    LOCAL_NETWORK_POLICY_NOTICE,
    get_local_permission_policy,
    resolve_local_permission_role,
)
from astrbot.core.tools.function_tool_manager import FunctionToolManager
from astrbot.core.tools.web_search_route import fetch_available, normalize_route

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext

from .common import _get_context_runtime_attr
from .config import MainAgentBuildConfig
from .prompts import _build_local_mode_prompt

WEB_SEARCH_CITATION_TOOL_NAMES = frozenset({"web_search"})


WEB_SEARCH_CITATION_PROMPT = (
    "Always cite web search results you rely on. "
    "Index is a unique identifier for each search result. "
    "Use the exact citation format <ref>index</ref> (e.g. <ref>abcd.3</ref>) "
    "after the sentence that uses the information. Do not invent citations."
)


WORK_LOOP_READ_ONLY_PROMPT = (
    "You are the work loop of a two-loop agent. Your write capabilities are "
    "removed on purpose: research, read, and plan for as long as the task "
    "needs, then answer from what you found. Shell, Python, and file-writing "
    "tools are not available to you, so do not call them."
)


WORK_LOOP_DELEGATION_PROMPT = (
    "When the task must create or change files, delegate it with "
    "`delegate_coding_task`. That coding agent runs with full write access "
    "inside its own task folder, so the `task` you pass must stand alone: "
    "state the goal, every input it needs, and the outputs you expect. Its "
    "reply names the folder and the artifacts it produced; report those to "
    "the user."
)


def _has_enabled_coding_agent(profile: object) -> bool:
    """Read the BTW-only delegation setting lazily.

    The default agent path must not load the BTW package; this helper only
    imports it when the active loop is the work loop and its catalog asks for
    delegation.
    """
    from astrbot.core.agent.btw.coding_agents import has_enabled_coding_agent

    return has_enabled_coding_agent(profile)


def _apply_btw_work_loop_prompt(
    req: ProviderRequest,
    event: AstrMessageEvent,
    plugin_context: CoreExecutionContext,
    config: MainAgentBuildConfig,
) -> None:
    """State the work loop's read-only role and its delegation path.

    The work loop's model decides what to do itself and what to hand over, so
    it has to be told both halves: which capabilities were removed and what
    replaces them.  Delegation starts a local process, so it is described only
    when the request's own computer boundary would actually expose it.
    """
    if loop_mode_of(event.get_extra("btw_loop")) != "work":
        return
    profile = plugin_context.get_config(umo=event.unified_msg_origin)
    fragments: list[str] = []
    if work_loop_is_read_only(profile, "work"):
        fragments.append(WORK_LOOP_READ_ONLY_PROMPT)
    if (
        config.computer_use_runtime == "local"
        and config.allow_computer_tools
        and _has_enabled_coding_agent(profile)
    ):
        fragments.append(WORK_LOOP_DELEGATION_PROMPT)
    if fragments:
        req.system_prompt = f"{req.system_prompt or ''}\n" + "\n".join(fragments) + "\n"


def _safe_iter_builtin_tools(tool_manager: FunctionToolManager) -> list[FunctionTool]:
    try:
        tools = tool_manager.iter_builtin_tools()
    except Exception:
        return []
    if not isinstance(tools, list):
        return []
    return tools


def _registered_tools_table(
    tool_manager: FunctionToolManager,
) -> dict[str, FunctionTool]:
    registered: dict[str, FunctionTool] = {}
    full_set = tool_manager.get_full_tool_set()
    tools = getattr(full_set, "tools", None)
    if isinstance(tools, list):
        for tool in tools:
            name = getattr(tool, "name", None)
            if isinstance(name, str) and name:
                registered[name] = tool
    for tool in _safe_iter_builtin_tools(tool_manager):
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            registered.setdefault(name, tool)
    return registered


def _configured_web_search_providers(provider_settings: dict) -> tuple[str, ...]:
    serpapi_keys = provider_settings.get("websearch_serpapi_key")
    if isinstance(serpapi_keys, list | tuple) and any(
        str(key).strip() for key in serpapi_keys
    ):
        return ("serpapi",)
    return ()


def _add_subagent_tools(
    req: ProviderRequest,
    plugin_context: CoreExecutionContext,
    tool_manager,
) -> None:
    orchestrator_config = plugin_context.get_config().get("subagent_orchestrator", {})
    orchestrator = plugin_context.subagent_orchestrator
    if not orchestrator_config.get("main_enable", False) or not orchestrator:
        return

    assigned_tools: set[str] = set()
    agents = orchestrator_config.get("agents", [])
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict) or agent.get("enabled", True) is False:
                continue
            prompt_tools = None
            if prompt_id := agent.get("prompt_id"):
                prompt = plugin_context.prompt_manager.get_runtime_prompt_by_id(
                    prompt_id
                )
                if prompt is not None:
                    prompt_tools = prompt.get("tools")
            tools = prompt_tools if prompt_tools is not None else agent.get("tools", [])
            if tools is None:
                assigned_tools.update(
                    tool.name
                    for tool in tool_manager.func_list
                    if not isinstance(tool, HandoffTool)
                )
            elif isinstance(tools, list):
                assigned_tools.update(
                    name for tool in tools if (name := str(tool).strip())
                )

    if req.func_tool is None:
        req.func_tool = ToolSet()
    for tool in orchestrator.handoffs:
        req.func_tool.add_tool(tool)

    if orchestrator_config.get("remove_main_duplicate_tools", False):
        handoff_names = {tool.name for tool in orchestrator.handoffs}
        for tool_name in assigned_tools - handoff_names:
            req.func_tool.remove_tool(tool_name)

    if router_prompt := str(
        orchestrator_config.get("router_system_prompt", "")
    ).strip():
        req.system_prompt += f"\n{router_prompt}\n"


def _assemble_request_tool_catalog(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: CoreExecutionContext,
    config: MainAgentBuildConfig,
) -> None:
    snapshot = event.get_extra(SKILL_SNAPSHOT_EXTRA_KEY)
    if not isinstance(snapshot, SkillSnapshot):
        snapshot = SkillSnapshot(skills=(), runtime=config.computer_use_runtime)
    prompt_tools = event.get_extra(PROMPT_TOOLS_EXTRA_KEY)
    if prompt_tools is not None and not isinstance(prompt_tools, list | tuple):
        prompt_tools = None
    auth_context = getattr(event, "auth_context", None)
    source = getattr(auth_context, "source", None) or "im"
    authenticated = bool(getattr(auth_context, "authenticated", False))
    subject = getattr(event, "subject", None)
    subject_kind = getattr(subject, "kind", None)
    metadata = getattr(auth_context, "metadata", {}) or {}
    elevated_instance_tool_actions = elevated_instance_tool_actions_from_metadata(
        metadata if isinstance(metadata, dict) else None
    )
    computer_runtime = getattr(plugin_context, "computer_runtime", None)
    existing_booter = None
    if computer_runtime is not None:
        getter = getattr(computer_runtime, "get_session_booter", None)
        if callable(getter):
            existing_booter = getter(req.session_id or event.unified_msg_origin)
    sandbox_capabilities = None
    if existing_booter is not None:
        capabilities = getattr(existing_booter, "capabilities", None)
        if isinstance(capabilities, list | tuple):
            sandbox_capabilities = capabilities
    cfg = plugin_context.get_config(umo=event.unified_msg_origin)
    provider_settings = cfg.get("provider_settings", {})
    ltm_settings = cfg.get("provider_ltm_settings", {})
    btw_config = btw_config_for(cfg)
    memory_manager = _get_context_runtime_attr(plugin_context, "memory_manager")
    tool_manager = plugin_context.get_llm_tool_manager()
    registered_tools = _registered_tools_table(tool_manager)
    builtin_tool_name_set: set[str] = set()
    for tool in _safe_iter_builtin_tools(tool_manager):
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name and registered_tools.get(name) is tool:
            builtin_tool_name_set.add(name)
    builtin_tool_names = frozenset(builtin_tool_name_set)
    session_tool_names = frozenset(registered_tools) - builtin_tool_name_set
    full_set = tool_manager.get_full_tool_set()
    full_tools = getattr(full_set, "tools", None)
    if isinstance(full_tools, list):
        full_tool_name_set: set[str] = set()
        for tool in full_tools:
            name = getattr(tool, "name", None)
            if isinstance(name, str) and name:
                full_tool_name_set.add(name)
        session_tool_names = frozenset(full_tool_name_set)
    surface = resolve_catalog_surface(
        source=source,
        authenticated=authenticated,
        subject_kind=subject_kind,
    )
    loop_mode = loop_mode_of(event.get_extra("btw_loop"))
    web_search_route = normalize_route(provider_settings.get("websearch_route"))
    catalog_inputs = ToolCatalogInputs(
        snapshot=snapshot,
        prompt_tools=prompt_tools,
        surface=surface,
        computer_use_runtime=config.computer_use_runtime,
        allow_computer_tools=config.allow_computer_tools,
        plugin_names=event.plugins_name,
        registered_tools=registered_tools,
        builtin_tool_names=builtin_tool_names,
        session_tool_names=session_tool_names,
        memory_enabled=memory_manager is not None,
        web_search_enabled=bool(provider_settings.get("web_search", False)),
        web_search_route=web_search_route,
        web_search_configured_providers=_configured_web_search_providers(
            provider_settings
        ),
        web_fetch_available=fetch_available(web_search_route, provider_settings),
        group_history_enabled=bool(
            event.get_message_type() == MessageType.GROUP_MESSAGE
            and ltm_settings.get("group_message_history_enable", False)
        ),
        proactive_messaging=bool(event.platform_meta.support_proactive_message),
        kb_agentic_mode=config.kb_agentic_mode,
        add_cron_tools=config.add_cron_tools,
        sandbox_booter=str(config.sandbox_cfg.get("booter", "shipyard_neo")),
        sandbox_capabilities=sandbox_capabilities,
        elevated_instance_tool_actions=elevated_instance_tool_actions,
        plugins=plugin_context.catalogs.plugins,
        btw_config=dict(btw_config) if btw_config else None,
        loop_mode=loop_mode,
        # Only the conversation loop submits work; the work loop runs it.
        work_loop_submission=(
            loop_mode == "conversation"
            and is_work_loop_enabled(cfg)
            and not event.get_extra("btw_classifier_no_handoff")
        ),
        # The work loop plans and reads; writes belong to a coding agent.
        work_loop_read_only=work_loop_is_read_only(cfg, loop_mode),
        work_loop_delegation=loop_mode == "work" and _has_enabled_coding_agent(cfg),
    )
    existing = req.func_tool
    if existing is not None:
        catalog_inputs = merge_existing_tools(catalog_inputs, existing.tools)
    req.func_tool = assemble_tool_catalog(catalog_inputs)
    _add_subagent_tools(req, plugin_context, tool_manager)


def _apply_llm_safety_mode(config: MainAgentBuildConfig, req: ProviderRequest) -> None:
    if config.safety_mode_strategy == "system_prompt":
        req.system_prompt = f"{LLM_SAFETY_MODE_SYSTEM_PROMPT}\n\n{req.system_prompt}"
    else:
        logger.warning(
            "Unsupported llm_safety_mode strategy: %s.",
            config.safety_mode_strategy,
        )


def _apply_web_search_citation_prompt(
    event: AstrMessageEvent,
    req: ProviderRequest,
) -> None:
    if event.get_platform_name() != "webchat" or not req.func_tool:
        return

    if not any(req.func_tool.get_tool(name) for name in WEB_SEARCH_CITATION_TOOL_NAMES):
        return

    system_prompt = req.system_prompt or ""
    if WEB_SEARCH_CITATION_PROMPT in system_prompt:
        return

    req.system_prompt = f"{system_prompt}\n{WEB_SEARCH_CITATION_PROMPT}\n"


def _apply_sandbox_tools(
    config: MainAgentBuildConfig,
    req: ProviderRequest,
    session_id: str,
    tool_manager: FunctionToolManager,
    existing_booter: object | None = None,
) -> None:
    _ = session_id
    _ = tool_manager
    if req.func_tool is None:
        req.func_tool = ToolSet()
    if req.system_prompt is None:
        req.system_prompt = ""
    booter = config.sandbox_cfg.get("booter", "shipyard_neo")
    if booter == "shipyard_neo":
        req.system_prompt += (
            "\n[Shipyard Neo File Path Rule]\n"
            "When using sandbox filesystem tools (upload/download/read/write/list/delete), "
            "always pass paths relative to the sandbox workspace root. "
            "Example: use `baidu_homepage.png` instead of `/workspace/baidu_homepage.png`.\n"
        )
        req.system_prompt += (
            "\n[Neo Skill Lifecycle Workflow]\n"
            "When user asks to create/update a reusable skill in Neo mode, use lifecycle tools instead of directly writing local skill folders.\n"
            "Preferred sequence:\n"
            "1) Use `astrbot_create_skill_payload` to store canonical payload content and get `payload_ref`.\n"
            "2) Use `astrbot_create_skill_candidate` with `skill_key` + `source_execution_ids` (and optional `payload_ref`) to create a candidate.\n"
            "3) Use `astrbot_promote_skill_candidate` to release: `stage=canary` for trial; `stage=stable` for production.\n"
            "For stable release, set `sync_to_local=true` to sync `payload.skill_markdown` into local `SKILL.md`.\n"
            "Do not treat ad-hoc generated files as reusable Neo skills unless they are captured via payload/candidate/release.\n"
            "To update an existing skill, create a new payload/candidate and promote a new release version; avoid patching old local folders directly.\n"
        )
        _ = existing_booter
    if booter == "cua":
        req.system_prompt += (
            "\n[CUA Desktop Control]\n"
            "Use `astrbot_execute_shell` with `background=true` to launch GUI apps. "
            'Use Firefox for browser tasks, for example `firefox "https://example.com"`. '
            "After each visible step, call `astrbot_cua_screenshot` with "
            "`send_to_user=true` and `return_image_to_llm=true` so the user can "
            "monitor progress. When typing, inspect the screenshot first and confirm "
            "the target field is focused and empty or safe to append to. Use "
            "`astrbot_cua_mouse_click` for coordinates and `astrbot_cua_keyboard_type` "
            "for text input; use text=`\\n` for Enter.\n"
        )
    req.system_prompt = f"{req.system_prompt or ''}\n{SANDBOX_MODE_PROMPT}\n"


async def _apply_local_env_tools(
    req: ProviderRequest,
    plugin_context: CoreExecutionContext,
    event: AstrMessageEvent,
) -> None:
    req.system_prompt = f"{req.system_prompt or ''}\n{_build_local_mode_prompt()}\n"
    run_context = AgentContextWrapper(
        context=AstrAgentContext(context=plugin_context, event=event)
    )
    await resolve_local_permission_role(run_context)
    local_policy = get_local_permission_policy(run_context)
    if (
        local_policy.allow_execution
        and not local_policy.allow_network
        and LOCAL_NETWORK_POLICY_NOTICE not in (req.system_prompt or "")
    ):
        req.system_prompt = (
            f"{req.system_prompt or ''}\n{LOCAL_NETWORK_POLICY_NOTICE}\n"
        )
