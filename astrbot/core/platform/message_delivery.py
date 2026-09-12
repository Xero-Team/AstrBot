"""Execution of portable message delivery plans."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace

from astrbot.core.message.components import (
    BaseMessageComponent,
    ComponentTypes,
    File,
    Image,
    Mention,
    MentionAll,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.message_event_result import MessageChain

from .message_i18n import DEFAULT_LOCALE
from .message_protocol import (
    ContentKind,
    DeliveryBatch,
    MediaReference,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    NativeContent,
    PortablePart,
    plan_delivery,
)


def _media_component(kind: ContentKind, value: MediaReference) -> BaseMessageComponent:
    """Create a transport-neutral media component from a resolved reference."""
    source = value.uri
    if kind == ContentKind.IMAGE:
        return Image(file=source, path=source)
    if kind == ContentKind.AUDIO:
        return Record(file=source, path=source)
    if kind == ContentKind.VIDEO:
        return Video(file=source, path=source)
    return File(file=source, name=value.file_name or "attachment")


def _portable_component(part: PortablePart) -> BaseMessageComponent:
    """Convert one portable part to an existing AstrBot component."""
    if part.kind == ContentKind.TEXT or part.kind == ContentKind.LINK:
        return Plain(str(part.value))
    if part.kind in {
        ContentKind.IMAGE,
        ContentKind.AUDIO,
        ContentKind.VIDEO,
        ContentKind.FILE,
    }:
        if not isinstance(part.value, MediaReference):
            raise TypeError(f"{part.kind} requires a MediaReference")
        return _media_component(part.kind, part.value)
    if part.kind == ContentKind.MENTION:
        data = (
            part.value if isinstance(part.value, Mapping) else {"id": str(part.value)}
        )
        return Mention(target=str(data.get("id", "")), name=str(data.get("name", "")))
    if part.kind == ContentKind.MENTION_ALL:
        return MentionAll()
    fallback = part.alt_text or f"[{part.kind.value}]"
    return Plain(fallback)


def _native_component(native: NativeContent) -> BaseMessageComponent | None:
    """Rehydrate a fresh component from a source-independent JSON snapshot."""
    component_type = ComponentTypes.get(native.kind)
    if component_type is None:
        return None
    try:
        return component_type.model_validate_json(native.payload)
    except ValueError:
        return None


def batch_to_message_chain(
    batch: DeliveryBatch,
    *,
    capabilities: MessageDeliveryCapabilities,
    quote_id: str | None = None,
) -> MessageChain:
    """Convert one planned batch into a chain for the target adapter."""
    components: list[BaseMessageComponent] = []
    if batch.quote is not None:
        if capabilities.quote and quote_id:
            components.append(Reply(id=quote_id))
        else:
            preview = batch.quote.preview or batch.quote.message_id
            components.append(Plain(f"> {preview}\n"))
    for part in batch.parts:
        components.append(_portable_component(part))
    if batch.native:
        for native in batch.native:
            component = _native_component(native)
            if (
                component is not None
                and native.namespace in capabilities.native_namespaces
                and native.kind in capabilities.native_kinds
            ):
                components.append(component)
            elif native.fallback:
                components.append(Plain(native.fallback))
    return MessageChain(components).use_markdown(False)


def plan_message_delivery(
    envelope: MessageEnvelope,
    capabilities: MessageDeliveryCapabilities,
    *,
    quote_id: str | None = None,
    target_umo: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> tuple[MessageChain, ...]:
    """Return ordered target chains, preserving Planner batch boundaries."""
    if target_umo != envelope.source_route.as_origin():
        capabilities = replace(capabilities, mention=False)
    if target_umo and target_umo.split(":", 1)[0] != envelope.source_route.platform_id:
        capabilities = replace(capabilities, native_namespaces=frozenset())
    if envelope.quote and not (capabilities.quote and quote_id):
        preview = envelope.quote.preview or envelope.quote.message_id
        envelope = replace(
            envelope,
            quote=None,
            content=(
                PortablePart(ContentKind.TEXT, f"> {preview}\n"),
                *envelope.content,
            ),
        )
    return tuple(
        batch_to_message_chain(batch, capabilities=capabilities, quote_id=quote_id)
        for batch in plan_delivery(envelope, capabilities, locale=locale)
    )


def iter_delivery_parts(batches: Iterable[DeliveryBatch]) -> Iterable[PortablePart]:
    """Iterate portable parts in transport order for diagnostics."""
    for batch in batches:
        yield from batch.parts


__all__ = [
    "batch_to_message_chain",
    "iter_delivery_parts",
    "plan_message_delivery",
]
