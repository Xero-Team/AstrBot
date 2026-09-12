from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.pipeline.whitelist_check.stage import WhitelistCheckStage


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
