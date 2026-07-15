from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig

from .context_utils import call_event_hook, call_handler

if TYPE_CHECKING:
    from astrbot.core.file_token_service import FileTokenService
    from astrbot.core.star import PluginManager
    from astrbot.core.utils.t2i.renderer import HtmlRenderer


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_manager: PluginManager  # 插件管理器对象
    astrbot_config_id: str
    html_renderer: HtmlRenderer
    file_token_service: FileTokenService
    call_handler = call_handler
    call_event_hook = call_event_hook
