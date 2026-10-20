import copy
import datetime
import platform
import zoneinfo
from pathlib import Path
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.chat_model import ChatModel
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.loop_policy import (
    btw_config as btw_config_for,
)
from astrbot.core.agent.loop_policy import (
    is_btw_enabled,
    loop_mode_of,
    route_is_available_in_loop,
)
from astrbot.core.agent.message import TextPart
from astrbot.core.astr_main_agent_resources import (
    CHATUI_SPECIAL_DEFAULT_PROMPT,
)
from astrbot.core.computer.booters.local import resolve_windows_shell
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.prompt_error_reply import (
    extract_prompt_custom_error_message_from_prompt,
    set_prompt_custom_error_message_on_event,
)
from astrbot.core.prompt_models import PromptSpec
from astrbot.core.skills._skill_snapshot import (
    PROMPT_TOOLS_EXTRA_KEY,
    SKILL_SNAPSHOT_EXTRA_KEY,
    SkillSnapshot,
    freeze_skill_snapshot,
)
from astrbot.core.skills.skill_manager import (
    SkillInfo,
    SkillManager,
    build_skills_prompt,
)
from astrbot.core.utils.string_utils import (
    interpolate_placeholders,
)

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext
    from astrbot.core.star.star import PluginRegistry

from .attachments import (
    _ensure_img_caption,
    _get_quoted_message_parser_settings,
    _process_quote_message,
)
from .common import (
    _get_context_runtime_attr,
    _get_workspace_path_for_umo,
    retrieve_knowledge_base,
)
from .config import MainAgentBuildConfig
from .providers import _provider_supports_modality

WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


async def _apply_kb(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: CoreExecutionContext,
    config: MainAgentBuildConfig,
) -> None:
    if not config.kb_agentic_mode:
        if req.prompt is None or not req.prompt.strip():
            return
        try:
            kb_result = await retrieve_knowledge_base(
                query=req.prompt,
                umo=event.unified_msg_origin,
                context=plugin_context,
            )
            if not kb_result:
                return
            req.extra_user_content_parts.append(
                TextPart(
                    text=f"[Related Knowledge Base Results]:\n{kb_result}",
                ).mark_as_temp()
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while retrieving knowledge base: %s", exc)


def _apply_prompt_prefix(req: ProviderRequest, cfg: dict) -> None:
    prefix = cfg.get("prompt_prefix")
    if not prefix:
        return
    prompt = req.prompt or ""
    if "{{prompt}}" in prefix:
        req.prompt = interpolate_placeholders(prefix, {"prompt": prompt})
    else:
        req.prompt = f"{prefix}{prompt}"


def _apply_workspace_extra_prompt(
    event: AstrMessageEvent,
    req: ProviderRequest,
) -> None:
    extra_prompt_path = _get_workspace_path_for_umo(event.unified_msg_origin) / (
        "EXTRA_PROMPT.md"
    )
    if not extra_prompt_path.is_file():
        return

    try:
        extra_prompt = extra_prompt_path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to read workspace extra prompt for umo=%s from %s: %s",
            event.unified_msg_origin,
            extra_prompt_path,
            exc,
        )
        return

    if not extra_prompt:
        return

    req.system_prompt = (
        f"{req.system_prompt or ''}\n"
        "[Workspace Extra Prompt]\n"
        "The following instructions are loaded from the current workspace "
        "`EXTRA_PROMPT.md` file.\n"
        f"{extra_prompt}\n"
    )


def _build_local_mode_prompt() -> str:
    system_name = platform.system() or "Unknown"
    if system_name.lower() != "windows":
        shell_hint = (
            "The runtime shell is Unix-like. Use POSIX-compatible shell commands."
        )
    elif Path(resolve_windows_shell()).name.lower().startswith("pwsh"):
        shell_hint = (
            "The runtime shell is PowerShell 7 (pwsh.exe). "
            "Use PowerShell 7-compatible syntax and cmdlets, and do not "
            "assume a full Unix userland or GNU utilities are available."
        )
    else:
        shell_hint = (
            "The runtime shell is Windows PowerShell 5.1 (powershell.exe). "
            "Use Windows PowerShell 5.1-compatible syntax and cmdlets; do not use "
            "PowerShell 7-only syntax or assume Unix commands like cat/ls/grep are available."
        )
    return (
        "Local computer tools are available subject to your role's file and execution permissions. "
        f"Current operating system: {system_name}. "
        f"{shell_hint} "
        "Long-running commands return managed sessions; use astrbot_shell_session "
        "with write_line for line-oriented programs."
    )


def _filter_skills_for_current_config(
    skills: list[SkillInfo],
    cfg: dict,
    plugins: PluginRegistry,
) -> list[SkillInfo]:
    plugin_set = cfg.get("plugin_set", ["*"])
    allowed_plugins = (
        None
        if not isinstance(plugin_set, list) or "*" in plugin_set
        else {str(name) for name in plugin_set}
    )
    plugin_by_root_dir = {
        metadata.root_dir_name: metadata
        for metadata in plugins.all()
        if metadata.root_dir_name
    }
    filtered: list[SkillInfo] = []
    for skill in skills:
        if skill.source_type != "plugin":
            filtered.append(skill)
            continue

        plugin = plugin_by_root_dir.get(skill.plugin_name)
        if not plugin or not plugin.activated:
            continue
        if plugin.reserved or allowed_plugins is None:
            filtered.append(skill)
            continue
        if plugin.name is not None and plugin.name in allowed_plugins:
            filtered.append(skill)
    return filtered


async def _inject_memory_context(
    req: ProviderRequest,
    event: AstrMessageEvent,
    memory_manager,
) -> None:
    if memory_manager is not None:
        try:
            await memory_manager.inject_context(
                req=req,
                event=event,
                query=req.prompt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to inject memory context: %s", exc)


def _append_skills_prompt(
    req: ProviderRequest,
    cfg: dict,
    prompt: PromptSpec | None,
    event: AstrMessageEvent,
    plugin_context: CoreExecutionContext,
) -> SkillSnapshot:
    runtime = str(cfg.get("computer_use_runtime", "none") or "none")
    profile = plugin_context.get_config(umo=event.unified_msg_origin)
    btw_config = btw_config_for(profile)
    btw_enabled = is_btw_enabled(profile)
    loop_mode = loop_mode_of(event.get_extra("btw_loop"))
    skills: list[SkillInfo] = []
    skill_manager: SkillManager | None = None
    try:
        skill_manager = plugin_context.skill_manager or SkillManager(
            builtin_skill_catalog=plugin_context.catalogs.builtin_skills,
        )
        skills = _filter_skills_for_current_config(
            skill_manager.list_skills(active_only=True, runtime=runtime),
            profile,
            plugin_context.catalogs.plugins,
        )
    except Exception:
        logger.exception("Failed to list skills while preparing LLM request.")
    if btw_enabled:
        skills = [
            skill
            for skill in skills
            if route_is_available_in_loop(
                btw_config.get("skill_routes"),
                route_key="skill_name",
                route_id=skill.name,
                loop_mode=loop_mode,
            )
        ]
    workspace_skills = (
        skill_manager.list_workspace_skills(
            _get_workspace_path_for_umo(event.unified_msg_origin)
        )
        if skill_manager
        and runtime == "local"
        and (not btw_enabled or loop_mode == "work")
        else []
    )
    if prompt and prompt.get("skills") is not None:
        if not prompt["skills"]:
            skills = []
        else:
            allowed = set(prompt["skills"])
            skills = [skill for skill in skills if skill.name in allowed]
    if workspace_skills and (not prompt or prompt.get("skills") != []):
        skills_by_name = {skill.name: skill for skill in skills}
        for skill in workspace_skills:
            skills_by_name[skill.name] = skill
        skills = [skills_by_name[name] for name in sorted(skills_by_name)]
    snapshot = freeze_skill_snapshot(skills, runtime=runtime)
    event.set_extra(SKILL_SNAPSHOT_EXTRA_KEY, snapshot)
    event.set_extra(
        PROMPT_TOOLS_EXTRA_KEY,
        None if not prompt else prompt.get("tools"),
    )
    if not snapshot.skills:
        return snapshot
    req.system_prompt += (
        f"\n{build_skills_prompt(_skill_infos_from_snapshot(snapshot))}\n"
    )
    if runtime == "none":
        req.system_prompt += (
            "User has not enabled the Computer Use feature. "
            "You cannot execute Shell or Python. "
            "You can still read Skill manuals with `read_skill`. "
            "If you need Shell or Python, ask the user to enable Computer Use "
            "in the AstrBot WebUI -> Config."
        )
    return snapshot


def _skill_infos_from_snapshot(snapshot: SkillSnapshot) -> list[SkillInfo]:
    return [
        SkillInfo(
            name=skill.name,
            description=skill.description,
            path=skill.runtime_copy,
            active=True,
            source_type=skill.source_type,
            source_label=skill.source_label,
            plugin_name=skill.plugin_name,
            declared_tools=skill.declared_tools,
        )
        for skill in snapshot.skills
    ]


async def _ensure_prompt_and_skills(
    req: ProviderRequest,
    cfg: dict,
    plugin_context: CoreExecutionContext,
    event: AstrMessageEvent,
) -> None:
    """Ensure prompt and skills are applied to the request's system prompt or user prompt."""
    if not req.conversation:
        return

    (
        prompt_id,
        prompt_spec,
        _,
        use_webchat_special_default,
    ) = await plugin_context.prompt_manager.resolve_selected_prompt(
        umo=event.unified_msg_origin,
        conversation_prompt_id=req.conversation.prompt_id,
        platform_name=event.get_platform_name(),
    )

    set_prompt_custom_error_message_on_event(
        event, extract_prompt_custom_error_message_from_prompt(prompt_spec)
    )

    if req.system_prompt is None:
        req.system_prompt = ""

    if prompt_spec:
        # Inject prompt system prompt
        if prompt_text := prompt_spec["prompt"]:
            req.system_prompt += f"\n# Prompt Instructions\n\n{prompt_text}\n"
        if begin_dialogs := copy.deepcopy(prompt_spec.get("_begin_dialogs_processed")):
            req.contexts[:0] = begin_dialogs
    elif (
        use_webchat_special_default
        and event.get_extra("enable_default_system_prompt") is not False
    ):
        req.system_prompt += CHATUI_SPECIAL_DEFAULT_PROMPT

    memory_manager = _get_context_runtime_attr(plugin_context, "memory_manager")
    await _inject_memory_context(req, event, memory_manager)

    _append_skills_prompt(req, cfg, prompt_spec, event, plugin_context)
    try:
        event.trace.record(
            "sel_prompt",
            prompt_id=prompt_id,
            prompt_toolset=[],
        )
    except Exception:
        pass


def _append_system_reminders(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
    timezone: str | None,
) -> None:
    persistent_system_parts: list[str] = []
    transient_system_parts: list[str] = []
    if cfg.get("identifier"):
        user_id = event.message_obj.sender.user_id
        user_nickname = event.message_obj.sender.nickname
        persistent_system_parts.append(f"User ID: {user_id}, Nickname: {user_nickname}")

    if cfg.get("group_name_display") and event.message_obj.group_id:
        if not event.message_obj.group:
            logger.error(
                "Group name display enabled but group object is None. Group ID: %s",
                event.message_obj.group_id,
            )
        else:
            group_name = event.message_obj.group.group_name
            if group_name:
                persistent_system_parts.append(f"Group name: {group_name}")

    if cfg.get("datetime_system_prompt"):
        now = None
        if timezone:
            try:
                now = datetime.datetime.now(zoneinfo.ZoneInfo(timezone))
            except Exception as exc:  # noqa: BLE001
                logger.error("时区设置错误: %s, 使用本地时区", exc)
        if now is None:
            now = datetime.datetime.now().astimezone()
        current_time = now.strftime("%Y-%m-%d %H:%M (%Z)")
        weekday = WEEKDAY_NAMES[now.weekday()]
        transient_system_parts.append(
            f"Current datetime: {current_time}, Weekday: {weekday}"
        )

    if persistent_system_parts:
        req.extra_user_content_parts.append(
            TextPart(
                text=(
                    "<system_reminder>"
                    + "\n".join(persistent_system_parts)
                    + "</system_reminder>"
                )
            )
        )
    if transient_system_parts:
        req.extra_user_content_parts.append(
            TextPart(
                text=(
                    "<system_reminder>"
                    + "\n".join(transient_system_parts)
                    + "</system_reminder>"
                )
            ).mark_as_temp()
        )


async def _decorate_llm_request(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: CoreExecutionContext,
    config: MainAgentBuildConfig,
    provider: ChatModel | None = None,
) -> None:
    cfg = config.provider_settings or plugin_context.get_config(
        umo=event.unified_msg_origin
    ).get("provider_settings", {})

    _apply_prompt_prefix(req, cfg)

    main_provider_supports_image = provider is not None and _provider_supports_modality(
        provider, "image"
    )
    img_cap_prov_id: str = cfg.get("default_image_caption_provider_id") or ""
    quote_images_already_captioned = False

    if req.conversation:
        await _ensure_prompt_and_skills(req, cfg, plugin_context, event)

        if img_cap_prov_id and req.image_urls and not main_provider_supports_image:
            await _ensure_img_caption(
                event,
                req,
                cfg,
                plugin_context,
                img_cap_prov_id,
            )
            quote_images_already_captioned = True

    quoted_message_settings = _get_quoted_message_parser_settings(cfg)
    await _process_quote_message(
        event,
        req,
        img_cap_prov_id,
        plugin_context,
        quoted_message_settings,
        config,
        main_provider_supports_image=main_provider_supports_image,
        skip_quote_image_caption=quote_images_already_captioned,
    )

    tz = config.timezone
    if tz is None:
        tz = plugin_context.get_config().get("timezone")
    _append_system_reminders(event, req, cfg, tz)
    _apply_workspace_extra_prompt(event, req)
