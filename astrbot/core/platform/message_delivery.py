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

from .message_i18n import (
    DEFAULT_LOCALE,
    LOCALES,
    localize,
    localize_kind,
    localize_value,
    message_key,
)
from .message_protocol import (
    ContentKind,
    DeliveryBatch,
    MediaReference,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    NativeContent,
    PortablePart,
    QuoteReference,
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
        batch_to_message_chain(
            batch, capabilities=capabilities, quote_id=quote_id, locale=locale
        )
        for batch in plan_delivery(envelope, capabilities, locale=locale)
    )


def _node_identity(sender: SenderSnapshot, locale: str) -> tuple[str, str]:
    uin = sender.id or "0"
    name = sender.name or localize(locale, "astrbot.msg.unknown_sender")
    return uin, name


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value:
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _part_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _location_component(value: object) -> Location | None:
    data = _part_mapping(value)
    lat = _as_float(data.get("lat"))
    lon = _as_float(data.get("lon"))
    if lat is None or lon is None:
        return None
    return Location(lat=lat, lon=lon, title=str(data.get("title") or ""))


def _contact_component(value: object) -> Contact | None:
    data = _part_mapping(value)
    raw_id = data.get("id")
    if raw_id is None or raw_id == "":
        contact_id = None
    else:
        contact_id = _as_int(raw_id)
        if contact_id is None:
            return None
    return Contact(_type=str(data.get("type") or ""), id=contact_id)


def _portable_node_component(
    part: PortablePart, *, cross_session: bool
) -> BaseMessageComponent | None:
    if part.kind == ContentKind.LOCATION:
        return _location_component(part.value)
    if part.kind == ContentKind.CONTACT:
        return _contact_component(part.value)
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
        sender = _item_sender(item)
        if _is_author_separator(item, locale):
            if sender is not None:
                open_node(sender)
            continue
        if current is None:
            if sender is None:
                continue
            open_node(sender)
        if isinstance(item, PortablePart) and item.kind in {
            ContentKind.TEXT,
            ContentKind.LINK,
        }:
            item = replace(item, value=localize_value(locale, str(item.value)))
        component = _item_to_node_component(item, cross_session=cross_session)
        if component is not None and current is not None:
            current.content.append(component)
    close_node()
    if not nodes:
        return None
    return MessageChain([Nodes(nodes=nodes)]).use_markdown(False)


_FORWARD_CARD_MAX_NAME_UTF16 = 80
_FORWARD_CARD_MAX_BODY_UTF16 = 1200


def _truncate_utf16(text: str, limit: int) -> str:
    """Bound text by UTF-16 code units, appending an ellipsis when cut."""
    if limit <= 0:
        return ""
    units = 0
    for index, char in enumerate(text):
        units += 2 if ord(char) > 0xFFFF else 1
        if units > limit:
            return f"{text[:index]}…"
    return text


def _normalize_card_text(text: str) -> str:
    """Collapse whitespace so each card row stays on one visual line."""
    return " ".join(text.split())


def _forward_card_item_text(
    item: PortablePart | NativeContent,
    *,
    locale: str,
) -> str:
    """Render one forwarded item as text for the image card."""
    if isinstance(item, NativeContent):
        return localize_value(locale, item.fallback or f"[{item.kind}]")
    if item.kind in {ContentKind.TEXT, ContentKind.LINK}:
        return localize_value(locale, str(item.value))
    if item.kind == ContentKind.MENTION:
        data = item.value if isinstance(item.value, Mapping) else {}
        label = str(data.get("name") or data.get("id") or "")
        return f"@{label}" if label else "@"
    if item.kind == ContentKind.MENTION_ALL:
        return "@all"
    return item.alt_text or localize_kind(locale, item.kind.value)


def _forward_card_image_uri(item: PortablePart | NativeContent) -> str | None:
    """Return the local file URI of a materialized image, else ``None``.

    Only ``file://`` references are inlined so no remote resource can be
    introduced into the rendered card.
    """
    if not isinstance(item, PortablePart) or item.kind != ContentKind.IMAGE:
        return None
    value = item.value
    if not isinstance(value, MediaReference):
        return None
    return value.uri if value.uri.startswith("file://") else None


def build_forward_card_rows(
    content: Sequence[PortablePart | NativeContent],
    *,
    locale: str = DEFAULT_LOCALE,
) -> list[dict[str, object]]:
    """Group sender-stamped items into ``sender`` / ``body`` card rows.

    Only the forward islands (items carrying a :class:`SenderSnapshot`) become
    rows, so the source header and any ordinary parts are ignored. Each row
    records its merged-forward nesting level so nested content can be indented.
    """
    rows: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    def open_row(sender: SenderSnapshot, level: int) -> None:
        nonlocal current
        uin, name = _node_identity(sender, locale)
        current = {
            "name": _truncate_utf16(name, _FORWARD_CARD_MAX_NAME_UTF16),
            "uin": uin,
            "text": "",
            "depth": max(0, level - 1),
        }
        rows.append(current)

    for item in content:
        sender = _item_sender(item)
        if _is_author_separator(item, locale):
            if sender is not None:
                open_row(sender, item.depth)
            continue
        if sender is None:
            continue
        if current is None or current["uin"] != (sender.id or "0"):
            open_row(sender, item.depth)
        image_uri = _forward_card_image_uri(item)
        if image_uri is not None:
            images = current.setdefault("images", [])
            if isinstance(images, list):
                images.append(image_uri)
            continue
        text = _normalize_card_text(_forward_card_item_text(item, locale=locale))
        if not text:
            continue
        if current["text"]:
            current["text"] = f"{current['text']} {text}"
        else:
            current["text"] = text
    return [
        {
            **row,
            "text": _truncate_utf16(str(row["text"]), _FORWARD_CARD_MAX_BODY_UTF16),
        }
        for row in rows
        if row["text"] or row.get("images")
    ]


def _with_quote(
    chain: MessageChain,
    quote: QuoteReference | None,
    *,
    capabilities: MessageDeliveryCapabilities,
    quote_id: str | None,
    locale: str = DEFAULT_LOCALE,
) -> MessageChain:
    if quote is None:
        return chain
    if capabilities.quote and quote_id:
        return MessageChain([Reply(id=quote_id), *chain.chain]).use_markdown(False)
    preview = quote.preview or localize(locale, message_key("quote"))
    return MessageChain([Plain(f"> {preview}\n"), *chain.chain]).use_markdown(False)


def _deliver_island(
    items: Sequence[PortablePart | NativeContent],
    *,
    envelope: MessageEnvelope,
    capabilities: MessageDeliveryCapabilities,
    quote_id: str | None,
    locale: str,
    cross_session: bool,
    has_sender: bool,
) -> tuple[MessageChain, ...]:
    sub_envelope = replace(envelope, content=tuple(items))
    if not has_sender:
        return _plan_flat(sub_envelope, capabilities, quote_id=quote_id, locale=locale)
    reconstructed = _reconstruct_forward_chain(
        items, locale=locale, cross_session=cross_session
    )
    if reconstructed is None:
        return _plan_flat(sub_envelope, capabilities, quote_id=quote_id, locale=locale)
    return (
        _with_quote(
            reconstructed,
            sub_envelope.quote,
            capabilities=capabilities,
            quote_id=quote_id,
            locale=locale,
        ),
    )


def batch_to_message_chain(
    batch: DeliveryBatch,
    *,
    capabilities: MessageDeliveryCapabilities,
    quote_id: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> MessageChain:
    """Convert one planned batch into a chain for the target adapter."""
    components: list[BaseMessageComponent] = []
    if batch.quote is not None:
        if capabilities.quote and quote_id:
            components.append(Reply(id=quote_id))
        else:
            preview = batch.quote.preview or localize(locale, message_key("quote"))
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
        preview = envelope.quote.preview or localize(locale, message_key("quote"))
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
        chains.extend(
            _deliver_island(
                items,
                envelope=replace(
                    envelope,
                    quote=remaining_quote if first else None,
                ),
                capabilities=root_capabilities,
                quote_id=remaining_quote_id if first else None,
                locale=locale,
                cross_session=cross_session,
                has_sender=has_sender,
            )
        )
        first = False
        remaining_quote = None
        remaining_quote_id = None
    return tuple(chains)


def iter_delivery_parts(batches: Iterable[DeliveryBatch]) -> Iterable[PortablePart]:
    """Iterate portable parts in transport order for diagnostics."""
    for batch in batches:
        yield from batch.parts


__all__ = [
    "batch_to_message_chain",
    "build_forward_card_rows",
    "iter_delivery_parts",
    "plan_message_delivery",
]
