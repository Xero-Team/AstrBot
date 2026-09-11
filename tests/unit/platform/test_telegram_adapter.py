import asyncio
import importlib
import ssl
import sys
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from telegram import (
    Animation,
    Audio,
    Chat,
    Document,
    Message,
    MessageEntity,
    PhotoSize,
    Update,
    User,
    Video,
    Voice,
)
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.request import HTTPXRequest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.core.command import CommandCatalog, CommandCatalogRegistration
from astrbot.core.pipeline.turn_router import LlmAccess, TurnRouteInput, route_turn
from astrbot.core.platform import Group
from astrbot.core.platform.contracts.onebot import OneBotActionValidationError
from astrbot.core.platform.contracts.telegram import (
    TELEGRAM_CAPABILITY_NAME,
    TelegramCallbackEvent,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import PluginRegistry, StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    HandlerRegistry,
    StarHandlerMetadata,
)
from astrbot.core.utils.proxy_route import set_global_network_config
from tests.fixtures.helpers import (
    NoopAwaitable,
    create_mock_file,
    create_mock_update,
    make_platform_config,
)
from tests.fixtures.mocks.telegram import (
    MockTelegramBuilder,
    MockTelegramNetworkError,
    create_mock_telegram_modules,
)

pytestmark = pytest.mark.platform


_TELEGRAM_PLATFORM_ADAPTER = None
_TELEGRAM_PLATFORM_EVENT = None
_TELEGRAM_MODULES: dict[str, object] = {}


def _build_telegram_patched_modules():
    mocks = create_mock_telegram_modules()
    return {
        "telegram": mocks["telegram"],
        "telegram.constants": mocks["telegram"].constants,
        "telegram.error": mocks["telegram"].error,
        "telegram.ext": mocks["telegram.ext"],
        "telegramify_markdown": mocks["telegramify_markdown"],
        "apscheduler": mocks["apscheduler"],
        "apscheduler.schedulers": mocks["apscheduler"].schedulers,
        "apscheduler.schedulers.asyncio": mocks["apscheduler"].schedulers.asyncio,
        "apscheduler.schedulers.background": mocks["apscheduler"].schedulers.background,
    }


def _load_telegram_module(module_name: str):
    module = _TELEGRAM_MODULES.get(module_name)
    if module is not None:
        return module

    with patch.dict(sys.modules, _build_telegram_patched_modules()):
        sys.modules.pop(module_name, None)
        module = importlib.import_module(module_name)

    sys.modules[module_name] = module
    _TELEGRAM_MODULES[module_name] = module
    return module


def _load_telegram_adapter():
    global _TELEGRAM_PLATFORM_ADAPTER
    if _TELEGRAM_PLATFORM_ADAPTER is not None:
        return _TELEGRAM_PLATFORM_ADAPTER

    module = _load_telegram_module("astrbot.core.platform.sources.telegram.tg_adapter")
    _TELEGRAM_PLATFORM_ADAPTER = module.TelegramPlatformAdapter
    return _TELEGRAM_PLATFORM_ADAPTER


def _load_telegram_platform_event():
    global _TELEGRAM_PLATFORM_EVENT
    if _TELEGRAM_PLATFORM_EVENT is not None:
        return _TELEGRAM_PLATFORM_EVENT

    module = _load_telegram_module("astrbot.core.platform.sources.telegram.tg_event")
    _TELEGRAM_PLATFORM_EVENT = module.TelegramPlatformEvent
    return _TELEGRAM_PLATFORM_EVENT


def _build_context() -> MagicMock:
    context = MagicMock()
    context.bot.username = "test_bot"
    context.bot.id = 12345678
    return context


def _build_real_reply_update(
    text: str,
    *,
    reply_user_id: int = 12345678,
    reply_username: str = "test_bot",
) -> Update:
    chat = Chat(id=-10001, type="group", title="Test group")
    replied_message = Message(
        message_id=22,
        date=datetime.now(UTC),
        chat=chat,
        from_user=User(
            id=reply_user_id,
            first_name="Reply sender",
            is_bot=reply_user_id == 12345678,
            username=reply_username,
        ),
        text="earlier reply",
    )
    message = Message(
        message_id=23,
        date=datetime.now(UTC),
        chat=chat,
        from_user=User(
            id=987654321,
            first_name="Test user",
            is_bot=False,
            username="test_user",
        ),
        reply_to_message=replied_message,
        text=text,
    )
    return Update(update_id=1, message=message)


def _build_real_topic_update(
    *,
    chat_type: str,
    chat_id: int,
    message_thread_id: int,
    is_forum: bool | None = None,
    text: str = "topic message",
) -> Update:
    chat = Chat(id=chat_id, type=chat_type, is_forum=is_forum)
    message = Message(
        message_id=message_thread_id,
        date=datetime.now(UTC),
        chat=chat,
        from_user=User(42, "Alice", False),
        text=text,
        message_thread_id=message_thread_id,
        is_topic_message=True,
    )
    return Update(update_id=message_thread_id, message=message)


def _bind_runtime_registries(adapter) -> tuple[HandlerRegistry, PluginRegistry]:
    plugins = PluginRegistry()
    handlers = HandlerRegistry(plugins)
    adapter.bind_runtime_registries(handlers, plugins)
    return handlers, plugins


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("global_proxy", "no_proxy", "expected_proxy"),
    [
        ("http://127.0.0.1:7890", [], "http://127.0.0.1:7890"),
        ("", [], None),
        ("http://127.0.0.1:7890", ["api.telegram.org"], None),
    ],
)
async def test_telegram_request_clients_use_explicit_proxy_route(
    monkeypatch: pytest.MonkeyPatch,
    global_proxy: str,
    no_proxy: list[str],
    expected_proxy: str | None,
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.return_value = MockTelegramBuilder.create_application()
    monkeypatch.setenv("HTTP_PROXY", "http://environment.example:8080")
    set_global_network_config(http_proxy=global_proxy, no_proxy=no_proxy)

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
            "HTTPXRequest": HTTPXRequest,
        },
    ):
        TelegramPlatformAdapter(
            make_platform_config("telegram"),
            {},
            asyncio.Queue(),
        )

    bot_request = builder.request.call_args.args[0]
    updates_request = builder.get_updates_request.call_args.args[0]
    assert bot_request is not updates_request

    for request in (bot_request, updates_request):
        try:
            assert isinstance(request, HTTPXRequest)
            assert request._client_kwargs["proxy"] == expected_proxy
            assert request._client_kwargs["trust_env"] is False
            ssl_context = request._client_kwargs["verify"]
            assert isinstance(ssl_context, ssl.SSLContext)
            assert ssl_context.check_hostname is True
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        finally:
            await request._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_proxy", "api_uses_proxy", "file_uses_proxy"),
    [
        (["files.telegram.example"], True, False),
        (["api.telegram.example"], False, True),
    ],
)
async def test_telegram_request_client_routes_distinct_file_host(
    no_proxy: list[str],
    api_uses_proxy: bool,
    file_uses_proxy: bool,
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.return_value = MockTelegramBuilder.create_application()
    set_global_network_config(
        http_proxy="http://127.0.0.1:7890",
        no_proxy=no_proxy,
    )

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
            "HTTPXRequest": HTTPXRequest,
        },
    ):
        TelegramPlatformAdapter(
            make_platform_config(
                "telegram",
                telegram_api_base_url="https://api.telegram.example/bot",
                telegram_file_base_url="https://files.telegram.example/file/bot",
            ),
            {},
            asyncio.Queue(),
        )

    bot_request = builder.request.call_args.args[0]
    updates_request = builder.get_updates_request.call_args.args[0]
    try:
        api_transport = bot_request._client._transport_for_url(
            httpx.URL("https://api.telegram.example/botTEST/getMe")
        )
        file_transport = bot_request._client._transport_for_url(
            httpx.URL("https://files.telegram.example/file/botTEST/photo.jpg")
        )
        updates_transport = updates_request._client._transport_for_url(
            httpx.URL("https://api.telegram.example/botTEST/getUpdates")
        )

        assert (getattr(api_transport._pool, "_proxy_url", None) is not None) is (
            api_uses_proxy
        )
        assert (getattr(file_transport._pool, "_proxy_url", None) is not None) is (
            file_uses_proxy
        )
        assert (getattr(updates_transport._pool, "_proxy_url", None) is not None) is (
            api_uses_proxy
        )
    finally:
        await bot_request._client.aclose()
        await updates_request._client.aclose()


@pytest.mark.asyncio
async def test_telegram_partial_quote_uses_exact_quote_text():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    reply_update = create_mock_update(
        message_text="😀 prefix target suffix",
        message_id=42,
        user_id=1001,
        username="original_sender",
    )
    update = create_mock_update(
        message_text="What does this mean?",
        reply_to_message=reply_update.message,
        quote=MagicMock(text="target", position=10),
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Comp.Reply)
    assert reply.id == "42"
    assert reply.message_str == "target"
    assert reply.text == "target"
    assert reply.chain is not None
    assert len(reply.chain) == 1
    assert isinstance(reply.chain[0], Comp.Plain)
    assert reply.chain[0].text == "target"


@pytest.mark.asyncio
@pytest.mark.parametrize("quote_text", [None, ""])
async def test_telegram_reply_without_quote_text_uses_full_message(quote_text):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    reply_update = create_mock_update(
        message_text="Use the complete replied message",
        message_id=43,
        user_id=1002,
        username="original_sender",
    )
    update = create_mock_update(
        message_text="Follow-up question",
        reply_to_message=reply_update.message,
        quote=MagicMock(text=quote_text) if quote_text is not None else None,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Comp.Reply)
    assert reply.message_str == "Use the complete replied message"
    assert reply.text == "Use the complete replied message"
    assert reply.chain is not None
    assert len(reply.chain) == 1
    assert isinstance(reply.chain[0], Comp.Plain)
    assert reply.chain[0].text == "Use the complete replied message"


@pytest.mark.asyncio
async def test_telegram_document_caption_populates_message_text_and_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    document = create_mock_file("https://api.telegram.org/file/test/report.md")
    document.file_name = "report.md"
    mention = MagicMock(type="mention", offset=0, length=6)
    update = create_mock_update(
        message_text=None,
        document=document,
        caption="@alice 请总结这份文档",
        caption_entities=[mention],
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "@alice 请总结这份文档"
    assert any(isinstance(component, Comp.File) for component in result.message)
    file_component = next(
        component for component in result.message if isinstance(component, Comp.File)
    )
    assert file_component.url == ""
    document.get_file.assert_not_awaited()
    assert await file_component.get_file(allow_return_url=True) == (
        "https://api.telegram.org/file/test/report.md"
    )
    document.get_file.assert_awaited_once()
    assert any(
        isinstance(component, Comp.Plain) and component.text == "@alice 请总结这份文档"
        for component in result.message
    )
    assert any(
        isinstance(component, Comp.Mention) and component.target == "alice"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_video_caption_populates_message_text_and_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    video = create_mock_file("https://api.telegram.org/file/test/lesson.mp4")
    video.file_name = "lesson.mp4"
    update = create_mock_update(
        message_text=None,
        video=video,
        caption="这段视频讲了什么",
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "这段视频讲了什么"
    assert any(isinstance(component, Comp.Video) for component in result.message)
    video_component = next(
        component for component in result.message if isinstance(component, Comp.Video)
    )
    assert video_component.file == ""
    video.get_file.assert_not_awaited()
    assert any(
        isinstance(component, Comp.Plain) and component.text == "这段视频讲了什么"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_voice_message_creates_record_component(tmp_path):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    voice = create_mock_file("https://api.telegram.org/file/test/voice.oga")
    update = create_mock_update(
        message_text=None,
        voice=voice,
    )
    wav_path = tmp_path / "voice.oga.wav"
    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    voice.get_file.assert_not_awaited()

    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value=str(wav_path))
    with patch(
        "astrbot.core.message.components.MediaResolver",
        MagicMock(return_value=media_resolver),
    ):
        resolved_path = await result.message[0].convert_to_file_path()

    assert resolved_path == str(wav_path)
    voice.get_file.assert_awaited_once()
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")
    assert result.message[0].url == "https://api.telegram.org/file/test/voice.oga"


@pytest.mark.asyncio
async def test_telegram_voice_caption_and_metadata_are_preserved():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    voice = Voice(
        file_id="voice-id",
        file_unique_id="voice-unique",
        duration=7,
        mime_type="audio/ogg",
        file_size=1234,
    )
    update = create_mock_update(message_text=None, voice=voice, caption="listen")

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    record = result.message[0]
    assert isinstance(record, Comp.Record)
    assert record.metadata == {
        "file_id": "voice-id",
        "file_unique_id": "voice-unique",
        "mime_type": "audio/ogg",
        "duration": 7,
        "file_size": 1234,
    }
    assert result.message_str == "listen"
    assert isinstance(result.message[1], Comp.Plain)


@pytest.mark.asyncio
async def test_telegram_animation_is_distinct_and_lazy():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    animation = Animation(
        file_id="animation-id",
        file_unique_id="animation-unique",
        width=320,
        height=240,
        duration=3,
        file_name="clip.gif",
        mime_type="image/gif",
        file_size=88,
    )
    update = create_mock_update(message_text=None, animation=animation, caption="clip")

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    image = result.message[0]
    assert isinstance(image, Comp.Image)
    assert image.sub_type == "animation"
    assert image.metadata["file_id"] == "animation-id"
    assert image.metadata["file_name"] == "clip.gif"
    assert image.file == ""


@pytest.mark.asyncio
async def test_telegram_text_mention_preserves_numeric_identity():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    text = "😀 Alice"
    entity = MessageEntity(
        type="text_mention",
        offset=3,
        length=5,
        user=User(2468, "Alice", False),
    )
    update = create_mock_update(message_text=text, entities=[entity])

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    mention = next(part for part in result.message if isinstance(part, Comp.Mention))
    assert mention.target == "2468"
    assert mention.name == "Alice"
    assert result.message_str == text


@pytest.mark.asyncio
async def test_telegram_audio_caption_populates_message_text_and_plain(tmp_path):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    audio = create_mock_file("https://api.telegram.org/file/test/song.mp3")
    update = create_mock_update(
        message_text=None,
        audio=audio,
        caption="这首歌是什么",
    )
    wav_path = tmp_path / "song.mp3.wav"
    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "这首歌是什么"
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    audio.get_file.assert_not_awaited()
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message[1].text == "这首歌是什么"

    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value=str(wav_path))
    with patch(
        "astrbot.core.message.components.MediaResolver",
        MagicMock(return_value=media_resolver),
    ):
        resolved_path = await result.message[0].convert_to_file_path()

    assert resolved_path == str(wav_path)
    audio.get_file.assert_awaited_once()
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")
    assert result.message[0].url == "https://api.telegram.org/file/test/song.mp3"


@pytest.mark.asyncio
async def test_telegram_topic_group_message_uses_thread_scoped_session():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-1001234567890,
        message_thread_id=42,
        is_topic_message=True,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group_id == "-1001234567890#42"
    assert result.session_id == "-1001234567890#42"
    assert result.message_str == "Hello World"


@pytest.mark.asyncio
async def test_telegram_real_private_topics_use_distinct_route_identities():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    context = _build_context()

    first = await adapter.convert_message(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=41),
        context,
    )
    second = await adapter.convert_message(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=42),
        context,
    )
    ordinary = await adapter.convert_message(
        create_mock_update(chat_type="private", chat_id=99),
        context,
    )

    assert first is not None and second is not None and ordinary is not None
    assert first.session_id == "99#41"
    assert second.session_id == "99#42"
    assert ordinary.session_id == "99"

    first_event = adapter.create_event(first)
    second_event = adapter.create_event(second)
    assert first_event.unified_msg_origin != second_event.unified_msg_origin
    assert first_event.route_identity.target_id == "99#41"
    assert second_event.route_identity.target_id == "99#42"


@pytest.mark.asyncio
async def test_telegram_real_topic_routes_keep_general_and_group_semantics():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    context = _build_context()

    private_general = await adapter.convert_message(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=1),
        context,
    )
    group_general = await adapter.convert_message(
        _build_real_topic_update(
            chat_type="supergroup",
            chat_id=-100123,
            message_thread_id=1,
            is_forum=True,
        ),
        context,
    )
    group_topic = await adapter.convert_message(
        _build_real_topic_update(
            chat_type="supergroup",
            chat_id=-100123,
            message_thread_id=42,
            is_forum=True,
        ),
        context,
    )

    assert private_general is not None
    assert private_general.session_id == "99#1"
    client = MockTelegramBuilder.create_bot()
    TelegramPlatformEvent = _load_telegram_platform_event()
    await TelegramPlatformEvent.send_with_client(
        client,
        MessageChain([Comp.Plain("general")]),
        private_general.session_id,
    )
    assert client.send_message.await_args.kwargs == {
        "text": "general",
        "parse_mode": "MarkdownV2",
        "chat_id": "99",
    }
    assert group_general is not None
    assert group_general.group_id == "-100123"
    assert group_topic is not None
    assert group_topic.group_id == "-100123#42"


@pytest.mark.asyncio
async def test_telegram_topic_standard_and_proactive_sends_restore_thread():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    client = MockTelegramBuilder.create_bot()
    adapter.client = client
    context = _build_context()
    message = await adapter.convert_message(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=42),
        context,
    )
    assert message is not None

    event = adapter.create_event(message)
    event.session_id = "99"
    await event.send(MessageChain([Comp.Plain("reply")]))
    client.send_message.assert_awaited_once_with(
        text="reply",
        parse_mode="MarkdownV2",
        chat_id="99",
        message_thread_id="42",
    )

    client.reset_mock()
    result = await adapter.send_by_session(
        MessageSession(
            platform_name="test_telegram",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="99#42",
        ),
        MessageChain([Comp.Plain("proactive")]),
    )
    assert result is not None and result.success
    assert result.target == "99#42"
    client.send_message.assert_awaited_once_with(
        text="proactive",
        parse_mode="MarkdownV2",
        chat_id="99",
        message_thread_id="42",
    )


@pytest.mark.asyncio
async def test_telegram_private_topic_typing_uses_route_identity():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    client = MockTelegramBuilder.create_bot()
    adapter.client = client
    message = await adapter.convert_message(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=42),
        _build_context(),
    )
    assert message is not None

    event = adapter.create_event(message)
    event.session_id = "99"
    await event.send_typing()

    client.send_chat_action.assert_awaited_once_with(
        chat_id="99",
        action="typing",
        message_thread_id="42",
    )


@pytest.mark.asyncio
async def test_telegram_private_topic_streaming_routes_draft_and_final_message():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    client = MockTelegramBuilder.create_bot()
    adapter.client = client
    message = await adapter.convert_message(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=42),
        _build_context(),
    )
    assert message is not None

    async def generator():
        yield MessageChain([Comp.Plain("streamed")])

    event = adapter.create_event(message)
    event.session_id = "99"
    result = await event.send_streaming(generator())

    assert result is not None and result.success
    assert result.target == "99#42"
    assert client.send_message_draft.await_count == 1
    draft_call = client.send_message_draft.await_args.kwargs
    assert draft_call["chat_id"] == 99
    assert draft_call["message_thread_id"] == 42
    client.send_message.assert_awaited_once_with(
        text="streamed",
        parse_mode="MarkdownV2",
        chat_id="99",
        message_thread_id="42",
    )


@pytest.mark.asyncio
async def test_telegram_group_topic_streaming_keeps_thread():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    client = MockTelegramBuilder.create_bot()
    client.send_message.return_value = SimpleNamespace(message_id=100)
    adapter.client = client
    message = await adapter.convert_message(
        _build_real_topic_update(
            chat_type="supergroup",
            chat_id=-100123,
            message_thread_id=42,
            is_forum=True,
        ),
        _build_context(),
    )
    assert message is not None

    async def generator():
        yield MessageChain([Comp.Plain("streamed")])

    event = adapter.create_event(message)
    await event.send_streaming(generator())

    client.send_chat_action.assert_awaited_once_with(
        chat_id="-100123",
        action="typing",
        message_thread_id="42",
    )
    assert client.send_message.await_args.kwargs["chat_id"] == "-100123"
    assert client.send_message.await_args.kwargs["message_thread_id"] == "42"


@pytest.mark.asyncio
async def test_telegram_private_topic_start_reply_restores_thread():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram", start_message="hello start"),
        {},
        asyncio.Queue(),
    )
    context = _build_context()
    context.bot.send_message = AsyncMock()

    await adapter.start(
        _build_real_topic_update(chat_type="private", chat_id=99, message_thread_id=42),
        context,
    )

    context.bot.send_message.assert_awaited_once_with(
        chat_id=99,
        text="hello start",
        message_thread_id="42",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["summarize this", "/help"])
async def test_telegram_group_reply_to_bot_preserves_text_and_identity(text):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    context = _build_context()
    update = _build_real_reply_update(text)

    result = await adapter.convert_message(update, context)

    assert result is not None
    assert result.self_id == str(context.bot.id)
    assert result.message_str == text
    assert isinstance(result.message[0], Comp.Reply)
    assert result.message[0].sender_id == str(context.bot.id)
    assert any(
        isinstance(component, Comp.Plain) and component.text == text
        for component in result.message
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply_user_id", "reply_to_bot", "group", "expected_wake"),
    [
        (12345678, True, "off", True),
        (12345678, False, "off", False),
        (20000000, True, "off", False),
        (12345678, True, "prefix", True),
        (12345678, False, "prefix", False),
    ],
)
async def test_telegram_group_reply_wake_modes(
    reply_user_id,
    reply_to_bot,
    group,
    expected_wake,
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    result = await adapter.convert_message(
        _build_real_reply_update(
            "summarize this",
            reply_user_id=reply_user_id,
            reply_username="test_bot" if reply_user_id == 12345678 else "other_user",
        ),
        _build_context(),
    )

    assert result is not None
    route = route_turn(
        TurnRouteInput(
            message_str=result.message_str,
            messages=tuple(result.message),
            is_private=False,
            command_prefixes=("/",),
            llm_access=LlmAccess(group=group, reply_to_bot=reply_to_bot),
            catalog=CommandCatalog(),
            self_id=result.self_id,
        )
    )
    assert route.should_run_llm is expected_wake
    assert ("reply_to_bot" in route.wake_reasons) is expected_wake


@pytest.mark.asyncio
async def test_telegram_convert_message_with_get_reply_false_skips_reply_chain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    reply_to_message = create_mock_update(
        message_text="quoted",
        chat_type="group",
        chat_id=-10001,
        user_id=200,
        username="quoted_user",
        message_id=22,
    ).message
    update = create_mock_update(
        message_text="current",
        chat_type="group",
        chat_id=-10001,
        reply_to_message=reply_to_message,
    )

    result = await adapter.convert_message(update, _build_context(), get_reply=False)

    assert result is not None
    assert not any(isinstance(component, Comp.Reply) for component in result.message)
    assert result.message_str == "current"


@pytest.mark.asyncio
async def test_telegram_group_command_strips_only_current_bot_mention():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.username = "test_bot"
    context = _build_context()
    context.bot.username = "test_bot"
    mention = MagicMock(type="mention", offset=4, length=9)
    update = create_mock_update(
        message_text="/ask@test_bot hi",
        chat_type="group",
        chat_id=-10001,
        entities=[mention],
    )

    result = await adapter.convert_message(update, context)

    assert result is not None
    assert result.message_str == "/ask hi"
    assert any(
        isinstance(component, Comp.Mention)
        and component.target == str(context.bot.id)
        and component.name == "test_bot"
        for component in result.message
    )
    assert any(
        isinstance(component, Comp.Plain) and component.text == "/ask hi"
        for component in result.message
    )

    async def ask_handler(self, event) -> None:
        return None

    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.ask",
        "ask",
        "plugin.ask",
        ask_handler,
        [],
    )
    command_filter = CommandFilter("ask")
    command_filter.init_handler_md(metadata)
    route = route_turn(
        TurnRouteInput(
            message_str=result.message_str,
            messages=tuple(result.message),
            is_private=False,
            command_prefixes=("/",),
            llm_access=LlmAccess(group="off"),
            catalog=CommandCatalog(
                [
                    CommandCatalogRegistration(
                        metadata.handler_full_name,
                        metadata,
                        command_filter.schema,
                        (("ask",),),
                        command_filter,
                    )
                ]
            ),
            self_id=result.self_id,
        )
    )
    assert route.should_run_command is True


@pytest.mark.asyncio
async def test_telegram_group_command_keeps_other_bot_mentions():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.username = "test_bot"
    context = _build_context()
    context.bot.username = "test_bot"
    mention = MagicMock(type="mention", offset=5, length=10)
    update = create_mock_update(
        message_text="ping @other_bot",
        chat_type="group",
        chat_id=-10001,
        entities=[mention],
    )

    result = await adapter.convert_message(update, context)

    assert result is not None
    assert result.message_str == "ping @other_bot"
    assert any(
        isinstance(component, Comp.Mention) and component.target == "other_bot"
        for component in result.message
    )
    assert any(
        isinstance(component, Comp.Plain) and component.text == "ping @other_bot"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_topic_reply_to_thread_marker_does_not_create_reply_component():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    thread_marker = create_mock_update(
        message_text="topic marker",
        chat_type="supergroup",
        chat_id=-10001,
        message_id=42,
    ).message
    update = create_mock_update(
        message_text="topic reply",
        chat_type="supergroup",
        chat_id=-10001,
        message_thread_id=42,
        is_topic_message=True,
        reply_to_message=thread_marker,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group_id == "-10001#42"
    assert not any(isinstance(component, Comp.Reply) for component in result.message)
    assert any(
        isinstance(component, Comp.Plain) and component.text == "topic reply"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_document_with_missing_file_path_does_not_append_caption_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    document = create_mock_file(None)
    document.file_name = "report.md"
    update = create_mock_update(
        message_text=None,
        document=document,
        caption="ignored caption",
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.File)
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message_str == "ignored caption"
    assert await result.message[0].get_file(allow_return_url=True) == ""


@pytest.mark.asyncio
async def test_telegram_video_with_missing_file_path_does_not_append_caption_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    video = create_mock_file(None)
    video.file_name = "lesson.mp4"
    update = create_mock_update(
        message_text=None,
        video=video,
        caption="ignored caption",
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.Video)
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message_str == "ignored caption"
    with pytest.raises(Exception, match="not a valid file"):
        await result.message[0].convert_to_file_path()


@pytest.mark.asyncio
async def test_telegram_sticker_with_emoji_adds_image_and_plain_text():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    sticker = create_mock_file("https://api.telegram.org/file/test/sticker.webp")
    sticker.emoji = "🙂"
    update = create_mock_update(
        message_text=None,
        sticker=sticker,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert isinstance(result.message[0], Comp.Image)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    sticker.get_file.assert_not_awaited()
    assert result.message_str == "Sticker: 🙂"
    assert any(
        isinstance(component, Comp.Plain) and component.text == "Sticker: 🙂"
        for component in result.message
    )


_STICKER_URL = "https://api.telegram.org/file/test/sticker_1.webp"
_ANIMATED_URL = "https://api.telegram.org/file/test/sticker_1.tgs"
_VIDEO_URL = "https://api.telegram.org/file/test/sticker_1.webm"
_THUMBNAIL_URL = "https://api.telegram.org/file/test/thumb_1.webp"


def _make_sticker(
    file_path: str,
    *,
    is_animated: bool = False,
    is_video: bool = False,
    thumbnail_path: str | None = None,
):
    sticker = create_mock_file(file_path)
    sticker.emoji = "🙄"
    sticker.is_animated = is_animated
    sticker.is_video = is_video
    sticker.thumbnail = (
        create_mock_file(thumbnail_path) if thumbnail_path is not None else None
    )
    return sticker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_path", "flags", "expected_url"),
    [
        (_STICKER_URL, {}, _STICKER_URL),
        (_ANIMATED_URL, {"is_animated": True}, _THUMBNAIL_URL),
        (_VIDEO_URL, {"is_video": True}, _THUMBNAIL_URL),
    ],
    ids=["static", "animated", "video"],
)
async def test_telegram_sticker_uses_thumbnail_only_when_animated(
    file_path, flags, expected_url
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    sticker = _make_sticker(file_path, thumbnail_path=_THUMBNAIL_URL, **flags)
    update = create_mock_update(message_text=None, sticker=sticker)

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    images = [c for c in result.message if isinstance(c, Comp.Image)]
    assert len(images) == 1
    assert images[0].file == ""
    assert images[0].url == ""
    assert result.message_str == "Sticker: 🙄"


@pytest.mark.asyncio
async def test_telegram_animated_sticker_without_thumbnail_skips_image():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    sticker = _make_sticker(_ANIMATED_URL, is_animated=True, thumbnail_path=None)
    update = create_mock_update(message_text=None, sticker=sticker)

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert not any(isinstance(c, Comp.Image) for c in result.message)
    assert result.message_str == "Sticker: 🙄"


@pytest.mark.asyncio
async def test_telegram_video_note_becomes_video_component():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    video_note = create_mock_file("https://api.telegram.org/file/test/note.mp4")
    update = create_mock_update(message_text=None, video_note=video_note)

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Video)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    video_note.get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_start_command_sends_welcome_and_returns_none():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram", start_message="hello start"),
        {},
        asyncio.Queue(),
    )
    context = _build_context()
    context.bot.send_message = AsyncMock()
    update = create_mock_update(message_text="/start")

    result = await adapter.convert_message(update, context)

    assert result is None
    context.bot.send_message.assert_awaited_once_with(
        chat_id=update.effective_chat.id,
        text="hello start",
    )


@pytest.mark.asyncio
async def test_telegram_convert_message_returns_none_without_sender():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update()
    update.message.from_user = None

    result = await adapter.convert_message(update, _build_context())

    assert result is None


@pytest.mark.asyncio
async def test_telegram_register_commands_updates_commands_only_when_snapshot_changes():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.delete_my_commands = AsyncMock()
    adapter.client.set_my_commands = AsyncMock()
    command = SimpleNamespace(command="ask", description="Ask something")
    adapter.collect_commands = MagicMock(return_value=[command])

    await adapter.register_commands()
    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_not_called()
    adapter.client.set_my_commands.assert_awaited_once_with([command])
    assert adapter._last_command_snapshot == (("ask", "Ask something"),)


@pytest.mark.asyncio
async def test_telegram_register_commands_clears_stale_menu_when_no_commands():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.delete_my_commands = AsyncMock()
    adapter.client.set_my_commands = AsyncMock()
    adapter.collect_commands = MagicMock(return_value=[])

    await adapter.register_commands()
    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_awaited_once()
    adapter.client.set_my_commands.assert_not_awaited()
    assert adapter._last_command_snapshot == ()


@pytest.mark.asyncio
async def test_telegram_register_commands_retries_after_rejected_write():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    command = SimpleNamespace(command="ask", description="Ask something")
    adapter.collect_commands = MagicMock(return_value=[command])
    adapter.client.set_my_commands = AsyncMock(side_effect=RuntimeError("rejected"))

    await adapter.register_commands()

    assert adapter._last_command_snapshot is None
    adapter.client.set_my_commands.side_effect = None
    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_not_called()
    assert adapter.client.set_my_commands.await_count == 2
    assert adapter._last_command_snapshot == (("ask", "Ask something"),)


@pytest.mark.asyncio
async def test_telegram_register_commands_retries_after_timeout():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    command = SimpleNamespace(command="ask", description="Ask something")
    adapter.collect_commands = MagicMock(return_value=[command])
    adapter.client.set_my_commands = AsyncMock(side_effect=TimedOut())

    await adapter.register_commands()

    assert adapter._last_command_snapshot is None
    adapter.client.set_my_commands.side_effect = None
    await adapter.register_commands()

    assert adapter.client.set_my_commands.await_count == 2
    assert adapter._last_command_snapshot == (("ask", "Ask something"),)


@pytest.mark.asyncio
async def test_telegram_periodic_command_refresh_reconciles_unchanged_snapshot():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    command = SimpleNamespace(command="ask", description="Ask something")
    adapter.collect_commands = MagicMock(return_value=[command])
    adapter.client.set_my_commands = AsyncMock()

    await adapter.register_commands()
    await adapter.register_commands(reconcile=True)

    adapter.client.delete_my_commands.assert_not_called()
    assert adapter.client.set_my_commands.await_count == 2


def test_telegram_command_scheduler_requests_reconciliation():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.scheduler.running = False

    adapter._start_command_scheduler()

    assert adapter.scheduler.add_job.call_args.kwargs["kwargs"] == {"reconcile": True}


@pytest.mark.asyncio
async def test_telegram_native_command_refresh_requires_started_application():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.register_commands = AsyncMock()

    await adapter.refresh_registered_commands()
    adapter.register_commands.assert_not_awaited()

    adapter._application_started = True
    await adapter.refresh_registered_commands()
    adapter.register_commands.assert_awaited_once()


def test_telegram_collect_commands_filters_duplicates_invalid_and_inactive_handlers():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    handlers, plugins = _bind_runtime_registries(adapter)
    for metadata in (
        StarMetadata(
            name="Alpha",
            module_path="plugin.alpha",
            activated=True,
        ),
        StarMetadata(
            name="Beta",
            module_path="plugin.beta",
            activated=True,
        ),
        StarMetadata(
            name="Off",
            module_path="plugin.off",
            activated=False,
        ),
    ):
        plugins.publish(metadata)

    async def handler_alpha(event):
        return None

    async def handler_beta(event):
        return None

    async def handler_invalid(event):
        return None

    async def handler_off(event):
        return None

    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.alpha_handler_alpha",
            handler_name="handler_alpha",
            handler_module_path="plugin.alpha",
            handler=handler_alpha,
            event_filters=[
                CommandFilter("ask", alias={"ask_alias"}),
                CommandFilter("child", parent_command_names=["root"]),
            ],
            desc="Primary ask command",
            enabled=True,
        )
    )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.beta_handler_beta",
            handler_name="handler_beta",
            handler_module_path="plugin.beta",
            handler=handler_beta,
            event_filters=[
                CommandFilter("ask"),
                CommandGroupFilter("tools", alias={"toolbox"}),
            ],
            desc="Duplicate ask command should lose",
            enabled=True,
        )
    )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.beta_handler_invalid",
            handler_name="handler_invalid",
            handler_module_path="plugin.beta",
            handler=handler_invalid,
            event_filters=[CommandFilter("Bad-Name")],
            desc="Should be filtered out",
            enabled=True,
        )
    )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.off_handler_off",
            handler_name="handler_off",
            handler_module_path="plugin.off",
            handler=handler_off,
            event_filters=[CommandFilter("hidden")],
            desc="Inactive plugin",
            enabled=True,
        )
    )

    module_globals = adapter.collect_commands.__func__.__globals__
    with patch.dict(
        module_globals,
        {
            "BotCommand": lambda command, description: SimpleNamespace(
                command=command,
                description=description,
            )
        },
    ):
        commands = adapter.collect_commands()

    assert [(cmd.command, cmd.description) for cmd in commands] == [
        ("ask", "Primary ask command"),
        ("tools", "Duplicate ask command should l..."),
        ("ask_alias", "Primary ask command"),
        ("toolbox", "Duplicate ask command should l..."),
    ]


def test_telegram_collect_commands_caps_menu_at_100_entries():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    handlers, plugins = _bind_runtime_registries(adapter)
    plugins.publish(
        StarMetadata(
            name="Many commands",
            module_path="plugin.many",
            activated=True,
        )
    )

    async def handler(event):
        return None

    for index in range(101):
        handlers.append(
            StarHandlerMetadata(
                event_type=EventType.AdapterMessageEvent,
                handler_full_name=f"plugin.many_handler_{index}",
                handler_name=f"handler_{index}",
                handler_module_path="plugin.many",
                handler=handler,
                event_filters=[CommandFilter(f"cmd_{index:03d}")],
                desc=f"Command {index}",
                enabled=True,
            )
        )

    commands = adapter.collect_commands()

    assert len(commands) == 100
    assert commands[0].command == "cmd_000"
    assert commands[-1].command == "cmd_099"


def test_telegram_collect_commands_prioritizes_primary_commands_over_aliases():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    handlers, plugins = _bind_runtime_registries(adapter)
    plugins.publish(
        StarMetadata(
            name="Many commands",
            module_path="plugin.many",
            activated=True,
        )
    )

    async def handler(event):
        return None

    for index in range(100):
        handlers.append(
            StarHandlerMetadata(
                event_type=EventType.AdapterMessageEvent,
                handler_full_name=f"plugin.many_handler_{index}",
                handler_name=f"handler_{index}",
                handler_module_path="plugin.many",
                handler=handler,
                event_filters=[CommandFilter(f"cmd_{index:03d}")],
                desc=f"Command {index}",
                enabled=True,
            )
        )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.many_handler_primary",
            handler_name="handler_primary",
            handler_module_path="plugin.many",
            handler=handler,
            event_filters=[CommandFilter("aaa_primary", alias={"aaa_alias"})],
            desc="Primary command",
            enabled=True,
        )
    )

    commands = adapter.collect_commands()
    command_names = {command.command for command in commands}

    assert len(commands) == 100
    assert "aaa_primary" in command_names
    assert "aaa_alias" not in command_names


def test_telegram_extract_command_info_skips_nested_groups_and_long_descriptions():
    TelegramPlatformAdapter = _load_telegram_adapter()
    root_group = CommandGroupFilter("root")
    nested_group = CommandGroupFilter("nested", parent_group=root_group)
    handler_md = SimpleNamespace(
        desc="A very long description that should be truncated for Telegram clients",
    )

    group_result = TelegramPlatformAdapter._extract_command_info(
        nested_group,
        handler_md,
        {"start"},
    )
    command_result = TelegramPlatformAdapter._extract_command_info(
        CommandFilter("valid_name", alias={"alias_name"}),
        handler_md,
        {"start"},
    )

    assert group_result is None
    assert command_result == [
        ("valid_name", "A very long description that s..."),
        ("alias_name", "A very long description that s..."),
    ]


@pytest.mark.asyncio
async def test_telegram_message_handler_routes_media_groups_and_regular_messages():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    converted = SimpleNamespace(message_id="m1")
    adapter.handle_media_group_message = AsyncMock()
    adapter.convert_message = AsyncMock(return_value=converted)
    adapter.handle_msg = AsyncMock()
    context = _build_context()

    media_group_update = create_mock_update(media_group_id="album-1")
    await adapter.message_handler(media_group_update, context)

    regular_update = create_mock_update(media_group_id=None)
    regular_update.update_id = 2
    await adapter.message_handler(regular_update, context)

    adapter.handle_media_group_message.assert_awaited_once_with(
        media_group_update, context
    )
    adapter.convert_message.assert_awaited_once_with(regular_update, context)
    adapter.handle_msg.assert_awaited_once_with(converted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_register", "command_refresh"),
    [(False, False), (False, True), (True, False), (True, True)],
)
async def test_telegram_media_group_delivery_independent_of_menu(
    command_register: bool, command_refresh: bool
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.enable_command_register = command_register
    adapter.enable_command_refresh = command_refresh
    adapter.media_group_timeout = 0.01
    adapter.media_group_max_wait = 0.05
    adapter.scheduler = MockTelegramBuilder.create_scheduler()
    adapter.scheduler.running = False
    context = _build_context()
    update = create_mock_update(media_group_id="album-menu-independent")
    delivered = asyncio.Event()

    async def process(media_group_id: str, entry: dict) -> None:
        assert media_group_id == "album-menu-independent"
        assert entry["items"] == [(update, context)]
        delivered.set()

    adapter._process_media_group_entry = process
    adapter._start_command_scheduler()

    await adapter.handle_media_group_message(update, context)

    await asyncio.wait_for(delivered.wait(), timeout=0.5)
    assert not adapter.media_group_cache
    assert not adapter._media_group_tasks
    if command_register and command_refresh:
        adapter.scheduler.start.assert_called_once()
    else:
        adapter.scheduler.start.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_media_group_cleanup_cancels_pending_collection():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.media_group_timeout = 60.0
    adapter.media_group_max_wait = 60.0

    await adapter.handle_media_group_message(
        create_mock_update(media_group_id="album-cleanup"), _build_context()
    )
    assert adapter._media_group_tasks

    await adapter._cleanup_media_groups()

    assert not adapter.media_group_cache
    assert not adapter._media_group_tasks
    assert not adapter._accept_media_groups


@pytest.mark.asyncio
async def test_telegram_media_group_max_wait_is_a_hard_deadline():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.media_group_timeout = 0.10
    adapter.media_group_max_wait = 0.12
    delivered = asyncio.Event()
    started_at = asyncio.get_running_loop().time()
    processed_at: float | None = None

    async def process(media_group_id: str, entry: dict) -> None:
        nonlocal processed_at
        assert media_group_id == "album-deadline"
        assert len(entry["items"]) == 3
        processed_at = asyncio.get_running_loop().time()
        delivered.set()

    adapter._process_media_group_entry = process
    context = _build_context()
    await adapter.handle_media_group_message(
        create_mock_update(media_group_id="album-deadline", message_id=1), context
    )
    await asyncio.sleep(0.05)
    await adapter.handle_media_group_message(
        create_mock_update(media_group_id="album-deadline", message_id=2), context
    )
    await asyncio.sleep(0.05)
    await adapter.handle_media_group_message(
        create_mock_update(media_group_id="album-deadline", message_id=3), context
    )

    await asyncio.wait_for(delivered.wait(), timeout=0.25)
    assert processed_at is not None
    assert processed_at - started_at < 0.17
    assert not adapter.media_group_cache


@pytest.mark.asyncio
async def test_telegram_media_group_capacity_rejects_new_albums():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._MEDIA_GROUP_MAX_ACTIVE = 1
    adapter.media_group_timeout = 60.0
    adapter.media_group_max_wait = 60.0

    await adapter.handle_media_group_message(
        create_mock_update(media_group_id="album-first"), _build_context()
    )
    await adapter.handle_media_group_message(
        create_mock_update(media_group_id="album-second"), _build_context()
    )

    assert len(adapter.media_group_cache) == 1
    assert len(adapter._media_group_tasks) == 1
    await adapter._cleanup_media_groups()


@pytest.mark.asyncio
async def test_telegram_media_group_entry_merges_media_without_later_reply_chain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    first_reply = create_mock_update(
        message_text="first quoted",
        chat_type="group",
        chat_id=-20001,
        user_id=200,
        username="first_user",
        message_id=51,
    ).message
    second_reply = create_mock_update(
        message_text="second quoted",
        chat_type="group",
        chat_id=-20001,
        user_id=201,
        username="second_user",
        message_id=52,
    ).message
    first_update = create_mock_update(
        message_text=None,
        chat_type="group",
        chat_id=-20001,
        media_group_id="album-1",
        photo=[create_mock_file("https://api.telegram.org/file/test/photo.jpg")],
        caption="first caption",
        reply_to_message=first_reply,
    )
    second_document = create_mock_file("https://api.telegram.org/file/test/notes.txt")
    second_document.file_name = "notes.txt"
    second_update = create_mock_update(
        message_text=None,
        chat_type="group",
        chat_id=-20001,
        media_group_id="album-1",
        document=second_document,
        caption="second caption",
        reply_to_message=second_reply,
    )
    await adapter._process_media_group_entry(
        "album-1",
        {
            "items": [
                (first_update, _build_context()),
                (second_update, _build_context()),
            ]
        },
    )

    adapter.handle_msg.assert_awaited_once()
    merged_message = adapter.handle_msg.await_args.args[0]
    assert (
        sum(isinstance(component, Comp.Reply) for component in merged_message.message)
        == 1
    )
    assert any(
        isinstance(component, Comp.Image) for component in merged_message.message
    )
    assert any(isinstance(component, Comp.File) for component in merged_message.message)
    plain_texts = [
        component.text
        for component in merged_message.message
        if isinstance(component, Comp.Plain)
    ]
    assert plain_texts == ["first caption", "second caption"]
    assert merged_message.message_str == "first caption\nsecond caption"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item_texts", "expected"),
    [
        (["first caption", ""], "first caption"),
        (["", "later caption"], "later caption"),
        (
            ["first caption", "second caption", "third caption"],
            "first caption\nsecond caption\nthird caption",
        ),
        (["", ""], ""),
    ],
)
async def test_telegram_media_group_entry_merges_non_empty_item_texts(
    item_texts, expected
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()

    updates = []
    for index, caption in enumerate(item_texts):
        if index % 2:
            document = create_mock_file(
                f"https://api.telegram.org/file/test/document-{index}.txt"
            )
            document.file_name = f"document-{index}.txt"
            media = {"document": document}
        else:
            media = {
                "photo": [
                    create_mock_file(
                        f"https://api.telegram.org/file/test/photo-{index}.jpg"
                    )
                ]
            }
        updates.append(
            create_mock_update(
                message_text=None,
                chat_type="group",
                chat_id=-20001,
                message_id=index + 1,
                media_group_id="album-text",
                caption=caption,
                **media,
            )
        )

    entry = {"items": [(update, _build_context()) for update in updates]}

    await adapter._process_media_group_entry("album-text", entry)

    merged_message = adapter.handle_msg.await_args.args[0]
    assert merged_message.message_str == expected
    assert [
        component.text
        for component in merged_message.message
        if isinstance(component, Comp.Plain)
    ] == [text for text in item_texts if text]


@pytest.mark.asyncio
async def test_telegram_media_group_entry_returns_when_first_message_cannot_convert():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.convert_message = AsyncMock(return_value=None)
    adapter.handle_msg = AsyncMock()
    await adapter._process_media_group_entry(
        "album-empty",
        {
            "items": [
                (create_mock_update(media_group_id="album-empty"), _build_context())
            ]
        },
    )

    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_media_group_entry_skips_later_items_that_convert_to_none():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    first_abm = SimpleNamespace(
        message=[Comp.Plain("first"), Comp.Image(file="photo.jpg", url="photo.jpg")],
        message_str="first",
        message_id="m1",
        session_id="session-1",
    )
    entry = {
        "items": [
            (create_mock_update(media_group_id="album-skip-none"), _build_context()),
            (create_mock_update(media_group_id="album-skip-none"), _build_context()),
        ],
    }
    adapter.convert_message = AsyncMock(side_effect=[first_abm, None])

    await adapter._process_media_group_entry("album-skip-none", entry)

    adapter.handle_msg.assert_awaited_once_with(first_abm)


@pytest.mark.asyncio
async def test_telegram_media_group_entry_returns_when_items_empty():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    await adapter._process_media_group_entry("album-empty-items", {"items": []})

    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_media_group_entry_swallows_exceptions_from_later_items():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    first_abm = SimpleNamespace(
        message=[Comp.Plain("first")],
        message_str="first",
        message_id="m1",
        session_id="session-1",
    )
    second_update = create_mock_update(media_group_id="album-error")
    entry = {
        "items": [
            (create_mock_update(media_group_id="album-error"), _build_context()),
            (second_update, _build_context()),
        ],
    }
    adapter.convert_message = AsyncMock(
        side_effect=[first_abm, RuntimeError("extra convert failed")]
    )

    await adapter._process_media_group_entry("album-error", entry)

    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_send_voice_with_privacy_fallback_sends_document():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_voice = AsyncMock(
        side_effect=Exception("Voice_messages_forbidden by privacy")
    )
    client.send_document = AsyncMock()

    class FakeBadRequest(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.message = message

    send_voice_error = FakeBadRequest("Voice_messages_forbidden by privacy")
    client.send_voice.side_effect = send_voice_error
    tg_event_module = _load_telegram_module(
        "astrbot.core.platform.sources.telegram.tg_event"
    )

    with patch.object(tg_event_module, "BadRequest", FakeBadRequest):
        await TelegramPlatformEvent._send_voice_with_fallback(
            client,
            "voice.wav",
            {"chat_id": "123"},
            caption="voice caption",
            use_media_action=False,
        )

    client.send_voice.assert_awaited_once_with(voice="voice.wav", chat_id="123")
    client.send_document.assert_awaited_once_with(
        document="voice.wav",
        caption="voice caption",
        chat_id="123",
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_prefixes_at_and_reuses_reply_and_thread_id():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()

    await TelegramPlatformEvent.send_with_client(
        client,
        MessageChain(
            [
                Comp.Reply(id="42", chain=[]),
                Comp.Mention(target="alice", name="alice"),
                Comp.Plain("hello there"),
            ]
        ),
        "123#99",
    )

    client.send_chat_action.assert_awaited_once_with(
        chat_id="123",
        action="typing",
        message_thread_id="99",
    )
    client.send_message.assert_awaited_once_with(
        text="@alice hello there",
        parse_mode="MarkdownV2",
        chat_id="123",
        reply_to_message_id="42",
        message_thread_id="99",
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_prefixes_mention_target_when_name_missing():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()

    await TelegramPlatformEvent.send_with_client(
        client,
        MessageChain([Comp.Mention(target="alice"), Comp.Plain("hello there")]),
        "123",
    )

    client.send_message.assert_awaited_once_with(
        text="@alice hello there",
        parse_mode="MarkdownV2",
        chat_id="123",
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_prefixes_mention_all():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()

    await TelegramPlatformEvent.send_with_client(
        client,
        MessageChain([Comp.MentionAll(), Comp.Plain("hello there")]),
        "123",
    )

    client.send_message.assert_awaited_once_with(
        text="hello there", parse_mode="MarkdownV2", chat_id="123"
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_preserves_multiple_numeric_mentions():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()

    await TelegramPlatformEvent.send_with_client(
        client,
        MessageChain(
            [
                Comp.Mention(target="11", name="Alice"),
                Comp.Mention(target="22", name="Bob"),
                Comp.Plain("hello"),
            ]
        ),
        "123",
    )

    assert client.send_message.await_args.kwargs["text"] == (
        "[Alice](tg://user?id=11) [Bob](tg://user?id=22) hello"
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_batches_compatible_images():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    first = Comp.Image(file="first.jpg")
    second = Comp.Image(file="second.jpg")

    with patch.object(
        type(first),
        "convert_to_file_path",
        AsyncMock(side_effect=["first.jpg", "second.jpg"]),
    ):
        await TelegramPlatformEvent.send_with_client(
            client,
            MessageChain([first, second, Comp.Plain("caption")]),
            "123",
        )

    client.send_media_group.assert_awaited_once()
    media = client.send_media_group.await_args.kwargs["media"]
    assert len(media) == 2
    tg_event_module = _load_telegram_module(
        "astrbot.core.platform.sources.telegram.tg_event"
    )
    assert (
        tg_event_module.InputMediaPhoto.call_args_list[0].kwargs["caption"] == "caption"
    )
    assert tg_event_module.InputMediaPhoto.call_args_list[1].kwargs["caption"] is None
    client.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_send_with_client_uses_animation_for_gif(monkeypatch):
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_animation = AsyncMock()
    image = Comp.Image(file="C:/tmp/anim.gif")
    tg_event_module = _load_telegram_module(
        "astrbot.core.platform.sources.telegram.tg_event"
    )
    monkeypatch.setattr(tg_event_module, "_is_gif", lambda _path: True)

    with patch.object(
        type(image),
        "convert_to_file_path",
        AsyncMock(return_value="C:/tmp/anim.gif"),
    ):
        await TelegramPlatformEvent.send_with_client(
            client,
            MessageChain([image]),
            "456",
        )

    client.send_animation.assert_awaited_once_with(
        animation="C:/tmp/anim.gif", chat_id="456"
    )
    client.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_send_with_client_sends_record_caption_as_document_fallback():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    record = Comp.Record(file="voice.wav")
    record.text = "voice caption"

    with (
        patch.object(
            type(record),
            "convert_to_file_path",
            AsyncMock(return_value="voice.wav"),
        ),
        patch.object(
            TelegramPlatformEvent,
            "_send_voice_with_fallback",
            AsyncMock(),
        ) as send_voice_with_fallback,
    ):
        await TelegramPlatformEvent.send_with_client(
            client,
            MessageChain([record]),
            "789",
        )

    send_voice_with_fallback.assert_awaited_once_with(
        client,
        "voice.wav",
        {"chat_id": "789"},
        caption="voice caption",
        use_media_action=False,
    )


@pytest.mark.asyncio
async def test_telegram_final_segment_splits_long_markdown_messages():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_message = AsyncMock()
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)

    delta = "A" * (TelegramPlatformEvent.MAX_MESSAGE_LENGTH + 32)
    payload = {"chat_id": "123456"}

    await event._send_final_segment(delta, payload)

    assert client.send_message.await_count == 2
    first_call = client.send_message.await_args_list[0].kwargs
    second_call = client.send_message.await_args_list[1].kwargs
    assert len(first_call["text"]) == TelegramPlatformEvent.MAX_MESSAGE_LENGTH
    assert len(second_call["text"]) == 32
    assert first_call["parse_mode"] == "MarkdownV2"
    assert second_call["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_telegram_send_returns_message_ids_and_keeps_base_send_bookkeeping():
    TelegramPlatformEvent = _load_telegram_platform_event()
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.session_id = "99"
    message.sender = MessageMember("42", "tester")
    message.message = []
    message.message_str = "hello"
    client = MockTelegramBuilder.create_bot()
    client.send_message.return_value = SimpleNamespace(message_id=101)
    event = TelegramPlatformEvent(
        "hello",
        message,
        PlatformMetadata(name="telegram", description="test", id="telegram-test"),
        "99",
        client,
    )

    result = await event.send(MessageChain([Comp.Plain("hello")]))

    assert result.message_ids == ("101",)
    assert result.platform_id == "telegram-test"
    assert event._has_send_oper is True


@pytest.mark.asyncio
async def test_telegram_final_segment_splits_long_plaintext_when_markdown_fails():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_message = AsyncMock()
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)

    delta = "B" * (TelegramPlatformEvent.MAX_MESSAGE_LENGTH + 18)
    payload = {"chat_id": "123456"}

    with patch(
        "astrbot.core.platform.sources.telegram.tg_event.telegramify_markdown.markdownify",
        side_effect=Exception("boom"),
    ):
        await event._send_final_segment(delta, payload)

    assert client.send_message.await_count == 2
    first_call = client.send_message.await_args_list[0].kwargs
    second_call = client.send_message.await_args_list[1].kwargs
    assert len(first_call["text"]) == TelegramPlatformEvent.MAX_MESSAGE_LENGTH
    assert len(second_call["text"]) == 18
    assert "parse_mode" not in first_call
    assert "parse_mode" not in second_call


@pytest.mark.asyncio
async def test_telegram_streaming_draft_break_flushes_real_message_and_resets_draft():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._send_message_draft = AsyncMock()
    event._send_final_segment = AsyncMock()
    event._process_chain_items = AsyncMock(
        side_effect=lambda chain, payload, user_name, message_thread_id, on_text: (
            on_text(chain.get_plain_text())
        )
    )
    allocated = iter([11, 12])

    with patch.object(
        TelegramPlatformEvent,
        "_allocate_draft_id",
        side_effect=lambda: next(allocated),
    ):

        async def generator():
            yield MessageChain([Comp.Plain("hello ")])
            yield MessageChain(type="break")
            yield MessageChain([Comp.Plain("world")])

        await event._send_streaming_draft("123", None, {"chat_id": "123"}, generator())

    assert event._send_message_draft.await_args_list == [
        call("123", 11, "\u23f3", None),
        call("123", 12, "\u23f3", None),
    ]
    assert event._send_final_segment.await_args_list == [
        call("hello ", {"chat_id": "123"}),
        call("world", {"chat_id": "123"}),
    ]


@pytest.mark.asyncio
async def test_telegram_send_message_draft_returns_explicit_success():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)

    outcome = await event._send_message_draft("123", 11, "hello")

    assert outcome == "sent"
    client.send_message_draft.assert_awaited_once_with(
        chat_id=123,
        draft_id=11,
        text="hello",
    )


@pytest.mark.asyncio
async def test_telegram_streaming_draft_bad_request_falls_back_to_plain_text():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message_draft.side_effect = [BadRequest("can't parse entities"), None]
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._send_final_segment = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("hello")])
        await asyncio.sleep(0)

    with patch(
        "astrbot.core.platform.sources.telegram.tg_event.BadRequest", BadRequest
    ):
        await event._send_streaming_draft("123", None, {"chat_id": "123"}, generator())

    assert client.send_message_draft.await_count == 3
    first_draft_id = client.send_message_draft.await_args_list[0].kwargs["draft_id"]
    assert client.send_message_draft.await_args_list[:2] == [
        call(
            chat_id=123,
            draft_id=first_draft_id,
            text="hello",
            parse_mode="MarkdownV2",
        ),
        call(chat_id=123, draft_id=first_draft_id, text="hello"),
    ]
    event._send_final_segment.assert_awaited_once_with("hello", {"chat_id": "123"})


@pytest.mark.asyncio
async def test_telegram_streaming_draft_non_content_bad_request_does_not_retry_plain_text():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message_draft.side_effect = BadRequest("Message thread not found")
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._send_final_segment = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("hello")])
        await asyncio.sleep(0)

    await event._send_streaming_draft("123", None, {"chat_id": "123"}, generator())

    draft_text_calls = [
        item
        for item in client.send_message_draft.await_args_list
        if item.kwargs.get("text") == "hello"
    ]
    assert len(draft_text_calls) == 1
    assert draft_text_calls[0].kwargs["parse_mode"] == "MarkdownV2"
    assert all("parse_mode" in item.kwargs for item in draft_text_calls)
    event._send_final_segment.assert_awaited_once_with("hello", {"chat_id": "123"})


@pytest.mark.asyncio
async def test_telegram_streaming_draft_retry_after_does_not_retry_or_block_final_send():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message_draft.side_effect = RetryAfter(1)
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._send_final_segment = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("hello")])
        await asyncio.sleep(0)

    with patch(
        "astrbot.core.platform.sources.telegram.tg_event.BadRequest", BadRequest
    ):
        await event._send_streaming_draft("123", None, {"chat_id": "123"}, generator())

    draft_text_calls = [
        item
        for item in client.send_message_draft.await_args_list
        if item.kwargs.get("text") == "hello"
    ]
    assert len(draft_text_calls) == 1
    assert draft_text_calls[0].kwargs["parse_mode"] == "MarkdownV2"
    event._send_final_segment.assert_awaited_once_with("hello", {"chat_id": "123"})


@pytest.mark.asyncio
async def test_telegram_send_message_draft_reports_invalid_thread_id_without_request():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)

    outcome = await event._send_message_draft("123", 11, "hello", "invalid")

    assert outcome == "failed"
    client.send_message_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_streaming_draft_final_send_survives_thread_id_failure():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._send_final_segment = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("hello")])
        await asyncio.sleep(0)

    await event._send_streaming_draft("123", "invalid", {"chat_id": "123"}, generator())

    client.send_message_draft.assert_not_awaited()
    event._send_final_segment.assert_awaited_once_with("hello", {"chat_id": "123"})


@pytest.mark.asyncio
async def test_telegram_streaming_edit_break_resets_message_id_and_sends_new_message():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.side_effect = [
        SimpleNamespace(message_id=100),
        SimpleNamespace(message_id=101),
    ]
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()
    event._process_chain_items = AsyncMock(
        side_effect=lambda chain, payload, user_name, message_thread_id, on_text: (
            on_text(chain.get_plain_text())
        )
    )

    async def generator():
        yield MessageChain([Comp.Plain("first")])
        yield MessageChain(type="break")
        yield MessageChain([Comp.Plain("second")])

    await event._send_streaming_edit("123", None, {"chat_id": "123"}, generator())

    client.send_message.assert_awaited()
    assert client.send_message.await_args_list[0].kwargs == {
        "text": "first",
        "chat_id": "123",
    }
    assert client.send_message.await_args_list[1].kwargs == {
        "text": "second",
        "chat_id": "123",
    }
    assert client.edit_message_text.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        ("A" * 4000, "B" * 200),
        ("A" * 4200,),
    ],
)
async def test_telegram_streaming_edit_splits_oversized_group_response(chunks):
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    visible: dict[int, str] = {}

    async def send_message(*, text, **_kwargs):
        if len(text) > TelegramPlatformEvent.MAX_MESSAGE_LENGTH:
            raise ValueError("message too long")
        message_id = len(visible) + 1
        visible[message_id] = text
        return SimpleNamespace(message_id=message_id)

    async def edit_message_text(*, text, message_id, **_kwargs):
        if len(text) > TelegramPlatformEvent.MAX_MESSAGE_LENGTH:
            raise ValueError("message too long")
        visible[message_id] = text

    client.send_message.side_effect = send_message
    client.edit_message_text.side_effect = edit_message_text
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()

    async def generator():
        for chunk in chunks:
            yield MessageChain([Comp.Plain(chunk)])

    result = await event._send_streaming_edit(
        "123", None, {"chat_id": "123"}, generator()
    )

    assert "".join(visible.values()) == "".join(chunks)
    assert all(
        len(text) <= TelegramPlatformEvent.MAX_MESSAGE_LENGTH
        for text in visible.values()
    )
    assert result.status == "accepted"
    assert result.message_count == 2


@pytest.mark.asyncio
async def test_telegram_streaming_edit_reports_failed_suffix_without_new_segment():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.side_effect = [SimpleNamespace(message_id=100)]
    client.edit_message_text.side_effect = RuntimeError("transport rejected")
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("A" * 4000)])
        yield MessageChain([Comp.Plain("B" * 200)])
        yield MessageChain([Comp.Plain("C" * 10)])

    result = await event._send_streaming_edit(
        "123", None, {"chat_id": "123"}, generator()
    )

    assert result.status == "partial"
    assert result.message_count == 1
    assert result.delivery_attempts[0].semantic_text == "A" * 4000
    assert result.delivery_attempts[1].semantic_text == "B" * 96
    assert result.delivery_attempts[2].status == "skipped"
    assert result.delivery_attempts[2].semantic_text == "B" * 104
    assert "".join(a.semantic_text for a in result.delivery_attempts) == (
        "A" * 4000 + "B" * 200
    )
    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_streaming_edit_reports_initial_send_failure():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.side_effect = RuntimeError("transport rejected")
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("undelivered")])

    result = await event._send_streaming_edit(
        "123", None, {"chat_id": "123"}, generator()
    )

    assert result.status == "failed"
    assert result.delivery_attempts[0].semantic_text == "undelivered"


@pytest.mark.asyncio
async def test_telegram_streaming_edit_retains_prefix_on_intermediate_failure():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.return_value = SimpleNamespace(message_id=100)
    client.edit_message_text.side_effect = TimedOut()
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()
    event._record_streaming_send = AsyncMock()
    clock = SimpleNamespace(time=lambda: next(ticks))
    ticks = iter([10, 10, 10, 11, 11])

    async def generator():
        yield MessageChain([Comp.Plain("hello")])
        yield MessageChain([Comp.Plain(" world")])

    with patch(
        "astrbot.core.platform.sources.telegram.tg_event.asyncio.get_running_loop",
        return_value=clock,
    ):
        result = await event._send_streaming_edit(
            "123", None, {"chat_id": "123"}, generator()
        )

    assert result.status == "partial"
    assert result.message_count == 1
    assert result.message_ids == ("100",)
    assert [(a.status, a.semantic_text) for a in result.delivery_attempts] == [
        ("accepted", "hello"),
        ("failed", " world"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [TimedOut(), NetworkError("offline"), RetryAfter(1), ValueError("conversion")],
)
async def test_telegram_streaming_edit_continues_after_markdown_failure(error):
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.side_effect = [
        SimpleNamespace(message_id=100),
        SimpleNamespace(message_id=101),
    ]
    client.edit_message_text.side_effect = error
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()
    module = "astrbot.core.platform.sources.telegram.tg_event"

    async def generator():
        yield MessageChain([Comp.Plain("!" * 4096 + "tail")])

    with (
        patch(module + ".BadRequest", BadRequest),
        patch(module + ".telegramify_markdown.markdownify", return_value="formatted"),
    ):
        result = await event._send_streaming_edit(
            "123", None, {"chat_id": "123"}, generator()
        )

    assert result.status == "accepted"
    assert result.message_count == 2
    assert "".join(a.semantic_text for a in result.delivery_attempts) == (
        "!" * 4096 + "tail"
    )
    assert client.edit_message_text.await_count == 2


@pytest.mark.asyncio
async def test_telegram_streaming_edit_propagates_markdown_cancellation():
    event_type = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.return_value = SimpleNamespace(message_id=100)
    client.edit_message_text.side_effect = asyncio.CancelledError()
    event = event_type("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()

    async def generator():
        yield MessageChain([Comp.Plain("hello!")])

    with (
        patch(
            "astrbot.core.platform.sources.telegram.tg_event.telegramify_markdown.markdownify",
            return_value="formatted",
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await event._send_streaming_edit("123", None, {"chat_id": "123"}, generator())


@pytest.mark.asyncio
async def test_telegram_polling_error_requests_rebuild_after_threshold():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._loop = asyncio.get_running_loop()

    assert not adapter._polling_recovery_requested.is_set()

    for _ in range(adapter._polling_recovery_threshold):
        adapter._on_polling_error(MockTelegramNetworkError("proxy disconnected"))

    await asyncio.sleep(0)

    assert adapter._polling_recovery_requested.is_set()


@pytest.mark.asyncio
async def test_telegram_run_rebuilds_application_after_repeated_polling_errors():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    app_one = MockTelegramBuilder.create_application()
    app_one.updater.running = True
    app_two = MockTelegramBuilder.create_application()
    app_two.updater.running = True
    created_apps = [app_one, app_two]

    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.side_effect = created_apps

    adapter = None

    def start_polling_side_effect(*args, **kwargs):
        nonlocal adapter
        error_callback = kwargs["error_callback"]
        assert adapter is not None

        async def _emit_errors():
            await asyncio.sleep(0)
            for _ in range(adapter._polling_recovery_threshold):
                error_callback(MockTelegramNetworkError("proxy disconnected"))

        asyncio.create_task(_emit_errors())
        return NoopAwaitable()

    app_one.updater.start_polling.side_effect = start_polling_side_effect

    async def second_start_polling(*args, **kwargs):
        assert adapter is not None
        adapter._terminating = True

    app_two.updater.start_polling.side_effect = second_start_polling

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
        },
    ):
        adapter = TelegramPlatformAdapter(
            make_platform_config("telegram"),
            {},
            asyncio.Queue(),
        )
        _bind_runtime_registries(adapter)
        await adapter.run()

    assert builder.build.call_count == 2
    app_one.updater.stop.assert_awaited()
    app_one.bot.delete_my_commands.assert_awaited_once()
    app_one.stop.assert_awaited()
    app_one.shutdown.assert_awaited()
    app_two.initialize.assert_awaited()
    app_two.start.assert_awaited()


@pytest.mark.asyncio
async def test_telegram_recreate_application_is_skipped_during_termination():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._terminating = True
    adapter._polling_recovery_requested.set()

    await adapter._recreate_application()

    assert not adapter._polling_recovery_requested.is_set()


@pytest.mark.asyncio
async def test_telegram_run_rebuilds_fresh_application_after_recreate_init_failure():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    app_one = MockTelegramBuilder.create_application()
    app_one.updater.running = True
    app_two = MockTelegramBuilder.create_application()
    app_three = MockTelegramBuilder.create_application()
    app_three.updater.running = True
    created_apps = [app_one, app_two, app_three]

    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.side_effect = created_apps

    adapter = None

    def first_start_polling(*args, **kwargs):
        nonlocal adapter
        error_callback = kwargs["error_callback"]
        assert adapter is not None

        async def _emit_errors():
            await asyncio.sleep(0)
            for _ in range(adapter._polling_recovery_threshold):
                error_callback(MockTelegramNetworkError("proxy disconnected"))

        asyncio.create_task(_emit_errors())
        return NoopAwaitable()

    app_one.updater.start_polling.side_effect = first_start_polling
    app_two.initialize.side_effect = TimeoutError("init timeout")

    async def final_start_polling(*args, **kwargs):
        assert adapter is not None
        adapter._terminating = True

    app_three.updater.start_polling.side_effect = final_start_polling

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
        },
    ):
        adapter = TelegramPlatformAdapter(
            make_platform_config(
                "telegram",
                telegram_polling_restart_delay=0.1,
            ),
            {},
            asyncio.Queue(),
        )
        _bind_runtime_registries(adapter)
        await adapter.run()

    assert builder.build.call_count == 3
    app_two.stop.assert_awaited()
    app_two.shutdown.assert_awaited()
    app_three.initialize.assert_awaited()
    app_three.start.assert_awaited()


def _telegram_bare_adapter():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter.__new__(TelegramPlatformAdapter)
    adapter.config = {"id": "telegram-test"}
    adapter.client = SimpleNamespace()
    return adapter


def _telegram_message(*, chat_type: str, status: str | None = None):
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType

    message = AstrBotMessage()
    message.type = (
        MessageType.FRIEND_MESSAGE
        if chat_type == "private"
        else MessageType.GROUP_MESSAGE
    )
    message.group_id = None if chat_type == "private" else "-1001"
    message.session_id = "1001" if chat_type == "private" else "-1001"
    message.sender = MessageMember("42", "tester")
    message.message_str = "hello"
    message.message = []
    update = SimpleNamespace(
        message=SimpleNamespace(chat=SimpleNamespace(type=chat_type)),
        chat_member=None,
        my_chat_member=None,
    )
    if status is not None:
        update.chat_member = SimpleNamespace(
            new_chat_member=SimpleNamespace(status=status)
        )
    message.raw_message = update
    return message


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("creator", "owner"),
        ("administrator", "admin"),
        ("member", "member"),
        ("restricted", "member"),
        ("kicked", "unknown"),
        (None, "unknown"),
    ],
)
def test_telegram_group_status_maps_or_stays_unknown(status, expected):
    event = _telegram_bare_adapter().create_event(
        _telegram_message(chat_type="group", status=status)
    )
    assert event.platform_member_role == expected
    assert event.platform_role_source == "adapter"


def test_telegram_private_chat_does_not_promote_creator_status():
    event = _telegram_bare_adapter().create_event(
        _telegram_message(chat_type="private", status="creator")
    )
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_telegram_group_admin_role_stays_in_current_session(tmp_path):
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.db.sqlite import SQLiteDatabase
    from tests.fixtures.auth import assert_platform_role_stays_in_session

    event = _telegram_bare_adapter().create_event(
        _telegram_message(chat_type="group", status="administrator")
    )
    db = SQLiteDatabase(str(tmp_path / "telegram-auth.db"))
    await db.initialize()
    service = AuthorizationService(db)
    await service.start()
    try:
        await assert_platform_role_stays_in_session(
            service,
            platform_instance="telegram",
            sender_id="42",
            platform_role=event.platform_member_role,
            current_umo="telegram:GroupMessage:-1001",
            other_umo="telegram:GroupMessage:-2002",
        )
    finally:
        await service.close()
        await db.close()


@pytest.mark.asyncio
async def test_telegram_topic_with_missing_name_falls_back_to_group_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    update.message.chat.title = "Engineering"

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "-100123#42"
    assert result.group.group_name == "Engineering"


@pytest.mark.asyncio
async def test_telegram_regular_supergroup_message_uses_group_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(chat_type="supergroup", chat_id=-100123)
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = False

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "-100123"
    assert result.group.group_name == "Engineering"


@pytest.mark.asyncio
async def test_telegram_forum_topic_name_is_learned_and_updated_from_events():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    created_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    created_update.message.chat.title = "Engineering"
    created_update.message.chat.is_forum = True
    created_update.message.forum_topic_created = SimpleNamespace(name="Backend")

    created = await adapter.convert_message(created_update, _build_context())

    assert created is not None
    assert created.group is not None
    assert created.group.group_name == "Engineering-Backend"

    regular_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    regular_update.message.chat.title = "Engineering"
    regular_update.message.chat.is_forum = True

    regular = await adapter.convert_message(regular_update, _build_context())

    assert regular is not None
    assert regular.group is not None
    assert regular.group.group_name == "Engineering-Backend"

    empty_edit_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    empty_edit_update.message.chat.title = "Engineering"
    empty_edit_update.message.chat.is_forum = True
    empty_edit_update.message.forum_topic_edited = SimpleNamespace(name="   ")

    empty_edit = await adapter.convert_message(empty_edit_update, _build_context())

    assert empty_edit is not None
    assert empty_edit.group is not None
    assert empty_edit.group.group_name == "Engineering-Backend"

    edited_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    edited_update.message.chat.title = "Engineering"
    edited_update.message.chat.is_forum = True
    edited_update.message.forum_topic_edited = SimpleNamespace(name="Platform")

    edited = await adapter.convert_message(edited_update, _build_context())

    assert edited is not None
    assert edited.group is not None
    assert edited.group.group_name == "Engineering-Platform"


@pytest.mark.asyncio
async def test_telegram_forum_topic_cache_evicts_oldest_entry():
    TelegramPlatformAdapter = _load_telegram_adapter()
    assert TelegramPlatformAdapter._FORUM_TOPIC_NAME_CACHE_MAX_SIZE == 1000
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._FORUM_TOPIC_NAME_CACHE_MAX_SIZE = 2

    for thread_id, topic_name in [(41, "One"), (42, "Two"), (43, "Three")]:
        update = create_mock_update(
            chat_type="supergroup",
            chat_id=-100123,
            message_thread_id=thread_id,
            is_topic_message=True,
        )
        update.message.chat.title = "Engineering"
        update.message.chat.is_forum = True
        update.message.forum_topic_created = SimpleNamespace(name=topic_name)
        await adapter.convert_message(update, _build_context())

    assert list(adapter._forum_topic_names) == [("-100123", 42), ("-100123", 43)]


@pytest.mark.asyncio
async def test_telegram_forum_topic_name_is_read_from_topic_root_reply():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    topic_root = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_id=42,
    ).message
    topic_root.forum_topic_created = SimpleNamespace(name="Backend")
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
        reply_to_message=topic_root,
    )
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = True

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_name == "Engineering-Backend"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_thread_id", "is_topic_message"),
    [(None, False), (1, True)],
)
async def test_telegram_general_forum_topic_without_known_name_uses_group_name(
    message_thread_id, is_topic_message
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=message_thread_id,
        is_topic_message=is_topic_message,
    )
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = True

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "-100123"
    assert result.group.group_name == "Engineering"


@pytest.mark.asyncio
async def test_telegram_general_forum_topic_uses_observed_custom_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    edited_update = create_mock_update(chat_type="supergroup", chat_id=-100123)
    edited_update.message.chat.title = "Engineering"
    edited_update.message.chat.is_forum = True
    edited_update.message.forum_topic_edited = SimpleNamespace(name="Lobby")

    edited = await adapter.convert_message(edited_update, _build_context())

    assert edited is not None
    assert edited.group is not None
    assert edited.group.group_name == "Engineering-Lobby"

    regular_update = create_mock_update(chat_type="supergroup", chat_id=-100123)
    regular_update.message.chat.title = "Engineering"
    regular_update.message.chat.is_forum = True

    regular = await adapter.convert_message(regular_update, _build_context())

    assert regular is not None
    assert regular.group is not None
    assert regular.group.group_name == "Engineering-Lobby"


@pytest.mark.asyncio
async def test_telegram_get_group_keeps_forum_topic_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    TelegramPlatformEvent = _load_telegram_platform_event()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = True
    update.message.forum_topic_created = SimpleNamespace(name="Backend")
    message = await adapter.convert_message(update, _build_context())
    assert message is not None

    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = message
    event._client = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Engineering 2", photo=None)
        ),
        get_chat_member_count=AsyncMock(return_value=24),
        get_chat_administrators=AsyncMock(return_value=[]),
    )

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "Engineering 2-Backend"


@pytest.mark.asyncio
async def test_telegram_get_group_enriches_available_metadata():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                title="Engineering",
                photo=SimpleNamespace(big_file_id="photo-1"),
            )
        ),
        get_file=AsyncMock(
            return_value=SimpleNamespace(
                file_path="https://api.telegram.org/file/group.jpg"
            )
        ),
        get_chat_member_count=AsyncMock(return_value=24),
        get_chat_administrators=AsyncMock(
            return_value=[
                SimpleNamespace(status="creator", user=SimpleNamespace(id=1)),
                SimpleNamespace(status="administrator", user=SimpleNamespace(id=2)),
            ]
        ),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123#42", group_name="Cached title"),
        group_id="-100123#42",
    )
    event._client = client

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "-100123#42"
    assert group.group_name == "Engineering"
    assert group.group_avatar == "https://api.telegram.org/file/group.jpg"
    assert group is not event.message_obj.group
    assert group.member_count == 24
    assert group.group_owner == "1"
    assert group.group_admins == ["2"]
    assert group.members is None
    client.get_chat.assert_awaited_once_with(chat_id=-100123)
    client.get_chat_member_count.assert_awaited_once_with(chat_id=-100123)
    client.get_chat_administrators.assert_awaited_once_with(chat_id=-100123)


@pytest.mark.asyncio
async def test_telegram_get_group_keeps_basic_metadata_when_apis_fail():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(side_effect=RuntimeError("chat unavailable")),
        get_chat_member_count=AsyncMock(side_effect=RuntimeError("count unavailable")),
        get_chat_administrators=AsyncMock(
            side_effect=RuntimeError("administrators unavailable")
        ),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123#42", group_name="Cached title"),
        group_id="-100123#42",
    )
    event._client = client

    group = await event.get_group()

    assert group is not event.message_obj.group
    assert group == Group(group_id="-100123#42", group_name="Cached title")


@pytest.mark.asyncio
async def test_telegram_get_group_joins_relative_avatar_with_file_base_url():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        base_file_url="https://api.telegram.org/file/botTESTTOKEN",
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                title="Engineering",
                photo=SimpleNamespace(big_file_id="photo-1"),
            )
        ),
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photos/group.jpg")),
        get_chat_member_count=AsyncMock(return_value=3),
        get_chat_administrators=AsyncMock(return_value=[]),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123", group_name="Cached title"),
        group_id="-100123",
    )
    event._client = client

    group = await event.get_group()

    assert (
        group.group_avatar
        == "https://api.telegram.org/file/botTESTTOKEN/photos/group.jpg"
    )


@pytest.mark.asyncio
async def test_telegram_get_group_leaves_avatar_none_when_file_path_unusable():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                title="Engineering",
                photo=SimpleNamespace(big_file_id="photo-1"),
            )
        ),
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photos/group.jpg")),
        get_chat_member_count=AsyncMock(return_value=3),
        get_chat_administrators=AsyncMock(return_value=[]),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123", group_name="Cached title"),
        group_id="-100123",
    )
    event._client = client

    group = await event.get_group()

    assert group.group_avatar is None


@pytest.mark.asyncio
async def test_telegram_get_group_does_not_use_topic_name_for_other_group():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Other", photo=None)),
        get_chat_member_count=AsyncMock(return_value=2),
        get_chat_administrators=AsyncMock(return_value=[]),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123#42", group_name="Engineering-Backend"),
        group_id="-100123#42",
        _telegram_topic_name="Backend",
    )
    event._client = client

    group = await event.get_group(group_id="-100999")

    assert group.group_id == "-100999"
    assert group.group_name == "Other"


@pytest.mark.asyncio
@pytest.mark.parametrize("media", [None, "audio", "photo", "document", "video"])
@pytest.mark.parametrize(
    ("text", "ranges", "expected", "names"),
    [
        ("😀 @test_bot hello", [(2, 9)], "😀  hello", ["test_bot"]),
        (
            "@test_bot hello @test_bot!",
            [(0, 9), (16, 9)],
            " hello !",
            ["test_bot", "test_bot"],
        ),
        (
            "😀@other@test_bot🚀@TEST_BOT",
            [(1, 6), (7, 9), (17, 9)],
            "😀@other🚀",
            ["other", "test_bot", "TEST_BOT"],
        ),
        ("@test_bot@test_bot", [(0, 9), (9, 9)], "", ["test_bot", "test_bot"]),
        (
            "@test_bot x @other",
            [(12, 6), (0, 9), (0, 9)],
            " x @other",
            ["other", "test_bot", "test_bot"],
        ),
        ("😀 untouched\n text 🚀", [], "😀 untouched\n text 🚀", []),
    ],
)
async def test_telegram_real_entities_preserve_text(
    media, text, ranges, expected, names
):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    entities = [
        MessageEntity.adjust_message_entities_to_utf_16(
            text, [MessageEntity("mention", offset, length)]
        )[0]
        for offset, length in ranges
    ]
    content = {"text": text, "entities": entities}
    if media:
        attachments = {
            "audio": Audio("file", "unique", 1),
            "photo": [PhotoSize("file", "unique", 1, 1)],
            "document": Document("file", "unique"),
            "video": Video("file", "unique", 1, 1, 1),
        }
        content = {
            "caption": text,
            "caption_entities": entities,
            media: attachments[media],
        }
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(-10001, "group"),
        from_user=User(42, "Alice", False),
        **content,
    )
    parser = message.parse_caption_entity if media else message.parse_entity
    assert [parser(entity)[1:] for entity in entities] == names

    context = _build_context()
    result = await adapter.convert_message(Update(1, message=message), context)

    assert result is not None
    assert result.message_str == expected
    assert [
        part.target for part in result.message if isinstance(part, Comp.Mention)
    ] == [
        str(context.bot.id) if name.lower() == context.bot.username.lower() else name
        for name in names
    ]
    assert (
        "".join(part.text for part in result.message if isinstance(part, Comp.Plain))
        == expected
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("caption", [False, True])
@pytest.mark.parametrize(
    ("offset", "length"),
    [
        (-1, 9),
        (99, 9),
        (3, 99),
        (3, 0),
        (3, -1),
        (1, 11),
        (0, 1),
        (4, 8),
        (0, 12),
        (13, 5),
    ],
)
async def test_telegram_malformed_entities_leave_original_text(caption, offset, length):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    text = "😀 @test_bot hello"
    entities = [MessageEntity("mention", offset, length), MessageEntity("bold", 3, 9)]
    content = {"text": text, "entities": entities}
    if caption:
        content = {
            "caption": text,
            "caption_entities": entities,
            "photo": [PhotoSize("file", "unique", 1, 1)],
        }
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(-10001, "group"),
        from_user=User(42, "Alice", False),
        **content,
    )

    result = await adapter.convert_message(Update(1, message=message), _build_context())

    assert result is not None
    assert result.message_str == text
    assert not any(isinstance(part, Comp.Mention) for part in result.message)


def _real_contract_update(
    field: str = "message",
    *,
    update_id: int = 1,
    connection_id: str = "connection:a",
    **message_fields,
) -> Update:
    user = {"id": 99, "first_name": "Customer", "is_bot": False}
    chat = {"id": 99, "type": "private"}
    message = {
        "message_id": update_id,
        "date": 1_700_000_000,
        "chat": chat,
        "from": user,
        "text": "hello",
        "message_thread_id": 42,
        "is_topic_message": True,
    }
    if field in {"channel_post", "edited_channel_post"}:
        message["chat"] = {"id": -10099, "type": "channel", "title": "News"}
        message["sender_chat"] = message["chat"]
        message.pop("from")
    if field in {"business_message", "edited_business_message"}:
        message["business_connection_id"] = connection_id
    message.update(message_fields)
    if field == "callback_query":
        return Update.de_json(
            {
                "update_id": update_id,
                "callback_query": {
                    "id": "callback-1",
                    "from": user,
                    "chat_instance": "instance",
                    "data": "ab1_token",
                    "message": message,
                },
            },
            bot=None,
        )
    return Update.de_json({"update_id": update_id, field: message}, bot=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "target", "sender", "message_type"),
    [
        ("message", "99#42", "99", MessageType.FRIEND_MESSAGE),
        ("channel_post", "-10099#42", "-10099", MessageType.GROUP_MESSAGE),
        (
            "business_message",
            "business:connection%3Aa:99#42",
            "99",
            MessageType.FRIEND_MESSAGE,
        ),
    ],
)
async def test_telegram_update_supported_variants(field, target, sender, message_type):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    update = _real_contract_update(field)

    message = await adapter.convert_message(update, _build_context())

    assert message is not None
    assert message.type == message_type
    assert message.session_id == target
    assert message.sender.user_id == sender
    assert message.message_str == "hello"
    assert message.raw_message is update
    assert adapter.create_event(message).route_identity.target_id == target


def _ignored_telegram_updates() -> dict[str, Update]:
    user = {"id": 99, "first_name": "Alice", "is_bot": False}
    chat = {"id": 99, "type": "private"}
    member = {"status": "member", "user": user}
    member_change = {
        "chat": chat,
        "from": user,
        "date": 1,
        "old_chat_member": member,
        "new_chat_member": member,
    }
    boost_source = {"source": "premium", "user": user}
    payloads = {
        "inline_query": {"id": "q", "from": user, "query": "q", "offset": ""},
        "chosen_inline_result": {"result_id": "r", "from": user, "query": "q"},
        "callback_query": {
            "id": "q",
            "from": user,
            "chat_instance": "c",
            "message": _real_contract_update().message.to_dict(),
        },
        "shipping_query": {
            "id": "q",
            "from": user,
            "invoice_payload": "p",
            "shipping_address": dict.fromkeys(
                [
                    "country_code",
                    "state",
                    "city",
                    "street_line1",
                    "street_line2",
                    "post_code",
                ],
                "x",
            ),
        },
        "pre_checkout_query": {
            "id": "q",
            "from": user,
            "currency": "USD",
            "total_amount": 1,
            "invoice_payload": "p",
        },
        "poll": {
            "id": "p",
            "question": "q",
            "options": [],
            "total_voter_count": 0,
            "is_closed": False,
            "is_anonymous": True,
            "type": "regular",
            "allows_multiple_answers": False,
            "allows_revoting": False,
            "members_only": False,
        },
        "poll_answer": {
            "poll_id": "p",
            "option_ids": [],
            "option_persistent_ids": [],
            "user": user,
        },
        "my_chat_member": member_change,
        "chat_member": member_change,
        "chat_join_request": {
            "chat": chat,
            "from": user,
            "user_chat_id": 99,
            "date": 1,
        },
        "chat_boost": {
            "chat": chat,
            "boost": {
                "boost_id": "b",
                "add_date": 1,
                "expiration_date": 2,
                "source": boost_source,
            },
        },
        "removed_chat_boost": {
            "chat": chat,
            "boost_id": "b",
            "remove_date": 1,
            "source": boost_source,
        },
        "message_reaction": {
            "chat": chat,
            "message_id": 1,
            "date": 1,
            "old_reaction": [],
            "new_reaction": [],
            "user": user,
        },
        "message_reaction_count": {
            "chat": chat,
            "message_id": 1,
            "date": 1,
            "reactions": [],
        },
        "business_connection": {
            "id": "b",
            "user": user,
            "user_chat_id": 99,
            "date": 1,
            "is_enabled": True,
        },
        "deleted_business_messages": {
            "business_connection_id": "b",
            "chat": chat,
            "message_ids": [1],
        },
        "purchased_paid_media": {"from": user, "paid_media_payload": "p"},
        "managed_bot": {"user": user, "bot": {**user, "is_bot": True}},
    }
    updates = {
        field: Update.de_json({"update_id": 1, field: payload}, bot=None)
        for field, payload in payloads.items()
    }
    for field in (
        "edited_message",
        "edited_channel_post",
        "edited_business_message",
        "guest_message",
    ):
        updates[field] = _real_contract_update(
            field, guest_query_id="guest-query" if field == "guest_message" else None
        )
    return updates


@pytest.mark.asyncio
@pytest.mark.parametrize("field", sorted(_ignored_telegram_updates()))
async def test_telegram_update_ignored_variants(field):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.handle_msg = AsyncMock()
    update = _ignored_telegram_updates()[field]

    assert await adapter.convert_message(update, _build_context()) is None
    await adapter.message_handler(update, _build_context())

    adapter.handle_msg.assert_not_awaited()
    assert not adapter._media_group_tasks


def test_telegram_update_handler_and_matrix_cover_ptb_types():
    from telegram.ext import MessageHandler, filters

    adapter_type = _load_telegram_adapter()
    with patch.dict(
        adapter_type.__init__.__globals__,
        {"filters": filters, "TelegramMessageHandler": MessageHandler},
    ):
        adapter = adapter_type(make_platform_config("telegram"), {}, asyncio.Queue())
    handler = adapter.application.add_handler.call_args.args[0]
    supported = adapter_type.run.__globals__["TELEGRAM_ALLOWED_UPDATES"]
    ignored = _ignored_telegram_updates()
    assert set(supported) | set(ignored) == set(Update.ALL_TYPES)
    message_supported = adapter_type.__init__.__globals__["TELEGRAM_MESSAGE_UPDATES"]
    for field in message_supported:
        assert handler.check_update(_real_contract_update(field))
    callback_handler = adapter.application.add_handler.call_args_list[0].args[0]
    assert callback_handler.check_update(_real_contract_update("callback_query"))
    for update in ignored.values():
        assert not handler.check_update(update)


@pytest.mark.asyncio
async def test_telegram_polling_allowed_updates_are_explicit():
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram", telegram_command_register=False),
        {},
        asyncio.Queue(),
    )
    adapter.application = MockTelegramBuilder.create_application()
    adapter.client = adapter.application.bot

    async def stop_after_start(**kwargs):
        adapter._terminating = True

    adapter.application.updater.start_polling = AsyncMock(side_effect=stop_after_start)
    await asyncio.wait_for(adapter.run(), timeout=1)

    adapter.application.updater.start_polling.assert_awaited_once_with(
        allowed_updates=(
            "message",
            "channel_post",
            "business_message",
            "callback_query",
        ),
        error_callback=adapter._on_polling_error,
    )


@pytest.mark.asyncio
async def test_telegram_update_duplicate_and_edit_replays_do_not_dispatch_twice():
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.handle_msg = AsyncMock()
    update = _real_contract_update()
    await adapter.message_handler(update, _build_context())
    await adapter.message_handler(update, _build_context())
    await adapter.message_handler(
        _real_contract_update("edited_message", update_id=2), _build_context()
    )
    assert adapter.handle_msg.await_count == 1
    adapter._UPDATE_REPLAY_CACHE_SIZE = 2
    for update_id in (3, 4):
        await adapter.message_handler(
            _real_contract_update(update_id=update_id), _build_context()
        )
    assert list(adapter._seen_update_ids) == [3, 4]


def _interaction_adapter():
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.client = MockTelegramBuilder.create_bot()
    adapter.client.id = 12345678
    adapter.client.send_message.return_value = SimpleNamespace(message_id=44)
    return adapter


def _callback_update(token: str, *, update_id: int = 10, user_id: int = 99):
    message = SimpleNamespace(
        message_id=44,
        chat=SimpleNamespace(id=99, type="private"),
        message_thread_id=None,
        is_topic_message=False,
        business_connection_id=None,
    )
    query = SimpleNamespace(
        id=f"query-{update_id}",
        data=token,
        message=message,
        from_user=SimpleNamespace(id=user_id, username="alice", full_name="Alice"),
    )
    return SimpleNamespace(update_id=update_id, callback_query=query)


@pytest.mark.asyncio
async def test_telegram_interactive_send_binds_tokens_and_callback_is_one_shot():
    adapter = _interaction_adapter()
    receipt = await adapter.invoke_capability(
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        target="99",
        text="Continue?",
        buttons=[[{"text": "Yes", "value": "confirm"}]],
        allowed_user_ids=[99],
    )

    assert receipt.success
    assert receipt.message_ids == ("44",)
    token = next(iter(adapter._callback_bindings))
    await adapter.callback_query_handler(_callback_update(token), _build_context())
    event = await adapter._event_queue.get()
    callback = event.get_extra("telegram_callback")
    assert isinstance(callback, TelegramCallbackEvent)
    assert callback.data == "confirm"
    assert callback.message_id == "44"
    assert not adapter._callback_bindings

    await adapter.callback_query_handler(
        _callback_update(token, update_id=11), _build_context()
    )
    assert adapter.client.answer_callback_query.await_count == 2
    assert adapter._event_queue.empty()


@pytest.mark.asyncio
async def test_telegram_callback_rejects_unauthorized_actor_and_expired_token():
    adapter = _interaction_adapter()
    await adapter.invoke_capability(
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        target="99",
        text="Continue?",
        buttons=[[{"text": "Yes", "value": "confirm"}]],
        allowed_user_ids=[99],
        ttl_seconds=1,
    )
    token = next(iter(adapter._callback_bindings))
    await adapter.callback_query_handler(
        _callback_update(token, user_id=100), _build_context()
    )
    assert adapter._event_queue.empty()
    assert not adapter._callback_bindings

    adapter = _interaction_adapter()
    await adapter.invoke_capability(
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        target="99",
        text="Continue?",
        buttons=[[{"text": "Yes", "value": "confirm"}]],
    )
    token = next(iter(adapter._callback_bindings))
    adapter._callback_bindings[token] = replace(
        adapter._callback_bindings[token], expires_at=0
    )
    await adapter.callback_query_handler(_callback_update(token), _build_context())
    assert adapter._event_queue.empty()
    assert not adapter._callback_bindings


@pytest.mark.asyncio
async def test_telegram_interactive_send_failure_removes_callback_bindings():
    adapter = _interaction_adapter()
    adapter.client.send_message.side_effect = RuntimeError("network")
    receipt = await adapter.invoke_capability(
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        target="99",
        text="Continue?",
        buttons=[[{"text": "Yes", "value": "confirm"}]],
    )
    assert not receipt.success
    assert not adapter._callback_bindings


@pytest.mark.asyncio
async def test_telegram_callback_pruning_handles_mixed_ttl_order():
    adapter = _interaction_adapter()
    await adapter.invoke_capability(
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        target="99",
        text="Long-lived",
        buttons=[[{"text": "One", "value": "one"}]],
        ttl_seconds=3600,
    )
    long_token = next(iter(adapter._callback_bindings))
    await adapter.invoke_capability(
        TELEGRAM_CAPABILITY_NAME,
        "send_interactive",
        target="99",
        text="Short-lived",
        buttons=[[{"text": "Two", "value": "two"}]],
        ttl_seconds=1,
    )
    short_token = next(
        token for token in adapter._callback_bindings if token != long_token
    )
    adapter._callback_bindings[short_token] = replace(
        adapter._callback_bindings[short_token], expires_at=0
    )

    adapter._prune_callback_bindings()

    assert list(adapter._callback_bindings) == [long_token]


@pytest.mark.asyncio
async def test_telegram_interactive_input_rejects_invalid_ids_and_large_button_sets():
    adapter = _interaction_adapter()
    with pytest.raises(OneBotActionValidationError):
        adapter._normalize_allowed_users([None])
    with pytest.raises(OneBotActionValidationError):
        adapter._normalize_allowed_roles(["owner"])
    with pytest.raises(OneBotActionValidationError):
        await adapter.invoke_capability(
            TELEGRAM_CAPABILITY_NAME,
            "send_interactive",
            target="99",
            text="Too many",
            buttons=[[{"text": "x", "value": str(index)} for index in range(2049)]],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"sender_business_bot": {"id": 12, "first_name": "Bot", "is_bot": True}},
        {"from": {"id": 100, "first_name": "Owner", "is_bot": False}},
        {"from": None},
        {"business_connection_id": None},
        {"chat": {"id": 99, "type": "group"}},
    ],
)
async def test_telegram_business_update_rejects_outgoing_or_unroutable_messages(fields):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.handle_msg = AsyncMock()
    update = _real_contract_update("business_message", **fields)
    await adapter.message_handler(update, _build_context())
    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_update_sender_chat_takes_precedence_over_fake_user():
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    update = _real_contract_update(
        "message",
        chat={"id": -10099, "type": "supergroup", "title": "Group"},
        sender_chat={"id": -10099, "type": "supergroup", "title": "Group"},
    )
    message = await adapter.convert_message(update, _build_context())
    assert message is not None
    assert message.sender.user_id == "-10099"
    assert message.sender.nickname == "Group"


@pytest.mark.asyncio
async def test_telegram_business_reply_proactive_typing_and_start_keep_namespace(
    tmp_path,
):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.client = MockTelegramBuilder.create_bot()
    update = _real_contract_update("business_message")
    message = await adapter.convert_message(update, _build_context())
    assert message is not None
    event = adapter.create_event(message)
    ordinary = await adapter.convert_message(_real_contract_update(), _build_context())
    assert ordinary is not None
    assert event.unified_msg_origin != adapter.create_event(ordinary).unified_msg_origin
    path = tmp_path / "report.txt"
    path.write_text("report")
    await event.send(
        MessageChain(
            [Comp.Plain("reply"), Comp.File(file=str(path), name="report.txt")]
        )
    )
    await adapter.send_by_session(
        MessageSession.from_str(event.unified_msg_origin),
        MessageChain([Comp.Plain("proactive")]),
    )
    await event.send_typing()
    for method in (
        adapter.client.send_message,
        adapter.client.send_document,
        adapter.client.send_chat_action,
    ):
        for api_call in method.await_args_list:
            assert api_call.kwargs["chat_id"] == "99"
            assert api_call.kwargs["message_thread_id"] == "42"
            assert api_call.kwargs["business_connection_id"] == "connection:a"
    context = _build_context()
    context.bot.send_message = AsyncMock()
    await adapter.start(update, context)
    assert (
        context.bot.send_message.await_args.kwargs["business_connection_id"]
        == "connection:a"
    )
    await event.react("👍")
    adapter.client.set_message_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_business_streaming_preserves_identity_on_media_and_edits(
    tmp_path,
):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.client = MockTelegramBuilder.create_bot()
    adapter.client.send_message.return_value = SimpleNamespace(message_id=100)
    message = await adapter.convert_message(
        _real_contract_update("business_message"), _build_context()
    )
    assert message is not None
    path = tmp_path / "report.txt"
    path.write_text("report")

    async def generator():
        yield MessageChain([Comp.Plain("first")])
        yield MessageChain(
            [Comp.Plain(" second"), Comp.File(file=str(path), name="report.txt")]
        )

    event = adapter.create_event(message)
    with patch.dict(
        event.send_streaming.__globals__,
        {"telegramify_markdown": SimpleNamespace(markdownify=lambda text: text + "!")},
    ):
        await event.send_streaming(generator())
    adapter.client.send_message_draft.assert_not_awaited()
    assert adapter.client.edit_message_text.await_count == 2
    for method in (
        adapter.client.send_message,
        adapter.client.send_document,
        adapter.client.send_chat_action,
        adapter.client.edit_message_text,
    ):
        for api_call in method.await_args_list:
            assert api_call.kwargs["chat_id"] == "99"
            assert api_call.kwargs["business_connection_id"] == "connection:a"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["message", "channel_post", "business_message"])
async def test_telegram_update_albums_use_supported_message_fields(field):
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    adapter.media_group_timeout = 0.01
    adapter.handle_msg = AsyncMock()
    context = _build_context()
    for update_id in (1, 1, 2):
        update = _real_contract_update(
            field,
            update_id=update_id,
            text=None,
            caption="caption" if update_id == 1 else None,
            media_group_id="album",
            photo=[
                {
                    "file_id": str(update_id),
                    "file_unique_id": str(update_id),
                    "width": 1,
                    "height": 1,
                }
            ],
        )
        await adapter.message_handler(update, context)
    await asyncio.gather(*adapter._media_group_tasks.values())
    adapter.handle_msg.assert_awaited_once()
    message = adapter.handle_msg.await_args.args[0]
    assert message.message_str == "caption"
    assert sum(isinstance(item, Comp.Image) for item in message.message) == 2


@pytest.mark.asyncio
async def test_telegram_business_albums_separate_connections():
    adapter = _load_telegram_adapter()(
        make_platform_config("telegram"), {}, asyncio.Queue()
    )
    for update_id, connection_id in enumerate(("one", "two"), 1):
        await adapter.message_handler(
            _real_contract_update(
                "business_message",
                update_id=update_id,
                connection_id=connection_id,
                media_group_id="same",
            ),
            _build_context(),
        )
    assert len(adapter._media_group_tasks) == 2
    await adapter._cleanup_media_groups()
