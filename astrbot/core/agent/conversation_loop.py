"""Opt-in conversation entry over the existing Agent request executor."""

import asyncio
import math
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import asdict
from typing import TYPE_CHECKING

from astrbot.core.agent.btw import i18n as work_i18n
from astrbot.core.agent.btw.classifier import (
    RoutingResult,
    classify_request,
    routing_state,
)
from astrbot.core.agent.btw.conversation_report import compose_work_report
from astrbot.core.agent.btw.types import is_work_loop_enabled
from astrbot.core.agent.btw.work_loop import WorkLoop
from astrbot.core.agent.btw.work_sessions import WorkSessionManager
from astrbot.core.message.components import Mention, Plain
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.typed_decision import ClassifierModel

if TYPE_CHECKING:
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
    )


class ConversationLoop:
    """Own conversation admission and the opt-in classifier experiment."""

    def __init__(self, agent_request: AgentRequestSubStage) -> None:
        self.agent_request = agent_request
        self._btw_enabled = False
        self._report_via_conversation = True
        self._result_dispatcher: (
            Callable[[AstrMessageEvent], Awaitable[None]] | None
        ) = None
        self.work_sessions = WorkSessionManager()
        self.work_loop: WorkLoop | None = None

    async def initialize(self, ctx: PipelineContext) -> None:
        """Initialize the shared Agent executor for this profile."""
        self.astrbot_config = ctx.astrbot_config
        self.ctx = ctx
        btw = self.astrbot_config.get("btw", {})
        self._btw_enabled = isinstance(btw, dict) and bool(btw.get("enabled", False))
        await self.agent_request.initialize(ctx)
        btw = btw if isinstance(btw, dict) else {}
        work = btw.get("work_loop", {})
        work = work if isinstance(work, dict) else {}
        self._report_via_conversation = bool(work.get("report_via_conversation", True))
        retention = btw.get("work_session", {})
        retention = retention if isinstance(retention, dict) else {}
        self.work_sessions.set_max_age_seconds(retention.get("max_age_seconds", 3600))
        concurrency = work.get("max_concurrent", 2)
        self.work_loop = WorkLoop(
            self.agent_request,
            self.work_sessions,
            max_concurrent=concurrency if type(concurrency) is int else 2,
        )

    def configure_detached_work(
        self,
        *,
        background_tasks: set[asyncio.Task],
        result_dispatcher: Callable[[AstrMessageEvent], Awaitable[None]],
        event_finalizer: Callable[[AstrMessageEvent], Awaitable[None]],
    ) -> None:
        """Attach the owning scheduler's delivery and cleanup services."""
        if self.work_loop is None:
            raise RuntimeError("ConversationLoop is not initialized")
        self._result_dispatcher = result_dispatcher
        self.work_loop.configure_detached_execution(
            background_tasks=background_tasks,
            result_dispatcher=result_dispatcher,
            event_finalizer=event_finalizer,
            result_reporter=(
                self.report_work_result if self._report_via_conversation else None
            ),
        )

    async def report_work_result(
        self, event: AstrMessageEvent, session_id: str
    ) -> None:
        """Report one finished work run to the user.

        The work loop calls this instead of delivering the result itself: the
        conversation loop is the user's counterpart, so the completion report
        is composed here and sent through the runtime's normal response path.

        Args:
            event: The work event whose result is ready to go out.
            session_id: The work session that produced the result.

        Raises:
            RuntimeError: No delivery path was attached, so nothing can be sent.
        """
        if self._result_dispatcher is None:
            raise RuntimeError("ConversationLoop has no result dispatcher")
        session = await self.work_sessions.get_by_id(session_id)
        compose_work_report(event, session, work_i18n.resolve_event_locale(event))
        await self._result_dispatcher(event)

    async def close(self) -> None:
        """Stop work owned by this conversation entry."""
        if self.work_loop is not None:
            await self.work_loop.close()

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        """Process one admitted conversation using the current Agent path."""
        if event.get_extra("btw_classifier_processed"):
            return
        if (
            self._btw_enabled
            and event.get_extra("btw_force_work")
            and is_work_loop_enabled(self.astrbot_config)
        ):
            if self.work_loop is None:
                raise RuntimeError("ConversationLoop is not initialized")
            async for response in self.work_loop.submit(event):
                yield response
            return
        if self._btw_enabled:
            event.set_extra("btw_loop", "conversation")
        settings = (
            self.astrbot_config.get("btw", {}).get("classifier", {})
            if self._btw_enabled
            else {}
        )
        if self._can_classify(event, settings):
            # Claim before the admission check's await as well as the model call.
            event.set_extra("btw_classifier_processed", True)
            event.set_extra("btw_classifier_no_handoff", True)
            if (
                not await self.agent_request.session_services.should_process_llm_request(
                    event
                )
                or event.is_stopped()
            ):
                return
            routing = await self._classify(event, settings)
            event.set_extra("btw_classifier_result", asdict(routing))
            if event.is_stopped():
                return
            if routing.decision == "work" and is_work_loop_enabled(self.astrbot_config):
                assert self.work_loop is not None
                async for response in self.work_loop.submit(event):
                    yield response
                return
            if routing.decision == "unavailable" or (
                settings.get("clarify_on_uncertain", False)
                and (routing.decision == "clarify" or routing.source == "safe_default")
            ):
                key = "unavailable" if routing.decision == "unavailable" else "clarify"
                event.set_result(
                    MessageEventResult().message(
                        work_i18n.text(
                            work_i18n.resolve_event_locale(event),
                            f"btw.classifier.{key}",
                        )
                    )
                )
                yield
                return
        async for response in self.agent_request.process(event):
            yield response

    def _can_classify(self, event: AstrMessageEvent, settings: object) -> bool:
        """Only ordinary admitted text requests on the local Agent are eligible."""
        return (
            isinstance(settings, dict)
            and settings.get("enabled") is True
            and bool(
                settings.get("provider_id") or settings.get("fallback_provider_id")
            )
            and is_work_loop_enabled(self.astrbot_config)
            and self.astrbot_config.get("agent_runner", {}).get("runner_type", "local")
            == "local"
            and self.astrbot_config.get("provider_settings", {}).get("enable", True)
            and not event.get_extra("provider_request")
            and not event.get_extra("btw_work_session_id")
            and not event.is_stopped()
            and bool(event.message_str.strip())
            and len(event.message_str) <= 8000
            and all(
                isinstance(part, Plain | Mention) for part in event.message_obj.message
            )
        )

    async def _classify(self, event: AstrMessageEvent, settings: dict) -> RoutingResult:
        from astrbot.core.astr_main_agent import (
            _is_chat_model,
            _select_provider,
            resolve_btw_capabilities,
        )

        try:
            threshold = settings.get("confidence_threshold", 0.85)
            if (
                type(threshold) not in (int, float)
                or not math.isfinite(threshold)
                or not 0 <= threshold <= 1
            ):
                return RoutingResult()
            context = self.ctx.execution_context
            capabilities = await resolve_btw_capabilities(event, context)
            state = routing_state(event.message_str, capabilities)
            provider_id = settings.get("provider_id", "")
            classifier = (
                context.get_provider_by_id(provider_id) if provider_id else None
            )
            fallback_id = settings.get("fallback_provider_id", "")
            if fallback_id:
                fallback = context.get_provider_by_id(fallback_id)
            else:
                loop_settings = self.astrbot_config.get("btw", {}).get(
                    "conversation_loop", {}
                )
                fallback = _select_provider(
                    event, context, loop_settings.get("provider_id", "")
                )
            return await classify_request(
                state,
                classifier if isinstance(classifier, ClassifierModel) else None,
                fallback if _is_chat_model(fallback) else None,
                confidence_threshold=threshold,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return RoutingResult()
