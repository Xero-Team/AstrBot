"""Capability preview for the BTW classifier.

This lives in the BTW package because only the opt-in dual-loop classifier
needs it. The default agent path must not import BTW.
"""

import copy
from dataclasses import replace
from typing import TYPE_CHECKING

from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.loop_policy import LOOP_WORK, resolve_computer_runtime
from astrbot.core.conversation_mgr import DIALOGUE_LOOP_SCOPE, WORK_LOOP_SCOPE
from astrbot.core.platform.astr_message_event import AstrMessageEvent

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext


async def resolve_btw_capabilities(
    event: AstrMessageEvent, plugin_context: CoreExecutionContext
) -> dict[str, list[dict[str, str]]]:
    """Preview both catalogs without running tools, hooks, models or creating history.

    Uses the same prompt resolution, Skill snapshots and catalog assembly as
    the main Agent. The returned allowlist contains no schemas or host paths;
    callers must redact its free-text fields before sending them off-device.
    """
    from astrbot.core.agent.request.config import local_agent_runtime_from_profile
    from astrbot.core.agent.request.prompts import _append_skills_prompt
    from astrbot.core.agent.request.tools import _assemble_request_tool_catalog

    profile = plugin_context.get_config(umo=event.unified_msg_origin)
    config, _ = local_agent_runtime_from_profile(profile)
    capabilities = {}
    for loop, scope in (
        ("conversation", DIALOGUE_LOOP_SCOPE),
        (LOOP_WORK, WORK_LOOP_SCOPE),
    ):
        probe = copy.copy(event)
        probe._extras = {"btw_loop": loop}
        runtime = resolve_computer_runtime(profile, loop, config.computer_use_runtime)
        loop_config = replace(
            config,
            computer_use_runtime=runtime,
            allow_computer_tools=runtime != "none",
            provider_settings={
                **config.provider_settings,
                "computer_use_runtime": runtime,
            },
        )
        manager = plugin_context.conversation_manager
        cid = await manager.get_curr_conversation_id(event.unified_msg_origin, scope)
        conversation = (
            await manager.get_conversation(event.unified_msg_origin, cid)
            if cid
            else None
        )
        (
            _,
            prompt,
            _,
            _,
        ) = await plugin_context.prompt_manager.resolve_selected_prompt(
            umo=event.unified_msg_origin,
            conversation_prompt_id=conversation.prompt_id if conversation else None,
            platform_name=event.get_platform_name(),
        )
        req = ProviderRequest()
        snapshot = _append_skills_prompt(
            req, loop_config.provider_settings, prompt, probe, plugin_context
        )
        _assemble_request_tool_catalog(probe, req, plugin_context, loop_config)
        tools = req.func_tool.tools if req.func_tool else []
        capabilities[loop] = [
            {"name": f"tool:{tool.name}", "summary": tool.description}
            for tool in tools
            if tool.name != "submit_work_task"
        ] + [
            {"name": f"skill:{skill.name}", "summary": skill.description}
            for skill in snapshot.skills
        ]
    return capabilities
