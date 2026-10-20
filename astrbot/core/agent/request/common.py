import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGES
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.tools.computer_tools import (
    normalize_umo_for_workspace,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_workspaces_path,
)

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext


LLM_ERROR_MESSAGE_EXTRA_KEY = "_llm_error_message"


def _set_llm_error_message(event: AstrMessageEvent, key: str, **params: str) -> None:
    """Format an internal LLM error in the requesting client's language.

    Args:
        event: Message event carrying the optional UI locale.
        key: Built-in error translation key.
        **params: Values interpolated into the message.
    """
    locale = event.get_extra("locale")
    if not isinstance(locale, str):
        locale = "zh-CN"
    messages = LLM_ERROR_MESSAGES.get(locale, LLM_ERROR_MESSAGES["zh-CN"])
    event.set_extra(LLM_ERROR_MESSAGE_EXTRA_KEY, messages[key].format(**params))


def _get_context_runtime_attr(plugin_context: CoreExecutionContext, name: str):
    return getattr(plugin_context, "__dict__", {}).get(name)


def _get_workspace_path_for_umo(umo: str) -> Path:
    normalized_umo = normalize_umo_for_workspace(umo)
    return Path(get_astrbot_workspaces_path()) / normalized_umo


async def retrieve_knowledge_base(*args: Any, **kwargs: Any) -> str | None:
    """Load the knowledge-base helper lazily to keep agent imports acyclic."""
    module = importlib.import_module("astrbot.core.tools.knowledge_base_tools")
    retrieve = getattr(module, "retrieve_knowledge_base")
    return await retrieve(*args, **kwargs)
