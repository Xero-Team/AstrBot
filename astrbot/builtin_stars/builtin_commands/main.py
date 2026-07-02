from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr

from .commands import (
    AdminCommands,
    ConversationCommands,
    HelpCommand,
    LLMCommands,
    NameCommand,
    PersonaCommands,
    PluginCommands,
    ProviderCommands,
    SetUnsetCommands,
    SIDCommand,
)


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        self.context = context

        self.admin_c = AdminCommands(self.context)
        self.conversation_c = ConversationCommands(self.context)
        self.help_c = HelpCommand(self.context)
        self.llm_c = LLMCommands(self.context)
        self.name_c = NameCommand(self.context)
        self.persona_c = PersonaCommands(self.context)
        self.plugin_c = PluginCommands(self.context)
        self.provider_c = ProviderCommands(self.context)
        self.setunset_c = SetUnsetCommands(self.context)
        self.sid_c = SIDCommand(self.context)

    @filter.command("help")
    async def help(self, event: AstrMessageEvent) -> None:
        """Show help message"""
        await self.help_c.help(event)

    @filter.command("sid")
    async def sid(self, event: AstrMessageEvent) -> None:
        """Get session ID and other related information"""
        await self.sid_c.sid(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("name")
    async def name(self, event: AstrMessageEvent, alias: GreedyStr) -> None:
        """Set display name for current UMO"""
        await self.name_c.name(event, alias)

    @filter.command("reset")
    async def reset(self, message: AstrMessageEvent) -> None:
        """Reset conversation history"""
        await self.conversation_c.reset(message)

    @filter.command("stop")
    async def stop(self, message: AstrMessageEvent) -> None:
        """Stop agent execution"""
        await self.conversation_c.stop(message)

    @filter.command("new")
    async def new_conv(self, message: AstrMessageEvent) -> None:
        """Create new conversation"""
        await self.conversation_c.new_conv(message)

    @filter.command("stats")
    async def stats(self, message: AstrMessageEvent) -> None:
        """Show token usage statistics for the current conversation"""
        await self.conversation_c.stats(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("provider")
    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ) -> None:
        """View or switch LLM Provider"""
        await self.provider_c.provider(event, idx, idx2)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("model")
    async def model(
        self,
        event: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ) -> None:
        """View or switch the current model"""
        await self.provider_c.model_ls(event, idx_or_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("dashboard_update")
    async def update_dashboard(self, event: AstrMessageEvent) -> None:
        """Update AstrBot WebUI"""
        await self.admin_c.update_dashboard(event)

    @filter.command("set")
    async def set_variable(self, event: AstrMessageEvent, key: str, value: str) -> None:
        """Set session variable"""
        await self.setunset_c.set_variable(event, key, value)

    @filter.command("unset")
    async def unset_variable(self, event: AstrMessageEvent, key: str) -> None:
        """Unset session variable"""
        await self.setunset_c.unset_variable(event, key)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("llm")
    async def llm(self, event: AstrMessageEvent) -> None:
        """Enable or disable LLM chat for the current session"""
        await self.llm_c.llm(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("op")
    async def op(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """Grant admin permission"""
        await self.admin_c.op(event, admin_id)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("deop")
    async def deop(self, event: AstrMessageEvent, admin_id: str = "") -> None:
        """Revoke admin permission"""
        await self.admin_c.deop(event, admin_id)

    @filter.command("history")
    async def history(self, event: AstrMessageEvent, page: int = 1) -> None:
        """Show conversation history"""
        await self.conversation_c.his(event, page)

    @filter.command("ls")
    async def convs(self, event: AstrMessageEvent, page: int = 1) -> None:
        """Show conversation list"""
        await self.conversation_c.convs(event, page)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("groupnew")
    async def groupnew(self, event: AstrMessageEvent, sid: str = "") -> None:
        """Create a new conversation for a target group"""
        await self.conversation_c.groupnew_conv(event, sid)

    @filter.command("switch")
    async def switch(self, event: AstrMessageEvent, index: int | None = None) -> None:
        """Switch to a listed conversation"""
        await self.conversation_c.switch_conv(event, index)

    @filter.command("rename")
    async def rename(self, event: AstrMessageEvent) -> None:
        """Rename the current conversation"""
        await self.conversation_c.rename_conv(event)

    @filter.command("del")
    async def delete(self, event: AstrMessageEvent) -> None:
        """Delete the current conversation"""
        await self.conversation_c.del_conv(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("persona")
    async def persona(self, event: AstrMessageEvent) -> None:
        """View or switch persona"""
        await self.persona_c.persona(event)

    @filter.command_group("plugin")
    def plugin(self) -> None:
        """Plugin management"""

    @plugin.command("ls")
    async def plugin_ls(self, event: AstrMessageEvent) -> None:
        """List loaded plugins"""
        await self.plugin_c.plugin_ls(event)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("off")
    async def plugin_off(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """Disable a plugin"""
        await self.plugin_c.plugin_off(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("on")
    async def plugin_on(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """Enable a plugin"""
        await self.plugin_c.plugin_on(event, plugin_name)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @plugin.command("get")
    async def plugin_get(self, event: AstrMessageEvent, plugin_repo: str = "") -> None:
        """Install a plugin"""
        await self.plugin_c.plugin_get(event, plugin_repo)

    @plugin.command("help")
    async def plugin_help(self, event: AstrMessageEvent, plugin_name: str = "") -> None:
        """Show plugin help"""
        await self.plugin_c.plugin_help(event, plugin_name)
