from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.pipeline.whitelist_check.stage import WhitelistCheckStage
from astrbot.core.platform.message_type import MessageType


@pytest.mark.asyncio
async def test_can_bypass_authorizes_provider_manage_against_instance_resource():
    subject = Subject.im(
        platform_instance="napcat", bot_account_id="bot", sender_id="42"
    )
    session = Resource.session("default", "napcat:GroupMessage:room-a")
    context = AuthContext(
        subject=subject,
        source="im",
        config_id="default",
        origin_session_resource_id=session.id,
        authenticated=True,
    )
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )
    stage = WhitelistCheckStage()
    stage.ctx = SimpleNamespace(
        authorization=authorization, astrbot_config_id="default"
    )
    event = SimpleNamespace(
        subject=subject,
        resource=session,
        auth_context=context,
    )

    assert await stage._can_bypass(event)
    authorization.authorize.assert_awaited_once_with(
        subject,
        "provider.manage",
        Resource.instance("default"),
        context,
    )


class _WhitelistEvent:
    def __init__(self, *, umo: str, group_id: str) -> None:
        self.unified_msg_origin = umo
        self._group_id = group_id
        self.stopped = False

    def get_platform_name(self) -> str:
        return "napcat"

    def get_message_type(self):
        return MessageType.GROUP_MESSAGE

    def get_group_id(self) -> str:
        return self._group_id

    def stop_event(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_whitelist_still_matches_umo_or_group_id():
    stage = WhitelistCheckStage()
    stage.enable_whitelist_check = True
    stage.whitelist = ["room-a"]
    stage.wl_ignore_admin_on_group = False
    stage.wl_ignore_admin_on_friend = False
    stage.wl_log = False

    allowed = _WhitelistEvent(
        umo="napcat:GroupMessage:user-1_room-a",
        group_id="room-a",
    )
    denied = _WhitelistEvent(
        umo="napcat:GroupMessage:user-1_room-b",
        group_id="room-b",
    )

    await stage.process(allowed)
    await stage.process(denied)

    assert allowed.stopped is False
    assert denied.stopped is True
