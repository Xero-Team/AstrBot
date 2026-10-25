import pytest

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.weixin_official_account import (
    weixin_offacc_event,
)
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_event import (
    WeixinOfficialAccountPlatformEvent,
)


class RecordingLogger:
    def __init__(self):
        self.calls = []

    def error(self, *args):
        self.calls.append(args)


@pytest.mark.asyncio
async def test_wechat_upload_failure_is_generic_and_redacted(monkeypatch):
    sent = []

    async def fake_send(_self, message):
        sent.append(message)
        return object()

    monkeypatch.setattr(AstrMessageEvent, "send", fake_send)
    recorder = RecordingLogger()
    monkeypatch.setattr(weixin_offacc_event, "logger", recorder)
    event = object.__new__(WeixinOfficialAccountPlatformEvent)

    result = await event._send_upload_failure(
        "图片",
        RuntimeError(
            "upload failed https://api.weixin.qq.com/cgi-bin/media/upload"
            "?access_token=secret-token"
        ),
    )

    assert result is not None
    assert len(sent) == 1
    text = sent[0].chain[0].text
    assert "secret-token" not in text
    assert "access_token" not in text
    assert "上传图片失败" in text

    rendered_log = " ".join(str(arg) for arg in recorder.calls[0])
    assert "secret-token" not in rendered_log
    assert "access_token" not in rendered_log
