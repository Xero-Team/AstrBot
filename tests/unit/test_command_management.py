from typing import Annotated

import pytest

from astrbot.core.db.po import CommandConfig
from astrbot.core.star.command_management import list_commands
from astrbot.core.star.filter.command import CommandFilter, option
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)
from astrbot.dashboard.services.command_service import CommandService


@pytest.mark.asyncio
async def test_list_commands_includes_signature_metadata(monkeypatch):
    original_handlers = list(star_handlers_registry)
    original_star_map = dict(star_map)

    star_handlers_registry.clear()
    star_map.clear()

    async def fake_get_command_configs():
        return []

    monkeypatch.setattr(
        "astrbot.core.star.command_management.db_helper.get_command_configs",
        fake_get_command_configs,
    )

    try:
        plugin = StarMetadata(
            name="demo",
            module_path="plugin.demo",
            activated=True,
        )
        star_map["plugin.demo"] = plugin

        async def tools(self, event) -> None: ...

        tools.__module__ = "plugin.demo"
        tools_handler = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.demo_tools",
            handler_name="tools",
            handler_module_path="plugin.demo",
            handler=tools,
            event_filters=[],
            desc="Tool commands",
        )
        tools_filter = CommandGroupFilter("tools", alias={"t"})
        tools_handler.event_filters.append(tools_filter)
        star_handlers_registry.append(tools_handler)

        async def greet(
            self,
            event,
            name: str,
            force: Annotated[bool, option("--force", "-f")] = False,
        ) -> None: ...

        greet.__module__ = "plugin.demo"
        greet_handler = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.demo_greet",
            handler_name="greet",
            handler_module_path="plugin.demo",
            handler=greet,
            event_filters=[],
            desc="Greet someone",
            extras_configs={"sub_command": True},
        )
        greet_filter = CommandFilter(
            "greet",
            alias={"hello"},
            parent_command_names=tools_filter.get_complete_command_names(),
        )
        greet_filter.init_handler_md(greet_handler)
        greet_handler.event_filters.append(greet_filter)
        star_handlers_registry.append(greet_handler)

        commands = await list_commands()

        assert len(commands) == 1
        group = commands[0]
        assert group["effective_command"] == "tools"
        assert group["signature"] == "tools"
        assert group["display_signature"] == "tools [aliases: t]"

        assert len(group["sub_commands"]) == 1
        sub_command = group["sub_commands"][0]
        assert sub_command["effective_command"] == "tools greet"
        assert (
            sub_command["signature"]
            == "tools greet (name(str),force[--force/-f](bool)=False)"
        )
        assert (
            sub_command["display_signature"]
            == "tools greet (name(str),force[--force/-f](bool)=False) [aliases: hello]"
        )
    finally:
        star_handlers_registry.clear()
        star_map.clear()
        for handler in original_handlers:
            star_handlers_registry.append(handler)
        star_map.update(original_star_map)


@pytest.mark.asyncio
async def test_command_service_finds_nested_subcommand_payload(monkeypatch):
    async def fake_list_commands():
        return [
            {
                "handler_full_name": "plugin.demo_tools",
                "sub_commands": [
                    {
                        "handler_full_name": "plugin.demo_greet",
                        "sub_commands": [],
                    }
                ],
            }
        ]

    monkeypatch.setattr(
        "astrbot.dashboard.services.command_service.list_commands",
        fake_list_commands,
    )

    payload = await CommandService._get_command_payload("plugin.demo_greet")

    assert payload == {
        "handler_full_name": "plugin.demo_greet",
        "sub_commands": [],
    }


@pytest.mark.asyncio
async def test_list_commands_uses_configured_aliases_in_display_signature(monkeypatch):
    original_handlers = list(star_handlers_registry)
    original_star_map = dict(star_map)

    star_handlers_registry.clear()
    star_map.clear()

    try:
        plugin = StarMetadata(
            name="demo",
            module_path="plugin.demo",
            activated=True,
        )
        star_map["plugin.demo"] = plugin

        async def greet(self, event, name: str) -> None: ...

        greet.__module__ = "plugin.demo"
        greet_handler = StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.demo_greet",
            handler_name="greet",
            handler_module_path="plugin.demo",
            handler=greet,
            event_filters=[],
            desc="Greet someone",
        )
        greet_filter = CommandFilter("greet", alias={"hello"})
        greet_filter.init_handler_md(greet_handler)
        greet_handler.event_filters.append(greet_filter)
        star_handlers_registry.append(greet_handler)

        async def fake_get_command_configs():
            return [
                CommandConfig(
                    handler_full_name="plugin.demo_greet",
                    plugin_name="demo",
                    module_path="plugin.demo",
                    original_command="greet",
                    resolved_command="welcome",
                    enabled=True,
                    extra_data={"resolved_aliases": ["hi", "yo"]},
                )
            ]

        monkeypatch.setattr(
            "astrbot.core.star.command_management.db_helper.get_command_configs",
            fake_get_command_configs,
        )

        commands = await list_commands()

        assert len(commands) == 1
        assert commands[0]["effective_command"] == "welcome"
        assert commands[0]["aliases"] == ["hi", "yo"]
        assert commands[0]["display_signature"] == "welcome (name(str)) [aliases: hi, yo]"
    finally:
        star_handlers_registry.clear()
        star_map.clear()
        for handler in original_handlers:
            star_handlers_registry.append(handler)
        star_map.update(original_star_map)
