"""Platform-neutral message semantics and delivery planning.

Adapters own transport details.  This module owns the small set of semantics
that can be preserved when a message crosses platform boundaries.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .message_i18n import DEFAULT_LOCALE, kind_key, localize, localize_value
from .route_identity import PlatformRouteIdentity


class ContentKind(StrEnum):
    """Portable message content kinds."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    MENTION = "mention"
    MENTION_ALL = "mention_all"
    LINK = "link"
    LOCATION = "location"
    CONTACT = "contact"
    QUOTE = "quote"


@dataclass(frozen=True, slots=True)
class SenderSnapshot:
    """Sender identity captured at ingress time."""

    id: str
    name: str = ""
    platform: str = ""


@dataclass(frozen=True, slots=True)
class MediaReference:
    """A source-independent description of a media resource."""

    uri: str
    mime_type: str | None = None
    file_name: str | None = None
    size: int | None = None
    resolve_source: Callable[[], Awaitable[str]] | None = field(
        default=None, repr=False, compare=False
    )


@dataclass(frozen=True, slots=True)
class QuoteReference:
    """A quote whose identifier is scoped to its originating route."""

    source_route: PlatformRouteIdentity
    message_id: str
    sender: SenderSnapshot | None = None
    preview: str = ""


@dataclass(frozen=True, slots=True)
class PortablePart:
    """Portable semantic content.

    ``value`` is text for textual kinds, a :class:`MediaReference` for media,
    or a small mapping for identity-bearing content.  Adapter-specific data
    never belongs here.
    """

    kind: ContentKind
    value: str | MediaReference | Mapping[str, Any]
    alt_text: str = ""
    sender: SenderSnapshot | None = None

    def __post_init__(self) -> None:
        if isinstance(self.value, Mapping):
            object.__setattr__(self, "value", MappingProxyType(dict(self.value)))


@dataclass(frozen=True, slots=True)
class NativeContent:
    """Platform-native content with an explicit protocol namespace."""

    namespace: str
    kind: str
    payload: str
    fallback: str = ""


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Immutable ingress snapshot used by observers and bridges."""

    source_route: PlatformRouteIdentity
    content: tuple[PortablePart | NativeContent, ...] = ()
    source_umo: str = ""
    is_self_message: bool = False
    sender: SenderSnapshot | None = None
    source_message_id: str | None = None
    quote: QuoteReference | None = None
    created_at: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze metadata so observers cannot mutate the ingress snapshot."""
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        if not self.source_umo:
            object.__setattr__(self, "source_umo", self.source_route.as_origin())


@dataclass(frozen=True, slots=True)
class MessageDeliveryCapabilities:
    """Effective message capabilities of one loaded adapter instance."""

    text: bool = True
    formatting: frozenset[str] = frozenset()
    media: frozenset[str] = frozenset()
    mixed_parts: bool = False
    media_caption: bool = False
    album: bool = False
    quote: bool = False
    forward: bool = False
    mention: bool = False
    native_namespaces: frozenset[str] = frozenset()
    native_kinds: frozenset[str] = frozenset()
    max_text_length: int | None = None
    max_media_size: int | None = None
    max_parts_per_request: int | None = None
    public_media_urls: bool = False
    proactive: bool = True
    available: bool = True
    standalone_media: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class DeliveryBatch:
    """One ordered transport submission produced by a planner."""

    parts: tuple[PortablePart, ...] = ()
    native: tuple[NativeContent, ...] = ()
    relation: str | None = None
    quote: QuoteReference | None = None


def plan_delivery(
    envelope: MessageEnvelope,
    capabilities: MessageDeliveryCapabilities,
    *,
    locale: str = DEFAULT_LOCALE,
) -> tuple[DeliveryBatch, ...]:
    """Plan ordered requests within target text and component limits."""
    batches: list[DeliveryBatch] = []
    pending: list[PortablePart] = []
    text_units = 0
    media_kinds = {
        ContentKind.IMAGE,
        ContentKind.AUDIO,
        ContentKind.VIDEO,
        ContentKind.FILE,
    }
    limit = capabilities.max_text_length
    max_parts = capabilities.max_parts_per_request
    if (limit is not None and limit < 2) or (max_parts is not None and max_parts < 1):
        raise ValueError("Invalid target message limits")

    def flush() -> None:
        nonlocal text_units
        if pending:
            batches.append(
                DeliveryBatch(
                    parts=tuple(pending), quote=envelope.quote if not batches else None
                )
            )
            pending.clear()
            text_units = 0

    def append_text(text: str) -> None:
        nonlocal text_units
        # UTF-16 units are conservative for both code-point and UTF-16 limits.
        chunk: list[str] = []
        for char in text:
            units = 2 if ord(char) > 0xFFFF else 1
            if limit is not None and text_units + units > limit:
                if chunk:
                    pending.append(PortablePart(ContentKind.TEXT, "".join(chunk)))
                    chunk.clear()
                flush()
            chunk.append(char)
            text_units += units
        if chunk:
            value = "".join(chunk)
            # Adjacent text has one semantic meaning.  Keep it in one part so
            # renderers can produce one platform message instead of turning a
            # source header and body into separate transport submissions.
            if pending and pending[-1].kind == ContentKind.TEXT:
                previous = pending[-1]
                pending[-1] = replace(previous, value=str(previous.value) + value)
            else:
                pending.append(PortablePart(ContentKind.TEXT, value))

    for item in envelope.content:
        if max_parts is not None and len(pending) >= max_parts:
            flush()
        if isinstance(item, NativeContent):
            if (
                item.namespace in capabilities.native_namespaces
                and item.kind in capabilities.native_kinds
            ):
                flush()
                batches.append(
                    DeliveryBatch(
                        native=(item,),
                        relation="native",
                        quote=envelope.quote if not batches else None,
                    )
                )
            else:
                append_text(
                    localize_value(
                        locale, item.fallback or f"[{item.namespace}:{item.kind}]"
                    )
                )
            continue
        is_media = item.kind in media_kinds
        value = item.value
        if (
            is_media
            and item.kind.value not in capabilities.media
            and "file" in capabilities.media
        ):
            item = replace(item, kind=ContentKind.FILE)
        supported = is_media and item.kind.value in capabilities.media
        if (
            supported
            and isinstance(value, MediaReference)
            and capabilities.max_media_size is not None
            and value.size is not None
        ):
            supported = value.size <= capabilities.max_media_size
        if supported:
            standalone = (
                not capabilities.mixed_parts
                or item.kind.value in capabilities.standalone_media
            )
            if standalone:
                flush()
            pending.append(item)
            if standalone:
                flush()
        elif (
            item.kind in {ContentKind.MENTION, ContentKind.MENTION_ALL}
            and capabilities.mention
        ):
            pending.append(item)
        else:
            if item.kind in {ContentKind.TEXT, ContentKind.LINK}:
                text = localize_value(locale, str(value))
            elif item.alt_text:
                text = localize_value(locale, item.alt_text)
            else:
                text = localize(locale, kind_key(item.kind.value))
            if capabilities.text:
                append_text(text)
    flush()
    return tuple(batches)


__all__ = [
    "ContentKind",
    "DeliveryBatch",
    "MediaReference",
    "MessageDeliveryCapabilities",
    "MessageEnvelope",
    "NativeContent",
    "PortablePart",
    "QuoteReference",
    "SenderSnapshot",
    "plan_delivery",
]
