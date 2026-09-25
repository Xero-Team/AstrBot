from astrbot import logger
from astrbot.core.auth.admission import (
    SESSION_SERVICE_CONFIG_KEY,
    UnlistedPolicy,
    compose_admission,
    sender_admission_key_from_event,
    sender_overlay_from_config,
    session_admission_key_from_event,
    session_overlay_from_config,
)
from astrbot.core.auth.models import Resource
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.command_ids import BUILTIN_COMMANDS_MODULE

from ..context import PipelineContext
from ..stage import Stage

_NOTICE_REQUEST_TYPES = frozenset({"notice", "request"})
SENDER_BLOCKED_PASSTHROUGH_HANDLERS = frozenset(
    {
        f"{BUILTIN_COMMANDS_MODULE}_user_unblock",
        f"{BUILTIN_COMMANDS_MODULE}_bot_status",
    }
)


def allows_blocked_sender(event: AstrMessageEvent) -> bool:
    """Return whether an activated handler may run while the sender is blocked."""
    handlers = event.get_extra("activated_handlers") or ()
    return any(
        getattr(handler, "handler_full_name", "") in SENDER_BLOCKED_PASSTHROUGH_HANDLERS
        for handler in handlers
    )


class AdmissionCheckStage(Stage):
    """Admit events by unlisted-session/sender policy and listed overlays."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        if ctx.preferences is None:
            raise RuntimeError("AdmissionCheckStage requires shared preferences")
        self.preferences = ctx.preferences
        admission = ctx.astrbot_config.get("admission")
        admission_map = admission if isinstance(admission, dict) else {}
        self.unlisted_sessions = self._unlisted_policy(
            admission_map.get("unlisted_sessions", UnlistedPolicy.ALLOW),
            "unlisted_sessions",
        )
        self.unlisted_senders = self._unlisted_policy(
            admission_map.get("unlisted_senders", UnlistedPolicy.ALLOW),
            "unlisted_senders",
        )

    async def process(self, event: AstrMessageEvent) -> None:
        if event.get_platform_name() == "webchat":
            return
        if event.get_extra("onebot_post_type") in _NOTICE_REQUEST_TYPES:
            return
        if await self._can_bypass(event):
            return

        session_key = session_admission_key_from_event(event)
        sender_key = sender_admission_key_from_event(event)
        session_overlay = session_overlay_from_config(
            await self.preferences.session_get(
                session_key,
                SESSION_SERVICE_CONFIG_KEY,
                {},
            )
        )
        sender_overlay = sender_overlay_from_config(
            await self.preferences.sender_get(
                sender_key,
                SESSION_SERVICE_CONFIG_KEY,
                {},
            )
        )
        decision = compose_admission(
            session_overlay,
            sender_overlay,
            unlisted_sessions=self.unlisted_sessions,
            unlisted_senders=self.unlisted_senders,
        )
        if decision.admit_event or session_overlay.session_blocked:
            return
        session_denied = (
            self.unlisted_sessions is UnlistedPolicy.DENY and not session_overlay.listed
        )
        if (
            decision.sender_blocked
            and allows_blocked_sender(event)
            and not session_denied
        ):
            return
        if decision.sender_blocked:
            logger.info("Sender %s is blocked; stopping event.", sender_key)
        elif self.unlisted_senders is UnlistedPolicy.DENY and not sender_overlay.listed:
            logger.info(
                "Sender %s is unlisted and unlisted_senders=deny; stopping event.",
                sender_key,
            )
        else:
            logger.info(
                "Session %s is unlisted and unlisted_sessions=deny; stopping event.",
                session_key,
            )
        event.stop_event()

    def _unlisted_policy(self, raw_policy: object, name: str) -> UnlistedPolicy:
        try:
            return UnlistedPolicy(raw_policy)
        except ValueError:
            logger.warning("Invalid %s %r; defaulting to allow", name, raw_policy)
            return UnlistedPolicy.ALLOW

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
