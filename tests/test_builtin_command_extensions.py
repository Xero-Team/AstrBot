from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.help import HelpCommand
from astrbot.builtin_stars.builtin_commands.commands.llm import LLMCommands
from astrbot.builtin_stars.builtin_commands.commands.persona import PersonaCommands
from astrbot.builtin_stars.builtin_commands.commands.plugin import PluginCommands
from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands
from astrbot.core.provider.entities import ProviderType
from astrbot.core.star.filter.command import CommandFilter, option
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)


class DummyEvent:
    def __init__(
        self,
        *,
        message_str: str,
        unified_msg_origin: str = "napcat:FriendMessage:42",
        platform_name: str = "napcat",
        platform_id: str = "napcat",
        role: str = "admin",
        group_id: str | None = None,
        sender_id: str = "42",
    ) -> None:
        self.message_str = message_str
        self.unified_msg_origin = unified_msg_origin
        self._platform_name = platform_name
        self._platform_id = platform_id
        self.role = role
        self._group_id = group_id
        self._sender_id = sender_id
        self.result = None
        self.extras: dict[str, object] = {}
        self.temporary_files: list[str] = []
        self.call_llm = False

    def set_result(self, result) -> None:
        self.result = result

    async def send(self, result) -> None:
        self.result = result

    def get_platform_name(self) -> str:
        return self._platform_name

    def get_platform_id(self) -> str:
        return self._platform_id

    def get_group_id(self) -> str | None:
        return self._group_id

    def get_sender_id(self) -> str:
        return self._sender_id

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value

    def track_temporary_local_file(self, path: str) -> None:
        self.temporary_files.append(path)

    def should_call_llm(self, call_llm: bool) -> None:
        self.call_llm = call_llm


def _plain_text(result) -> str:
    return result.chain[0].text


@pytest.mark.asyncio
async def test_help_command_defaults_to_plain_text(monkeypatch):
    async def fake_list_commands(_db):
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            },
            {
                "reserved": True,
                "enabled": True,
                "type": "command_group",
                "parent_signature": None,
                "effective_command": "plugin",
                "description": "Plugin management",
            },
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "model",
                "description": "View or switch the current model",
            },
        ]

    async def fake_dashboard_version():
        return "test-ui"

    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.command_management.list_commands",
        fake_list_commands,
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.get_dashboard_version",
        fake_dashboard_version,
    )

    command = HelpCommand(SimpleNamespace(get_db=lambda: object()))
    event = DummyEvent(message_str="help")
    await command.help(event)

    text = _plain_text(event.result)
    assert "AstrBot v" in text
    assert "/persona - View or switch persona" in text
    assert "/plugin - Plugin management" in text
    assert "/model - View or switch the current model" in text
    assert "/help --image" in text
    assert event.result.use_t2i_ is False
    assert event.call_llm is True


@pytest.mark.asyncio
async def test_help_command_supports_image_mode(monkeypatch):
    async def fake_list_commands(_db):
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.command_management.list_commands",
        fake_list_commands,
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.get_dashboard_version",
        fake_dashboard_version,
    )
    render_calls: list[dict[str, object]] = []

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        render_calls.append(
            {
                "text": text,
                "template_name": template_name,
            }
        )
        return "D:/Documents/Github/AstrBot/data/temp/help-card.png"

    async def fake_register_file(path: str) -> str:
        assert path == "D:/Documents/Github/AstrBot/data/temp/help-card.png"
        return "token-123"

    command = HelpCommand(
        SimpleNamespace(
            get_config=lambda umo=None: {
                "callback_api_base": "http://127.0.0.1:6185",
            },
            html_renderer=SimpleNamespace(render_t2i=fake_render_t2i),
            file_token_service=SimpleNamespace(register_file=fake_register_file),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert len(render_calls) == 1
    assert render_calls[0]["template_name"] == "astrbot_help"
    assert "help-grid" in str(render_calls[0]["text"])

    assert event.result.chain[0].file == (
        "http://127.0.0.1:6185/api/v1/files/tokens/token-123"
    )
    assert event.result.chain[0].path == ""
    assert event.result.use_t2i_ is False
    assert event.temporary_files == [
        "D:/Documents/Github/AstrBot/data/temp/help-card.png"
    ]
    assert event.call_llm is True


@pytest.mark.asyncio
async def test_help_command_sends_local_image_when_callback_url_is_unavailable(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "help-card.png"

    async def fake_list_commands(_db):
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        _ = text, template_name
        return str(image_path)

    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.command_management.list_commands",
        fake_list_commands,
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.get_dashboard_version",
        fake_dashboard_version,
    )
    command = HelpCommand(
        SimpleNamespace(
            html_renderer=SimpleNamespace(render_t2i=fake_render_t2i),
            file_token_service=SimpleNamespace(register_file=AsyncMock()),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert event.result.chain[0].file == image_path.resolve().as_uri()
    assert event.result.chain[0].path == str(image_path.resolve())
    assert event.result.use_t2i_ is False
    assert event.temporary_files == [str(image_path)]


@pytest.mark.asyncio
async def test_help_command_sends_local_image_when_file_token_registration_fails(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "help-card.png"

    async def fake_list_commands(_db):
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        _ = text, template_name
        return str(image_path)

    async def fake_register_file(path: str) -> str:
        assert path == str(image_path)
        raise RuntimeError("file service unavailable")

    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.command_management.list_commands",
        fake_list_commands,
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.get_dashboard_version",
        fake_dashboard_version,
    )
    command = HelpCommand(
        SimpleNamespace(
            get_config=lambda umo=None: {
                "callback_api_base": "http://127.0.0.1:6185",
            },
            html_renderer=SimpleNamespace(render_t2i=fake_render_t2i),
            file_token_service=SimpleNamespace(register_file=fake_register_file),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert event.result.chain[0].file == image_path.resolve().as_uri()
    assert event.result.chain[0].path == str(image_path.resolve())
    assert event.temporary_files == [str(image_path)]


@pytest.mark.asyncio
async def test_help_command_uses_file_token_for_local_image_when_callback_is_available(
    monkeypatch,
):
    async def fake_list_commands(_db):
        return [
            {
                "reserved": True,
                "enabled": True,
                "type": "command",
                "parent_signature": None,
                "effective_command": "persona",
                "description": "View or switch persona",
            }
        ]

    async def fake_dashboard_version():
        return "test-ui"

    async def fake_render_t2i(
        text: str,
        *,
        template_name: str | None = None,
    ) -> str:
        _ = text, template_name
        return "D:/Documents/Github/AstrBot/data/temp/help-card.png"

    async def fake_register_file(path: str) -> str:
        assert path == "D:/Documents/Github/AstrBot/data/temp/help-card.png"
        return "token-123"

    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.command_management.list_commands",
        fake_list_commands,
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.help.get_dashboard_version",
        fake_dashboard_version,
    )
    command = HelpCommand(
        SimpleNamespace(
            get_config=lambda umo=None: {
                "callback_api_base": "http://127.0.0.1:6185",
            },
            html_renderer=SimpleNamespace(render_t2i=fake_render_t2i),
            file_token_service=SimpleNamespace(register_file=fake_register_file),
        )
    )
    event = DummyEvent(message_str="help --image")
    await command.help(event, image=True)

    assert event.result.chain[0].file == (
        "http://127.0.0.1:6185/api/v1/files/tokens/token-123"
    )
    assert event.temporary_files == [
        "D:/Documents/Github/AstrBot/data/temp/help-card.png"
    ]


@pytest.mark.asyncio
async def test_plugin_help_lists_command_signatures_and_aliases():
    original_handlers = list(star_handlers_registry)
    original_star_map = dict(star_map)

    star_handlers_registry.clear()
    star_map.clear()

    try:
        plugin = StarMetadata(
            name="demo",
            author="Tester",
            version="1.2.3",
            module_path="plugin.demo",
            activated=True,
        )
        star_map["plugin.demo"] = plugin

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
        )
        greet_filter = CommandFilter("greet", alias={"hello"})
        greet_filter.init_handler_md(greet_handler)
        greet_handler.event_filters.append(greet_filter)
        star_handlers_registry.append(greet_handler)

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
        tools_handler.event_filters.append(CommandGroupFilter("tools", alias={"t"}))
        star_handlers_registry.append(tools_handler)

        context = SimpleNamespace(
            get_registered_star=lambda plugin_name: (
                plugin if plugin_name == "demo" else None
            )
        )
        command = PluginCommands(context)
        event = DummyEvent(message_str="plugin help demo")

        await command.plugin_help(event, "demo")

        text = _plain_text(event.result)
        assert (
            "/greet (name(str),force[--force/-f](bool)=False) [aliases: hello]" in text
        )
        assert "/tools [aliases: t]" in text
        assert "Greet someone" in text
        assert "Tool commands" in text
    finally:
        star_handlers_registry.clear()
        star_map.clear()
        for handler in original_handlers:
            star_handlers_registry.append(handler)
        star_map.update(original_star_map)


@pytest.mark.asyncio
async def test_llm_command_toggles_session_service_status(monkeypatch):
    calls: list[tuple[str, bool]] = []

    async def fake_is_enabled(umo: str) -> bool:
        assert umo == "napcat:FriendMessage:42"
        return True

    async def fake_set_status(umo: str, enabled: bool) -> None:
        calls.append((umo, enabled))

    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.llm.SessionServiceManager.is_llm_enabled_for_session",
        fake_is_enabled,
    )
    monkeypatch.setattr(
        "astrbot.builtin_stars.builtin_commands.commands.llm.SessionServiceManager.set_llm_status_for_session",
        fake_set_status,
    )

    command = LLMCommands(SimpleNamespace())
    event = DummyEvent(message_str="llm")
    await command.llm(event)

    assert calls == [("napcat:FriendMessage:42", False)]
    assert "disabled" in _plain_text(event.result)


@pytest.mark.asyncio
async def test_persona_command_switches_current_conversation_persona():
    updates: list[tuple[str, str]] = []

    async def get_curr_conversation_id(_umo: str) -> str:
        return "abcd-1234"

    async def get_conversation(**kwargs):
        _ = kwargs
        return SimpleNamespace(title="Current", persona_id=None)

    async def update_conversation(
        *, unified_msg_origin: str, persona_id: str, **kwargs
    ):
        _ = kwargs
        updates.append((unified_msg_origin, persona_id))

    async def get_default_runtime_persona(umo=None):
        _ = umo
        return {"name": "default"}

    async def resolve_selected_persona(**kwargs):
        _ = kwargs
        return (None, None, None, False)

    context = SimpleNamespace(
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=get_curr_conversation_id,
            get_conversation=get_conversation,
            update_conversation=update_conversation,
        ),
        persona_manager=SimpleNamespace(
            get_default_runtime_persona=get_default_runtime_persona,
            resolve_selected_persona=resolve_selected_persona,
            get_runtime_persona_by_id=lambda persona_id: (
                {"name": persona_id, "prompt": "prompt"}
                if persona_id == "assistant"
                else None
            ),
            get_folder_tree=None,
            personas=[],
        ),
        get_config=lambda umo=None: {"provider_settings": {}},
    )

    command = PersonaCommands(context)
    event = DummyEvent(message_str="persona assistant")
    await command.persona(event)

    assert updates == [("napcat:FriendMessage:42", "assistant")]
    assert "Persona updated" in _plain_text(event.result)


class DummyProvider:
    def __init__(self) -> None:
        self.model = "model-a"

    def meta(self):
        return SimpleNamespace(
            id="demo",
            model=self.model,
            provider_type=ProviderType.CHAT_COMPLETION,
        )

    async def get_models(self) -> list[str]:
        return ["model-a", "model-b"]

    def get_model(self) -> str:
        return self.model

    def set_model(self, model: str) -> None:
        self.model = model


@pytest.mark.asyncio
async def test_provider_model_ls_lists_and_switches_by_index():
    provider = DummyProvider()

    async def set_provider(**kwargs):
        _ = kwargs
        return None

    context = SimpleNamespace(
        provider_manager=SimpleNamespace(
            register_provider_change_hook=lambda hook: None,
            set_provider=set_provider,
        ),
        get_config=lambda umo=None: {"provider_settings": {}},
        get_using_provider=lambda umo=None: provider,
        get_all_providers=lambda: [provider],
        get_all_tts_providers=lambda: [],
        get_all_stt_providers=lambda: [],
        get_using_tts_provider=lambda umo=None: None,
        get_using_stt_provider=lambda umo=None: None,
    )

    command = ProviderCommands(context)

    list_event = DummyEvent(message_str="model")
    await command.model_ls(list_event)
    assert "Available models" in _plain_text(list_event.result)
    assert "model-b" in _plain_text(list_event.result)

    switch_event = DummyEvent(message_str="model 2")
    await command.model_ls(switch_event, 2)
    assert provider.model == "model-b"
    assert "Switched model successfully" in _plain_text(switch_event.result)
