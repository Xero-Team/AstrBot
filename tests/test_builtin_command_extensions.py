from types import SimpleNamespace

import pytest

from astrbot.builtin_stars.builtin_commands.commands.help import HelpCommand
from astrbot.builtin_stars.builtin_commands.commands.llm import LLMCommands
from astrbot.builtin_stars.builtin_commands.commands.persona import PersonaCommands
from astrbot.builtin_stars.builtin_commands.commands.provider import ProviderCommands
from astrbot.core.provider.entities import ProviderType


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


def _plain_text(result) -> str:
    return result.chain[0].text


@pytest.mark.asyncio
async def test_help_command_lists_rewritten_builtin_extension_commands(monkeypatch):
    async def fake_list_commands():
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

    command = HelpCommand(SimpleNamespace())
    event = DummyEvent(message_str="help")
    await command.help(event)

    text = _plain_text(event.result)
    assert "/persona - View or switch persona" in text
    assert "/plugin - Plugin management" in text
    assert "/model - View or switch the current model" in text


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

    async def update_conversation(*, unified_msg_origin: str, persona_id: str, **kwargs):
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
