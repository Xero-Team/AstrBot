from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)


def test_extract_response_message_id_supports_platform_send_result():
    result = PlatformSendResult(
        platform_id="qq_official",
        success=True,
        target="user-1",
        message_id="msg-42",
    )

    assert QQOfficialMessageEvent._extract_response_message_id(result) == "msg-42"
