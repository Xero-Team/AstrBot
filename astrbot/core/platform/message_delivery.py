"""Execution of portable message delivery plans."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from astrbot.core.message.components import (
    BaseMessageComponent,
    ComponentTypes,
    Contact,
    Face,
    File,
    Image,
    Json,
    Location,
    Mention,
    MentionAll,
    MFace,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.json_card import format_json_card_prompt
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.message.qq_face import format_qq_face

from .message_i18n import DEFAULT_LOCALE, LOCALES, localize, message_key
from .message_protocol import (
    ContentKind,
    DeliveryBatch,
    MediaReference,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    NativeContent,
    PortablePart,
    SenderSnapshot,
    plan_delivery,
)

_REPLAY_NATIVE_KINDS = frozenset(
    {
        "face",
        "mface",
        "json",
        "poke",
        "markdown",
        "miniapp",
        "xml",
        "dice",
        "rps",
        "shake",
        "share",
        "music",
    }
)
_UNKNOWN_AUTHOR_TEXTS = frozenset(
    {
        message_key("unknown_author"),
        *(bundle["astrbot.msg.unknown_author"] for bundle in LOCALES.values()),
    }
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


def _item_sender(item: PortablePart | NativeContent) -> SenderSnapshot | None:
    return item.sender


def _is_author_separator(item: PortablePart | NativeContent, locale: str) -> bool:
    if (
        not isinstance(item, PortablePart)
        or item.kind != ContentKind.TEXT
        or item.sender is None
    ):
        return False
    value = str(item.value)
    if value in _UNKNOWN_AUTHOR_TEXTS:
        return True
    if value == localize(locale, "astrbot.msg.unknown_author"):
        return True
    sender = item.sender
    return value in {f"[{sender.name}]\n", f"[{sender.id}]\n"}


def _split_sender_islands(
    content: Sequence[PortablePart | NativeContent],
) -> list[tuple[bool, list[PortablePart | NativeContent]]]:
    islands: list[tuple[bool, list[PortablePart | NativeContent]]] = []
    for item in content:
        has_sender = _item_sender(item) is not None
        if islands and islands[-1][0] == has_sender:
            islands[-1][1].append(item)
        else:
            islands.append((has_sender, [item]))
    return islands


def _native_flatten_text(native: NativeContent) -> str | None:
    component = _native_component(native)
    if isinstance(component, Face):
        return format_qq_face(component.id)
    if isinstance(component, Json):
        return format_json_card_prompt(component)
    if isinstance(component, MFace):
        return component.summary or "[MFace]"
    return None


def _enrich_native_fallbacks(envelope: MessageEnvelope) -> MessageEnvelope:
    content: list[PortablePart | NativeContent] = []
    for item in envelope.content:
        if isinstance(item, NativeContent):
            richer = _native_flatten_text(item)
            if richer is not None and richer != item.fallback:
                item = replace(item, fallback=richer)
        content.append(item)
    return replace(envelope, content=tuple(content))


def _plan_flat(
    envelope: MessageEnvelope,
    capabilities: MessageDeliveryCapabilities,
    *,
    quote_id: str | None,
    locale: str,
) -> tuple[MessageChain, ...]:
    envelope = _enrich_native_fallbacks(envelope)
    return tuple(
        batch_to_message_chain(batch, capabilities=capabilities, quote_id=quote_id)
        for batch in plan_delivery(envelope, capabilities, locale=locale)
    )


def _node_identity(sender: SenderSnapshot, locale: str) -> tuple[str, str]:
    uin = sender.id or "0"
    name = sender.name or localize(locale, "astrbot.msg.unknown_sender")
    return uin, name


def _portable_node_component(
    part: PortablePart, *, cross_session: bool
) -> BaseMessageComponent | None:
    if part.kind == ContentKind.LOCATION:
        data = part.value if isinstance(part.value, Mapping) else {}
        try:
            return Location(
                lat=float(data.get("lat")),
                lon=float(data.get("lon")),
                title=str(data.get("title") or ""),
            )
        except TypeError, ValueError:
            return None
    if part.kind == ContentKind.CONTACT:
        data = part.value if isinstance(part.value, Mapping) else {}
        return Contact(_type=str(data.get("type") or ""), id=data.get("id"))
    if part.kind == ContentKind.MENTION and cross_session:
        data = (
            part.value if isinstance(part.value, Mapping) else {"id": str(part.value)}
        )
        name = str(data.get("name") or "") or str(data.get("id") or "")
        return Plain(f"@{name}")
    if part.kind == ContentKind.MENTION_ALL and cross_session:
        return Plain("@all")
    return _portable_component(part)


def _item_to_node_component(
    item: PortablePart | NativeContent, *, cross_session: bool
) -> BaseMessageComponent | None:
    if isinstance(item, NativeContent):
        if item.kind not in _REPLAY_NATIVE_KINDS:
            return None
        return _native_component(item)
    return _portable_node_component(item, cross_session=cross_session)


def _reconstruct_forward_chain(
    items: Sequence[PortablePart | NativeContent],
    *,
    locale: str,
    cross_session: bool,
) -> MessageChain | None:
    nodes: list[Node] = []
    current: Node | None = None

    def close_node() -> None:
        nonlocal current
        if current is not None and current.content:
            nodes.append(current)
        current = None

    def open_node(sender: SenderSnapshot) -> None:
        nonlocal current
        close_node()
        uin, name = _node_identity(sender, locale)
        current = Node(content=[], uin=uin, name=name)

    for item in items:
        if _is_author_separator(item, locale):
            assert item.sender is not None
            open_node(item.sender)
            continue
        sender = _item_sender(item)
        if current is None:
            if sender is None:
                continue
            open_node(sender)
        component = _item_to_node_component(item, cross_session=cross_session)
        if component is not None and current is not None:
            current.content.append(component)
    close_node()
    if not nodes:
        return None
    return MessageChain([Nodes(nodes=nodes)]).use_markdown(False)


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
    cross_session = target_umo != envelope.source_route.as_origin()
    if cross_session:
        capabilities = replace(capabilities, mention=False)
    root_capabilities = capabilities
    if target_umo and target_umo.split(":", 1)[0] != envelope.source_route.platform_id:
        root_capabilities = replace(capabilities, native_namespaces=frozenset())
    if envelope.quote and not (root_capabilities.quote and quote_id):
        preview = envelope.quote.preview or envelope.quote.message_id
        envelope = replace(
            envelope,
            quote=None,
            content=(
                PortablePart(ContentKind.TEXT, f"> {preview}\n"),
                *envelope.content,
            ),
        )
    has_forwarded = any(_item_sender(item) is not None for item in envelope.content)
    if not capabilities.forward or not has_forwarded:
        return _plan_flat(envelope, root_capabilities, quote_id=quote_id, locale=locale)

    chains: list[MessageChain] = []
    first = True
    remaining_quote = envelope.quote
    remaining_quote_id = quote_id
    for has_sender, items in _split_sender_islands(envelope.content):
        sub_envelope = replace(
            envelope,
            content=tuple(items),
            quote=remaining_quote if first else None,
        )
        sub_quote_id = remaining_quote_id if first else None
        first = False
        remaining_quote = None
        remaining_quote_id = None
        if not has_sender:
            chains.extend(
                _plan_flat(
                    sub_envelope,
                    root_capabilities,
                    quote_id=sub_quote_id,
                    locale=locale,
                )
            )
            continue
        reconstructed = _reconstruct_forward_chain(
            items, locale=locale, cross_session=cross_session
        )
        if reconstructed is None:
            chains.extend(
                _plan_flat(
                    sub_envelope,
                    root_capabilities,
                    quote_id=sub_quote_id,
                    locale=locale,
                )
            )
            continue
        if sub_envelope.quote is not None and root_capabilities.quote and sub_quote_id:
            reconstructed = MessageChain(
                [Reply(id=sub_quote_id), *reconstructed.chain]
            ).use_markdown(False)
        elif sub_envelope.quote is not None:
            preview = sub_envelope.quote.preview or sub_envelope.quote.message_id
            reconstructed = MessageChain(
                [Plain(f"> {preview}\n"), *reconstructed.chain]
            ).use_markdown(False)
        chains.append(reconstructed)
    return tuple(chains)


def iter_delivery_parts(batches: Iterable[DeliveryBatch]) -> Iterable[PortablePart]:
    """Iterate portable parts in transport order for diagnostics."""
    for batch in batches:
        yield from batch.parts


__all__ = [
    "batch_to_message_chain",
    "iter_delivery_parts",
    "plan_message_delivery",
]
