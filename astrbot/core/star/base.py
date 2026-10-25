from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from astrbot.core.log import LogManager
from astrbot.core.utils.plugin_kv_store import PluginKVStoreMixin

logger = logging.getLogger("astrbot")


@dataclass(frozen=True, slots=True)
class StarDeclaration:
    """Static plugin declaration attached to a :class:`Star` subclass.

    Importing a plugin may create declarations, but it must not publish mutable
    state into a process-wide registry.  A runtime catalog materializes this
    declaration only after the plugin module has been validated.
    """

    star_cls_type: type[Star]
    module_path: str


class Star(PluginKVStoreMixin):
    """所有插件（Star）的父类，所有插件都应该继承于这个类"""

    author: str
    name: str
    logger: logging.Logger

    def __init__(self, context: Any, config: dict | None = None) -> None:
        # Keep the plugin context opaque: importing its concrete type for
        # annotations would create a star.base <-> star.plugin_context cycle.
        self.context: Any = context
        plugin_name = getattr(self.__class__, "__astrbot_plugin_logger_name__", None)
        self.logger = (
            LogManager.get_plugin_logger(plugin_name)
            if isinstance(plugin_name, str) and plugin_name
            else logging.getLogger("astrbot")
        )

    def _get_context_config(self, umo: str | None = None) -> Any:
        """Resolve the configuration bound to a unified message origin."""
        try:
            return self.context.config.get(umo)
        except Exception as exc:
            logger.debug("Unable to resolve plugin configuration: %s", exc)
            return None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__astrbot_star_declaration__ = StarDeclaration(
            star_cls_type=cls,
            module_path=cls.__module__,
        )

    async def text_to_image(
        self,
        text: str,
        *,
        template_name: str | None = None,
        umo: str | None = None,
    ) -> str:
        """将文本转换为图片。

        Args:
            text: The text to render.
            template_name: Explicit t2i template name. Takes precedence over
                the `t2i.active_template` value from the resolved configuration.
            umo: The unified_message_origin used to resolve the bound
                configuration file. Falls back to the default configuration
                when omitted or unbound.

        Returns:
            The rendered image path or URL.
        """
        if template_name is None:
            template_name = self._resolve_active_template(umo)
        return await self.context.rendering.text_to_image(
            text,
            template_name=template_name,
        )

    def _resolve_active_template(self, umo: str | None) -> str | None:
        """Return the active local text-to-image template for a context."""
        config_obj = self._get_context_config(umo)
        if not hasattr(config_obj, "get"):
            return None
        try:
            return (config_obj.get("t2i") or {}).get("active_template")
        except Exception:
            return None

    async def html_render(
        self,
        tmpl: str,
        data: dict,
        options: dict | None = None,
    ) -> str:
        """渲染 HTML"""
        return await self.context.rendering.html(
            tmpl,
            data,
            options=options,
        )

    async def initialize(self) -> None:
        """当插件被激活时会调用这个方法"""

    async def terminate(self) -> None:
        """当插件被禁用、重载插件时会调用这个方法"""

    def __del__(self) -> None:
        """[Deprecated] 当插件被禁用、重载插件时会调用这个方法"""
