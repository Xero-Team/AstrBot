from astrbot import logger
from astrbot.core.auth.admission import (
    SESSION_SERVICE_CONFIG_KEY,
    SenderAdmissionOverlay,
    UnlistedPolicy,
    compose_admission,
    session_admission_key_from_event,
    session_overlay_from_config,
)
from astrbot.core.auth.models import Resource
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage

_NOTICE_REQUEST_TYPES = frozenset({"notice", "request"})


class AdmissionCheckStage(Stage):
    """Admit events by unlisted-session policy and listed session overlays."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        if ctx.preferences is None:
            raise RuntimeError("AdmissionCheckStage requires shared preferences")
        self.preferences = ctx.preferences
        admission = ctx.astrbot_config.get("admission")
        raw_policy = (
            admission.get("unlisted_sessions", UnlistedPolicy.ALLOW)
            if isinstance(admission, dict)
            else UnlistedPolicy.ALLOW
        )
        try:
            self.unlisted_sessions = UnlistedPolicy(raw_policy)
        except ValueError:
            self.unlisted_sessions = UnlistedPolicy.ALLOW

    async def process(self, event: AstrMessageEvent) -> None:
        if event.get_platform_name() == "webchat":
            return
        if event.get_extra("onebot_post_type") in _NOTICE_REQUEST_TYPES:
            return
        if await self._can_bypass(event):
            return

        session_key = session_admission_key_from_event(event)
        session_overlay = session_overlay_from_config(
            await self.preferences.session_get(
                session_key,
                SESSION_SERVICE_CONFIG_KEY,
                {},
            )
        )
        decision = compose_admission(
            session_overlay,
            SenderAdmissionOverlay(),
            unlisted_sessions=self.unlisted_sessions,
            unlisted_senders=UnlistedPolicy.ALLOW,
        )
        if decision.admit_event or session_overlay.session_blocked:
            return
        logger.info(
            "Session %s is unlisted and unlisted_sessions=deny; stopping event.",
            session_key,
        )
        event.stop_event()

    async def _can_bypass(self, event: AstrMessageEvent) -> bool:
        if (
            self.ctx.authorization is None
            or event.subject is None
            or event.resource is None
            or event.auth_context is None
            or event.resource.config_id is None
        ):
            return False
        return (
            await self.ctx.authorization.authorize(
                event.subject,
                "provider.manage",
                Resource.instance(event.resource.config_id),
                event.auth_context,
            )
        ).allowed
