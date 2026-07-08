import hashlib

from astrbot.core.agent.message import TextPart
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest

from .injector import PersonaRuntimeInjector
from .learners import BehaviorLearner, ExpressionLearner, JargonLearner
from .models import PersonaRuntimeSignal
from .proactive_scheduler import ProactiveScheduler
from .signals import event_mentions_bot
from .state_store import PersonaRuntimeStateStore


class PersonaRuntimeManager:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.state_store = PersonaRuntimeStateStore(db)
        self.injector = PersonaRuntimeInjector()
        self.proactive_scheduler = ProactiveScheduler()
        self.expression_learner = ExpressionLearner(db)
        self.jargon_learner = JargonLearner(db)
        self.behavior_learner = BehaviorLearner(db)

    async def initialize(self) -> None:
        return

    async def inject_context(
        self,
        *,
        req: ProviderRequest,
        persona_id: str,
        umo: str,
    ) -> None:
        state = await self.state_store.get_or_create(persona_id, umo)
        self.injector.inject(req, state)
        scope = f"isolated:{umo}"
        expressions = await self.db.list_persona_expression_assets(
            persona_id=persona_id,
            scope=scope,
            limit=3,
        )
        jargon = await self.db.list_persona_jargon_assets(
            persona_id=persona_id,
            scope=scope,
            approved=True,
            limit=3,
        )
        policies = await self.db.list_persona_behavior_policies(
            persona_id=persona_id,
            scope=scope,
            limit=3,
        )
        if expressions or jargon or policies:
            lines = ["<persona_learned_assets>"]
            if expressions:
                lines.append("Expression preferences:")
                lines.extend(f"- {item.style_text}" for item in expressions)
            if jargon:
                lines.append("Approved jargon:")
                lines.extend(
                    f"- {item.term}: {item.meaning or 'context-specific term'}"
                    for item in jargon
                )
            if policies:
                lines.append("Behavior policies:")
                lines.extend(
                    f"- {item.situation}: {item.preferred_action}" for item in policies
                )
            lines.append("Use these transient learned assets only when relevant.")
            lines.append("</persona_learned_assets>")
            req.extra_user_content_parts.append(
                TextPart(text="\n".join(lines)).mark_as_temp()
            )

    async def process_turn(
        self,
        *,
        event: AstrMessageEvent,
        persona_id: str,
        conversation_id: str | None,
        assistant_text: str,
    ) -> None:
        sender = getattr(getattr(event, "message_obj", None), "sender", None)
        signal = PersonaRuntimeSignal(
            persona_id=persona_id,
            umo=event.unified_msg_origin,
            user_text=event.message_str or "",
            assistant_text=assistant_text,
            sender_id=str(getattr(sender, "user_id", "") or "unknown"),
            conversation_id=conversation_id,
            mentioned=event_mentions_bot(event),
        )
        await self.state_store.apply_signal(signal)
        digest = hashlib.sha256(
            f"{event.unified_msg_origin}\n{event.message_str or ''}\n{assistant_text}".encode()
        ).hexdigest()[:24]
        source_message_id = f"{conversation_id or event.unified_msg_origin}:{digest}"
        scope = f"isolated:{event.unified_msg_origin}"
        await self.expression_learner.learn(
            persona_id=persona_id,
            scope=scope,
            user_text=event.message_str or "",
            assistant_text=assistant_text,
            source_message_id=source_message_id,
        )
        await self.jargon_learner.learn(
            persona_id=persona_id,
            scope=scope,
            user_text=event.message_str or "",
            source_message_id=source_message_id,
        )
        await self.behavior_learner.learn(
            persona_id=persona_id,
            scope=scope,
            user_text=event.message_str or "",
            assistant_text=assistant_text,
        )
