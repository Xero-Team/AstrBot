import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Face, Json, Mention, Plain, Reply
from astrbot.api.provider import Provider
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main


def _make_extras_store():
    """Return a mutable dict and get_extra / set_extra side_effects bound to it."""
    store: dict[str, object] = {}
    get_extra = lambda key, default=None: store.get(key, default)  # noqa: E731
    set_extra = store.__setitem__  # type: ignore[assignment]
    return store, get_extra, set_extra


def make_event(
    umo: str = "aiocqhttp:GroupMessage:user_123_group_456",
    *,
    handlers_parsed_params: dict | None = None,
):
    event = MagicMock()
    event.unified_msg_origin = umo
    event.get_platform_id.return_value = "aiocqhttp"
    event.message_obj = SimpleNamespace(message=[Plain("hello")])
    event.message_str = "hello"
    event.session_id = "session-1"

    store, get_extra, set_extra = _make_extras_store()
    # Simulate WakingCheckStage output: an empty dict means no command matched.
    store["handlers_parsed_params"] = (
        {} if handlers_parsed_params is None else handlers_parsed_params
    )
    event.get_extra.side_effect = get_extra
    event.set_extra.side_effect = set_extra
    return event


@pytest.mark.asyncio
async def test_group_context_image_caption_normalizes_missing_completion_text():
    """A successful provider response without text must not render ``None``."""
    provider = MagicMock(spec=Provider)
    provider.text_chat = AsyncMock(return_value=MagicMock(completion_text=None))
    context = SimpleNamespace(models=SimpleNamespace(using_chat=lambda: provider))

    caption = await GroupChatContext(context).get_image_caption(
        "https://example.com/image.png",
        "",
        "Describe the image.",
    )

    assert caption == ""


@pytest.mark.asyncio
async def test_group_context_renders_qq_face_semantics() -> None:
    context = GroupChatContext(SimpleNamespace())
    event = SimpleNamespace(
        message_obj=SimpleNamespace(sender=SimpleNamespace(nickname="tester")),
        get_messages=lambda: [Plain("hello"), Face(id=111)],
        get_self_id=lambda: "",
    )

    formatted = await context._format_message(event, {})

    assert "[QQ Face: 可怜 (id: 111)]" in formatted


@pytest.mark.asyncio
async def test_group_context_prefers_structured_quoted_face_context() -> None:
    context = GroupChatContext(SimpleNamespace())
    event = SimpleNamespace(
        message_obj=SimpleNamespace(sender=SimpleNamespace(nickname="tester")),
        get_messages=lambda: [
            Reply(
                id="quoted-face",
                message_str="[Face:111]",
                chain=[Face(id=111)],
            )
        ],
        get_self_id=lambda: "",
    )

    formatted = await context._format_message(event, {})

    assert "[QQ Face: 可怜 (id: 111)]" in formatted
    assert "[Face:111]" not in formatted


def _make_main(*, group_icl_enable: bool):
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.config.get.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": group_icl_enable,
        },
    }
    main.group_chat_context = SimpleNamespace(
        handle_message=AsyncMock(),
        remove_session=AsyncMock(),
    )
    return main


@pytest.mark.asyncio
async def test_on_message_does_not_clear_group_context_on_first_enabled_message():
    main = _make_main(group_icl_enable=True)
    event = make_event()

    await main.on_message(event)

    main.group_chat_context.handle_message.assert_awaited_once_with(event)
    main.group_chat_context.remove_session.assert_not_called()
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_skips_recording_when_command_handler_matched():
    """A slash-command message (handlers_parsed_params non-empty) must not be
    recorded into the group context buffer."""
    main = _make_main(group_icl_enable=True)
    event = make_event(
        handlers_parsed_params={
            "astrbot.builtin_stars.builtin_commands.main_conversation_reset": {}
        },
    )

    await main.on_message(event)

    main.group_chat_context.handle_message.assert_not_awaited()
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_records_json_card_without_requesting_llm():
    main = _make_main(group_icl_enable=True)
    event = make_event()
    event.message_obj.message = [Json(data={"meta": {"news": {"title": "News"}}})]

    await main.on_message(event)

    main.group_chat_context.handle_message.assert_awaited_once_with(event)
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_ignores_leftover_active_reply_config():
    main = _make_main(group_icl_enable=False)
    main.context.config.get.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": False,
            "active_reply": {
                "enable": True,
                "method": "possibility_reply",
                "possibility_reply": 1.0,
                "whitelist": [],
            },
        },
    }
    event = make_event()

    await main.on_message(event)

    main.group_chat_context.handle_message.assert_not_awaited()
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_records_history_without_llm_when_active_reply_leftover():
    main = _make_main(group_icl_enable=True)
    main.context.config.get.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {
                "enable": True,
                "method": "possibility_reply",
                "possibility_reply": 1.0,
                "whitelist": [],
            },
        },
    }
    event = make_event()

    await main.on_message(event)

    main.group_chat_context.handle_message.assert_awaited_once_with(event)
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("card_data", "expected"),
    [
        (
            {
                "meta": {
                    "detail_1": {
                        "title": "WeChat AI models",
                        "desc": "AI learning\nwith examples",
                        "qqdocurl": "https://example.com/detail",
                    }
                }
            },
            " [Shared Card: Title: WeChat AI models; Description: AI learning "
            "with examples; URL: https://example.com/detail]",
        ),
        (
            {
                "data": json.dumps(
                    {
                        "meta": {
                            "news": {
                                "title": "Wrapped card",
                                "jumpUrl": "https://example.com/news",
                            }
                        }
                    }
                )
            },
            " [Shared Card: Title: Wrapped card; URL: https://example.com/news]",
        ),
        ({"app": "com.example.unknown"}, " [Shared Card]"),
    ],
)
async def test_json_card_rendering(card_data, expected):
    context = GroupChatContext(MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [Json(data=card_data)]

    formatted = await context._format_message(event, {})

    assert formatted.endswith(expected)


@pytest.mark.asyncio
async def test_format_message_truncates_long_json_card_fields():
    context = GroupChatContext(MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [
        Json(data={"meta": {"news": {"desc": "a" * 201}}})
    ]

    formatted = await context._format_message(event, {})

    assert f"Description: {'a' * 200}..." in formatted


def _make_empty_mention_main():
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.config.get.return_value = {
        "platform_settings": {
            "empty_mention_waiting": True,
            "empty_mention_waiting_need_reply": True,
        },
        "command_prefixes": ["/"],
    }
    main.context.conversations.current_id = AsyncMock(return_value="cid-1")
    main.context.conversations.get = AsyncMock(return_value=None)
    main.context.messages.wait_for = AsyncMock()
    main.context.messages.submit = MagicMock()
    main.group_chat_context = None
    return main


@pytest.mark.asyncio
async def test_empty_mention_does_not_request_llm_or_resubmit():
    main = _make_empty_mention_main()
    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:GroupMessage:group"
    event.get_messages.return_value = [Mention(target="bot")]
    event.get_self_id.return_value = "bot"
    event.request_llm = MagicMock()
    event.message_obj.message = [Mention(target="bot")]

    results = [item async for item in main.handle_empty_mention(event)]

    assert results == []
    event.request_llm.assert_not_called()
    main.context.messages.wait_for.assert_not_awaited()
    main.context.messages.submit.assert_not_called()


@pytest.mark.asyncio
async def test_empty_mention_waiting_false_skips_prefix_only_wait():
    main = _make_empty_mention_main()
    main.context.config.get.return_value = {
        "platform_settings": {
            "empty_mention_waiting": False,
            "empty_mention_waiting_need_reply": True,
        },
        "command_prefixes": ["/"],
    }
    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:GroupMessage:group"
    event.get_messages.return_value = [Plain("/")]
    event.is_private_chat.return_value = False
    event.request_llm = MagicMock()

    results = [item async for item in main.handle_empty_mention(event)]

    assert results == []
    event.request_llm.assert_not_called()
    main.context.messages.wait_for.assert_not_awaited()
    main.context.messages.submit.assert_not_called()


@pytest.mark.asyncio
async def test_prefix_only_wait_skips_when_group_llm_off():
    main = _make_empty_mention_main()
    main.context.config.get.return_value = {
        "platform_settings": {
            "empty_mention_waiting": True,
            "empty_mention_waiting_need_reply": True,
        },
        "command_prefixes": ["/"],
        "llm_access": {"group": "off", "private": "prefix"},
    }
    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:GroupMessage:group"
    event.get_messages.return_value = [Plain("/")]
    event.is_private_chat.return_value = False
    event.request_llm = MagicMock()

    results = [item async for item in main.handle_empty_mention(event)]

    assert results == []
    event.request_llm.assert_not_called()
    main.context.messages.wait_for.assert_not_awaited()
    main.context.messages.submit.assert_not_called()


@pytest.mark.asyncio
async def test_prefix_only_wait_skips_when_private_llm_off():
    main = _make_empty_mention_main()
    main.context.config.get.return_value = {
        "platform_settings": {
            "empty_mention_waiting": True,
            "empty_mention_waiting_need_reply": True,
        },
        "command_prefixes": ["/"],
        "llm_access": {"group": "prefix", "private": "off"},
    }
    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:FriendMessage:user"
    event.get_messages.return_value = [Plain("/")]
    event.is_private_chat.return_value = True
    event.request_llm = MagicMock()

    results = [item async for item in main.handle_empty_mention(event)]

    assert results == []
    event.request_llm.assert_not_called()
    main.context.messages.wait_for.assert_not_awaited()
    main.context.messages.submit.assert_not_called()


@pytest.mark.asyncio
async def test_command_prefix_only_still_waits_without_synthesizing_mention():
    main = _make_empty_mention_main()
    waiter_holder: dict[str, object] = {}

    async def capture_wait(event, waiter, timeout_seconds=60):
        _ = event
        _ = timeout_seconds
        waiter_holder["waiter"] = waiter

    main.context.messages.wait_for = capture_wait
    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:GroupMessage:group"
    event.get_messages.return_value = [Plain("/")]
    event.is_private_chat.return_value = False
    event.get_self_id.return_value = "bot"
    event.get_platform_id.return_value = "aiocqhttp"
    event.request_llm = MagicMock(return_value="llm")
    event.plain_result = MagicMock()

    results = [item async for item in main.handle_empty_mention(event)]

    assert results == ["llm"]
    event.request_llm.assert_called_once()
    waiter = waiter_holder["waiter"]
    follow_up = MagicMock()
    follow_up.message_str = "hello"
    follow_up.message_obj.message = [Plain("hello")]
    follow_up.get_self_id.return_value = "bot"
    controller = MagicMock()
    await waiter(controller, follow_up)
    assert all(not isinstance(item, Mention) for item in follow_up.message_obj.message)
    follow_up.set_extra.assert_called_once_with("explicit_surface", True)
    main.context.messages.submit.assert_called_once()
    follow_up.stop_event.assert_called_once()
    controller.stop.assert_called_once()
