from typing import Protocol, cast

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry


class _PluginManager(Protocol):
    async def turn_off_plugin(self, plugin_name: str) -> None: ...

    async def turn_on_plugin(self, plugin_name: str) -> None: ...

    async def install_plugin(self, repo_url: str) -> None: ...


class PluginCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def list_plugins(self, event: AstrMessageEvent) -> None:
        """List loaded plugins."""
        parts = ["Loaded plugins:\n"]
        for plugin in self.context.get_all_stars():
            line = f"- `{plugin.name}` by {plugin.author}: {plugin.desc}"
            if not plugin.activated:
                line += " (disabled)"
            parts.append(line + "\n")

        if len(parts) == 1:
            plugin_list_info = "No plugins are currently loaded."
        else:
            plugin_list_info = "".join(parts)

        plugin_list_info += (
            "\nUse /plugin show <plugin> to inspect commands.\n"
            "Use /plugin enable <plugin> or /plugin disable <plugin> to change its state."
        )
        event.set_result(
            MessageEventResult().message(plugin_list_info).use_t2i(False),
        )

    async def disable(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Disable a plugin."""
        if self.context.demo_mode:
            event.set_result(
                MessageEventResult().message("Cannot disable plugins in demo mode."),
            )
            return
        star_manager = cast(_PluginManager | None, self.context._star_manager)
        if star_manager is None:
            event.set_result(
                MessageEventResult().message("Plugin manager is not available."),
            )
            return
        await star_manager.turn_off_plugin(plugin_name)
        event.set_result(
            MessageEventResult().message(f"✅ Plugin `{plugin_name}` disabled."),
        )

    async def enable(self, event: AstrMessageEvent, plugin_name: str) -> None:
        """Enable a plugin."""
        if self.context.demo_mode:
            event.set_result(
                MessageEventResult().message("Cannot enable plugins in demo mode."),
            )
            return
        star_manager = cast(_PluginManager | None, self.context._star_manager)
        if star_manager is None:
            event.set_result(
                MessageEventResult().message("Plugin manager is not available."),
            )
            return
        await star_manager.turn_on_plugin(plugin_name)
        event.set_result(
            MessageEventResult().message(f"✅ Plugin `{plugin_name}` enabled."),
        )

    async def install(self, event: AstrMessageEvent, plugin_repo: str) -> None:
        """Install a plugin from a repo URL."""
        if self.context.demo_mode:
            event.set_result(
                MessageEventResult().message("Cannot install plugins in demo mode."),
            )
            return
        logger.info("Preparing to install plugin from %s", plugin_repo)
        star_mgr = cast(_PluginManager | None, self.context._star_manager)
        if star_mgr is None:
            event.set_result(
                MessageEventResult().message("Plugin manager is not available."),
            )
            return

        try:
            await star_mgr.install_plugin(plugin_repo)
        except Exception as exc:
            logger.error("Plugin installation failed: %s", exc)
            event.set_result(
                MessageEventResult().message(f"❌ Failed to install plugin: {exc}"),
            )
            return

        event.set_result(
            MessageEventResult().message("✅ Plugin installed successfully."),
        )

    async def show(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
    ) -> None:
        """Show plugin metadata and commands."""
        plugin = self.context.get_registered_star(plugin_name)
        if plugin is None:
            event.set_result(MessageEventResult().message("Plugin not found."))
            return

        help_msg = f"\n\nAuthor: {plugin.author}\nVersion: {plugin.version}"
        command_entries: list[tuple[str, StarHandlerMetadata]] = []

        for handler in star_handlers_registry:
            if not isinstance(handler, StarHandlerMetadata):
                continue
            if handler.handler_module_path != plugin.module_path:
                continue
            for filter_ in handler.event_filters:
                if isinstance(filter_, CommandFilter):
                    command_entries.append(
                        (
                            filter_.format_invocation(
                                command_name=filter_.get_complete_command_names()[0],
                                include_aliases=True,
                            ),
                            handler,
                        )
                    )
                    break
                if isinstance(filter_, CommandGroupFilter):
                    command_entries.append(
                        (
                            filter_.format_invocation(
                                command_name=filter_.get_complete_command_names()[0],
                                include_aliases=True,
                            ),
                            handler,
                        )
                    )
                    break

        if command_entries:
            command_entries.sort(key=lambda item: item[0].lower())
            parts = ["\n\nCommands:\n"]
            for command_name, handler in command_entries:
                line = f"- /{command_name}"
                if handler.desc:
                    line += f": {handler.desc}"
                parts.append(line + "\n")
            parts.append(
                "\nTip: commands are triggered through the configured wake prefix, usually `/`."
            )
            help_msg += "".join(parts)

        event.set_result(
            MessageEventResult()
            .message(
                f"Plugin `{plugin_name}` help:\n{help_msg}More details may be available in the plugin README.",
            )
            .use_t2i(False),
        )
