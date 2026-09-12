"""Project AstrBot events into the portable message protocol."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from astrbot.core.message.components import (
    BaseMessageComponent,
    Contact,
    File,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    Mention,
    MentionAll,
    MiniApp,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    Video,
    Xml,
)

from .message_i18n import kind_key, message_key
from .message_protocol import (
    ContentKind,
    MediaReference,
    MessageEnvelope,
    NativeContent,
    PortablePart,
    QuoteReference,
    SenderSnapshot,
)

if TYPE_CHECKING:
    from .astr_message_event import AstrMessageEvent


def _media_reference(component: Image | Record | Video | File) -> MediaReference:
    """Capture a media source without resolving or mutating it."""
    snapshot = component.model_copy()

    async def resolve_source() -> str:
        if isinstance(snapshot, File):
            return await snapshot.get_file(allow_return_url=True)
        await snapshot._resolve_deferred_source()
        return str(snapshot.url or snapshot.file or snapshot.path or "")

    uri = str(
        getattr(component, "url", None)
        or getattr(component, "file", None)
        or getattr(component, "path", None)
        or ""
    )
    return MediaReference(
        uri=uri,
        mime_type=getattr(component, "mime_type", None),
        file_name=getattr(component, "name", None),
        resolve_source=resolve_source,
    )


def _project_component(
    component: BaseMessageComponent,
    *,
    namespace: str,
) -> tuple[PortablePart | None, NativeContent | None]:
    """Project one component, retaining native data with a readable fallback."""
    if isinstance(component, Plain):
        return PortablePart(ContentKind.TEXT, component.text), None
    if isinstance(component, Image):
        return PortablePart(
            ContentKind.IMAGE,
            _media_reference(component),
            kind_key(ContentKind.IMAGE.value),
        ), None
    if isinstance(component, Record):
        return PortablePart(
            ContentKind.AUDIO,
            _media_reference(component),
            kind_key(ContentKind.AUDIO.value),
        ), None
    if isinstance(component, Video):
        return PortablePart(
            ContentKind.VIDEO,
            _media_reference(component),
            kind_key(ContentKind.VIDEO.value),
        ), None
    if isinstance(component, File):
        return PortablePart(
            ContentKind.FILE,
            _media_reference(component),
            kind_key(ContentKind.FILE.value),
        ), None
    if isinstance(component, Mention):
        return PortablePart(
            ContentKind.MENTION,
            {"id": str(component.target), "name": component.name or ""},
            f"@{component.name or component.target}",
        ), None
    if isinstance(component, MentionAll):
        return PortablePart(ContentKind.MENTION_ALL, {"id": "all"}, "@all"), None
    if isinstance(component, Location):
        return PortablePart(
            ContentKind.LOCATION,
            {
                "lat": component.lat,
                "lon": component.lon,
                "title": component.title or "",
            },
            kind_key(ContentKind.LOCATION.value),
        ), None
    if isinstance(component, Contact):
        return PortablePart(
            ContentKind.CONTACT,
            {"type": component.sub_type, "id": str(component.id or "")},
            kind_key(ContentKind.CONTACT.value),
        ), None
    if isinstance(component, (Markdown, MiniApp, Json, Xml)):
        kind = component.type.value.lower()
        return None, NativeContent(
            namespace=namespace,
            kind=kind,
            payload=component.model_dump_json(),
            fallback=str(component.content)
            if isinstance(component, Markdown)
            else f"[{kind}]",
        )
    return None, NativeContent(
        namespace=namespace,
        kind=component.type.value.lower(),
        payload=component.model_dump_json(),
        fallback=f"[{component.type.value}]",
    )


def _expand_forwarded_content(
    components: Iterable[BaseMessageComponent],
    depth: int = 0,
    sender: SenderSnapshot | None = None,
) -> Iterator[tuple[BaseMessageComponent, SenderSnapshot | None]]:
    """Flatten forwarded transcripts while retaining their media and authors."""
    if depth >= 8:
        yield Plain(message_key("forward_limit")), sender
        return
    for component in components:
        if isinstance(component, Nodes):
            yield from _expand_forwarded_content(component.nodes, depth + 1, sender)
        elif isinstance(component, Node):
            node_sender = SenderSnapshot(
                id=str(component.uin or ""), name=component.name or ""
            )
            author = component.name or component.uin
            yield (
                Plain(f"[{author}]\n" if author else message_key("unknown_author")),
                node_sender,
            )
            yield from _expand_forwarded_content(
                component.content, depth + 1, node_sender
            )
        elif isinstance(component, Forward) and component.content:
            yield from _expand_forwarded_content(component.content, depth + 1, sender)
        elif isinstance(component, Reply) and depth:
            yield (
                Plain(f"> {component.message_str or component.text or component.id}\n"),
                sender,
            )
        else:
            yield component, sender


def envelope_from_event(event: AstrMessageEvent) -> MessageEnvelope:
    """Create an immutable portable snapshot from a normalized platform event."""
    content: list[PortablePart | NativeContent] = []
    quote: QuoteReference | None = None
    for index, (component, forwarded_sender) in enumerate(
        _expand_forwarded_content(event.get_messages())
    ):
        if index >= 1024:
            content.append(PortablePart(ContentKind.TEXT, message_key("content_limit")))
            break
        if isinstance(component, Reply):
            quote = QuoteReference(
                source_route=event.route_identity,
                message_id=str(component.id),
                sender=SenderSnapshot(
                    id=str(component.sender_id or ""),
                    name=component.sender_nickname or "",
                    platform=event.get_platform_name(),
                ),
                preview=component.message_str or component.text or "",
            )
            continue
        part, native_component = _project_component(
            component,
            namespace=event.get_platform_name(),
        )
        if part is not None:
            if forwarded_sender is not None:
                part = replace(part, sender=forwarded_sender)
            content.append(part)
        if native_component is not None:
            content.append(native_component)

    sender = SenderSnapshot(
        id=str(event.get_sender_id()),
        name=event.get_sender_name() or "",
        platform=event.get_platform_name(),
    )
    message_obj = getattr(event, "message_obj", None)
    source_message_id = getattr(message_obj, "message_id", None)
    if source_message_id is None:
        source_message_id = getattr(message_obj, "id", None)
    return MessageEnvelope(
        source_route=event.route_identity,
        content=tuple(content),
        source_umo=event.unified_msg_origin,
        is_self_message=bool(event.get_self_id())
        and str(event.get_sender_id()) == str(event.get_self_id()),
        sender=sender,
        source_message_id=str(source_message_id) if source_message_id else None,
        quote=quote,
        created_at=event.created_at,
        metadata={"platform_name": event.get_platform_name()},
    )


def envelope_from_send_event(
    event: AstrMessageEvent, target_umo: str
) -> MessageEnvelope:
    """Remove only the command header, preserving the body and attachment order.

    Command text may span multiple Plain components. The bound target must match
    the header; a mismatch fails closed rather than forwarding command text.
    """
    envelope = envelope_from_event(event)
    text = "".join(
        str(part.value)
        for part in envelope.content
        if isinstance(part, PortablePart) and part.kind == ContentKind.TEXT
    )
    match = re.match(r"""^\s*\S+\s+("[^"]+"|'[^']+'|\S+)[ \t]*""", text)
    if match is None or match.group(1).strip("\"'") != target_umo:
        raise ValueError("Cannot locate the send command header")
    remaining = match.end()
    content: list[PortablePart | NativeContent] = []
    for part in envelope.content:
        if (
            isinstance(part, PortablePart)
            and part.kind == ContentKind.TEXT
            and remaining
        ):
            value = str(part.value)
            trimmed = value[remaining:]
            remaining = max(0, remaining - len(value))
            if trimmed:
                content.append(replace(part, value=trimmed))
        elif (
            remaining
            and isinstance(part, PortablePart)
            and part.kind == ContentKind.MENTION
            and isinstance(part.value, Mapping)
            and part.value.get("id") == str(event.get_self_id())
        ):
            continue
        else:
            content.append(part)
    return replace(envelope, content=tuple(content))


__all__ = ["envelope_from_event", "envelope_from_send_event"]
