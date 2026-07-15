from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage


def _make_stage(
    *, use_file_service: bool, callback_api_base: str
) -> ResultDecorateStage:
    stage = ResultDecorateStage()
    stage.reply_prefix = ""
    stage.content_safe_check_reply = False
    stage.enable_segmented_reply = False
    stage.only_llm_result = False
    stage.words_count_threshold = 100
    stage.split_mode = "words"
    stage.split_words = ["。"]
    stage.split_words_pattern = None
    stage.content_cleanup_rule = ""
    stage.show_reasoning = False
    stage.tts_trigger_probability = 0
    stage.reply_with_mention = False
    stage.reply_with_quote = False
    stage.forward_threshold = 1000
    stage.t2i_word_threshold = 10
    stage.t2i_active_template = "base"
    stage.t2i_use_file_service = use_file_service
    stage.ctx = SimpleNamespace(
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(get_using_tts_provider=lambda _umo: None),
        ),
        astrbot_config={
            "provider_tts_settings": {
                "enable": False,
                "use_file_service": False,
                "dual_output": False,
            },
            "callback_api_base": callback_api_base,
            "t2i": True,
        },
        html_renderer=SimpleNamespace(render_t2i=AsyncMock()),
        file_token_service=SimpleNamespace(register_file=AsyncMock()),
    )
    return stage


@pytest.mark.asyncio
async def test_result_decorate_uses_local_t2i_and_file_token_url(monkeypatch):
    stage = _make_stage(
        use_file_service=False,
        callback_api_base="http://127.0.0.1:6185/",
    )
    result = MessageEventResult(chain=[Plain("0123456789abcde")])
    tracked_files: list[str] = []

    async def fake_render_t2i(text: str, template_name: str | None = None) -> str:
        assert text == "\n\n0123456789abcde"
        assert template_name == "base"
        return "D:/temp/rendered.png"

    async def fake_register_file(path: str) -> str:
        assert path == "D:/temp/rendered.png"
        return "token-123"

    monkeypatch.setattr(stage.ctx.html_renderer, "render_t2i", fake_render_t2i)
    monkeypatch.setattr(
        stage.ctx.file_token_service, "register_file", fake_register_file
    )

    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="napcat:FriendMessage:42",
        get_result=lambda: result,
        get_platform_name=lambda: "napcat",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
        track_temporary_local_file=tracked_files.append,
    )

    processed = stage.process(cast(Any, event))
    if hasattr(processed, "__aiter__"):
        async for _ in cast(Any, processed):
            pass
    else:
        await cast(Any, processed)

    image = result.chain[0]
    assert image.file == "http://127.0.0.1:6185/api/v1/files/tokens/token-123"
    assert tracked_files == ["D:/temp/rendered.png"]


@pytest.mark.asyncio
async def test_result_decorate_keeps_local_file_when_no_callback_url(
    monkeypatch, tmp_path
):
    stage = _make_stage(use_file_service=False, callback_api_base="")
    result = MessageEventResult(chain=[Plain("0123456789abcde")])
    image_path = tmp_path / "rendered.png"

    monkeypatch.setattr(
        stage.ctx.html_renderer,
        "render_t2i",
        AsyncMock(return_value=str(image_path)),
    )

    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="qq_official:GroupMessage:group-1",
        get_result=lambda: result,
        get_platform_name=lambda: "qq_official",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
        track_temporary_local_file=lambda *_args, **_kwargs: None,
    )

    processed = stage.process(cast(Any, event))
    if hasattr(processed, "__aiter__"):
        async for _ in cast(Any, processed):
            pass
    else:
        await cast(Any, processed)

    image = result.chain[0]
    assert image.file == image_path.resolve().as_uri()
    assert image.path == str(image_path.resolve())
