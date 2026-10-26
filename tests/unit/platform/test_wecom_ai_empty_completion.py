import pytest

from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_queue_mgr import WecomAIQueueMgr


@pytest.mark.asyncio
async def test_send_none_terminates_the_stream_queue():
    manager = WecomAIQueueMgr()
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="user-1", nickname="Sender")
    message.self_id = "bot-1"
    message.session_id = "user-1"
    message.message_id = "msg-1"
    message.message = []
    message.message_str = ""
    message.raw_message = {"stream_id": "stream-1"}
    event = WecomAIBotMessageEvent(
        message_str="",
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="wecom_ai_bot",
            description="WeCom AI",
            id="wecom-ai-test",
            support_streaming_message=True,
        ),
        session_id="user-1",
        api_client=None,
        queue_mgr=manager,
    )

    await event.send(None)

    queued = manager.get_or_create_back_queue("stream-1").get_nowait()
    assert queued["type"] == "end"
    assert queued["data"] == ""
