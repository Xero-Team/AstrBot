from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from astrbot.core.message.components import (
    RPS,
    At,
    AtAll,
    BaseMessageComponent,
    Contact,
    Dice,
    Face,
    File,
    FlashTransfer,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    MFace,
    MiniApp,
    Music,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Unknown,
    Video,
    Xml,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .quoted_message.chain_parser import OneBotPayloadParser
from .quoted_message.image_resolver import ImageResolver
from .quoted_message.onebot_client import OneBotClient
from .quoted_message.settings import SETTINGS, QuotedMessageParserSettings
from .string_utils import normalize_and_dedupe_strings

_MAX_RENDERED_VALUE_LENGTH = 4000


def _limited_text(value: object) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    if len(text) <= _MAX_RENDERED_VALUE_LENGTH:
        return text
    return f"{text[:_MAX_RENDERED_VALUE_LENGTH]}…[truncated]"


def _is_usable_media_ref(value: str) -> bool:
    return bool(
        value
        and (
            value.startswith(("http://", "https://", "file://", "base64://"))
            or "/" in value
            or "\\" in value
        )
    )


@dataclass(slots=True)
class MessageContextContent:
    text: str | None = None
    image_refs: list[str] = field(default_factory=list)
    nested_media: list[BaseMessageComponent] = field(default_factory=list)

    def extend(self, other: MessageContextContent) -> None:
        if other.text:
            self.text = "\n".join(part for part in (self.text, other.text) if part)
        self.image_refs.extend(other.image_refs)
        self.nested_media.extend(other.nested_media)


class MessageContextRenderer:
    """Render non-plain message components for an agent request."""

    def __init__(
        self,
        event: AstrMessageEvent,
        settings: QuotedMessageParserSettings = SETTINGS,
    ) -> None:
        self._event = event
        self._settings = settings
        self._client = OneBotClient(event, settings=settings)
        self._payload_parser = OneBotPayloadParser(settings=settings)
        self._image_resolver = ImageResolver(event, self._client)
        cache = getattr(event, "_forward_message_payload_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            setattr(event, "_forward_message_payload_cache", cache)
        self._forward_payload_cache: dict[str, dict[str, object] | None] = cache
        message_cache = getattr(event, "_message_component_payload_cache", None)
        if not isinstance(message_cache, dict):
            message_cache = {}
            setattr(event, "_message_component_payload_cache", message_cache)
        self._message_payload_cache: dict[str, dict[str, object] | None] = message_cache
        self._active_forward_ids: set[str] = set()
        self._forward_fetch_count = 0

    async def render_event_components(self) -> MessageContextContent:
        content = await self._render_components(
            self._event.message_obj.message,
            include_plain=False,
            depth=0,
        )
        content.image_refs = await self._image_resolver.resolve_for_llm(
            normalize_and_dedupe_strings(content.image_refs)
        )
        return content

    async def _render_forward(
        self,
        component: Forward,
        *,
        depth: int,
    ) -> MessageContextContent:
        if depth > self._settings.max_forward_node_depth:
            return MessageContextContent(text="[Forward depth limit reached]")

        if component.content:
            return await self._render_components(
                component.content,
                include_plain=True,
                depth=depth + 1,
            )

        forward_id = str(component.id).strip()
        if not forward_id:
            return MessageContextContent(text="[Empty Forward Message]")
        if forward_id in self._active_forward_ids:
            return MessageContextContent(text="[Cyclic Forward Message]")

        payload = self._forward_payload_cache.get(forward_id)
        if forward_id not in self._forward_payload_cache:
            if self._forward_fetch_count >= self._settings.max_forward_fetch:
                return MessageContextContent(text="[Forward fetch limit reached]")
            self._forward_fetch_count += 1
            payload = await self._client.get_forward_msg(forward_id)
            self._forward_payload_cache[forward_id] = payload
        if not payload:
            return MessageContextContent(text="[Unavailable Forward Message]")

        self._active_forward_ids.add(forward_id)
        try:
            parsed = self._payload_parser.parse_get_forward_payload(payload)
            content = MessageContextContent(
                text=parsed["text"],
                image_refs=list(parsed["image_refs"]),
                nested_media=self._collect_forward_media(payload),
            )
            for nested_id in parsed["forward_ids"]:
                nested = await self._render_forward(
                    Forward(id=nested_id),
                    depth=depth + 1,
                )
                content.extend(nested)
            return content
        finally:
            self._active_forward_ids.discard(forward_id)

    async def _render_existing_node(
        self,
        component: Node,
        *,
        depth: int,
    ) -> MessageContextContent:
        node_id = str(component.id or "").strip()
        if not node_id or node_id == "0":
            return MessageContextContent()
        payload = self._message_payload_cache.get(node_id)
        if node_id not in self._message_payload_cache:
            if self._forward_fetch_count >= self._settings.max_forward_fetch:
                return MessageContextContent(text="[Message fetch limit reached]")
            self._forward_fetch_count += 1
            payload = await self._client.get_msg(node_id)
            self._message_payload_cache[node_id] = payload
        if not payload:
            return MessageContextContent()

        parsed = self._payload_parser.parse_get_msg_payload(payload)
        payload_data = payload.get("data")
        message_data = payload_data if isinstance(payload_data, Mapping) else payload
        raw_segments = message_data.get("message") or message_data.get("messages") or []
        nested_media = (
            self._collect_forward_media(
                {"messages": [{"message": raw_segments}]},
                depth=depth,
            )
            if isinstance(raw_segments, list)
            else []
        )
        content = MessageContextContent(
            text=parsed["text"],
            image_refs=list(parsed["image_refs"]),
            nested_media=nested_media,
        )
        for nested_id in parsed["forward_ids"]:
            content.extend(
                await self._render_forward(
                    Forward(id=nested_id),
                    depth=depth + 1,
                )
            )
        return content

    def _collect_forward_media(
        self,
        payload: Mapping[str, object],
        *,
        depth: int = 0,
    ) -> list[BaseMessageComponent]:
        if depth > self._settings.max_forward_node_depth:
            return []

        data = payload.get("data")
        payload_data = data if isinstance(data, Mapping) else payload
        raw_nodes = (
            payload_data.get("messages")
            or payload_data.get("message")
            or payload_data.get("nodes")
            or []
        )
        if not isinstance(raw_nodes, list):
            return []

        media: list[BaseMessageComponent] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, Mapping):
                continue
            if raw_node.get("type") == "node":
                node_data = raw_node.get("data")
                if not isinstance(node_data, Mapping):
                    continue
                raw_chain = node_data.get("content") or node_data.get("message") or []
            else:
                raw_chain = raw_node.get("message") or raw_node.get("content") or []
            if not isinstance(raw_chain, list):
                continue

            for raw_segment in raw_chain:
                if not isinstance(raw_segment, Mapping):
                    continue
                segment_type = raw_segment.get("type")
                raw_data = raw_segment.get("data")
                segment_data = raw_data if isinstance(raw_data, Mapping) else {}
                file_ref = segment_data.get("file")
                url_ref = segment_data.get("url")
                path_ref = segment_data.get("path")
                file_text = str(file_ref) if file_ref is not None else ""
                url_text = str(url_ref) if url_ref is not None else ""
                path_text = str(path_ref) if path_ref is not None else ""

                if segment_type in {"record", "voice"} and (
                    url_text or path_text or _is_usable_media_ref(file_text)
                ):
                    media.append(
                        Record(
                            file=file_text or url_text or path_text,
                            url=url_text,
                            path=path_text or None,
                        )
                    )
                elif segment_type == "video" and (file_text or url_text):
                    media.append(Video(file=file_text or url_text, url=url_text))
                elif segment_type == "file" and (url_text or path_text):
                    name = (
                        segment_data.get("name")
                        or segment_data.get("file_name")
                        or file_text
                        or "file"
                    )
                    media.append(
                        File(
                            name=str(name),
                            file=path_text or file_text or url_text,
                            url=url_text,
                        )
                    )
                elif segment_type in {"forward", "forward_msg", "nodes"}:
                    nested_content = segment_data.get("content")
                    if isinstance(nested_content, list) and nested_content:
                        media.extend(
                            self._collect_forward_media(
                                {"messages": nested_content},
                                depth=depth + 1,
                            )
                        )
                elif segment_type == "node":
                    media.extend(
                        self._collect_forward_media(
                            {"messages": [raw_segment]},
                            depth=depth + 1,
                        )
                    )
        return media

    async def _render_components(
        self,
        components: list[BaseMessageComponent],
        *,
        include_plain: bool,
        depth: int,
    ) -> MessageContextContent:
        if depth > self._settings.max_component_chain_depth:
            return MessageContextContent(text="[Message component depth limit reached]")

        text_parts: list[str] = []
        result = MessageContextContent()
        for component in components:
            text = ""
            if isinstance(component, Plain):
                if include_plain:
                    text = component.text
            elif isinstance(component, At):
                if include_plain:
                    text = f"@{component.name or component.qq}"
            elif isinstance(component, AtAll):
                if include_plain:
                    text = "@all"
            elif isinstance(component, Image):
                if depth > 0:
                    text = "[Image]"
                    result.nested_media.append(component)
            elif isinstance(component, Record):
                if depth > 0:
                    text = "[Audio]"
                    result.nested_media.append(component)
            elif isinstance(component, Video):
                if depth > 0:
                    text = "[Video]"
                    result.nested_media.append(component)
            elif isinstance(component, File):
                if depth > 0:
                    text = f"[File: {component.name or 'file'}]"
                    result.nested_media.append(component)
            elif isinstance(component, Forward):
                nested = await self._render_forward(component, depth=depth)
                result.image_refs.extend(nested.image_refs)
                result.nested_media.extend(nested.nested_media)
                if nested.text:
                    text = f"<Forwarded Message>\n{nested.text}\n</Forwarded Message>"
            elif isinstance(component, Node):
                if component.content:
                    nested = await self._render_components(
                        component.content,
                        include_plain=True,
                        depth=depth + 1,
                    )
                else:
                    nested = await self._render_existing_node(
                        component,
                        depth=depth,
                    )
                result.image_refs.extend(nested.image_refs)
                result.nested_media.extend(nested.nested_media)
                sender = component.name or component.uin or "Unknown User"
                preview = ""
                if component.news:
                    preview = "\n".join(
                        str(item.get("text") or "")
                        for item in component.news
                        if item.get("text")
                    )
                node_text = (
                    nested.text
                    or component.summary
                    or component.prompt
                    or preview
                    or component.source
                    or "[Empty Node]"
                )
                text = f"{sender}: {node_text}"
            elif isinstance(component, Nodes):
                nested = await self._render_components(
                    [*component.nodes],
                    include_plain=True,
                    depth=depth + 1,
                )
                result.image_refs.extend(nested.image_refs)
                result.nested_media.extend(nested.nested_media)
                text = nested.text or "[Empty Forward Nodes]"
            elif isinstance(component, Json):
                text = f"[JSON]\n{_limited_text(component.data)}"
            elif isinstance(component, Xml):
                text = f"[XML]\n{_limited_text(component.data)}"
            elif isinstance(component, Markdown):
                text = f"[Markdown]\n{_limited_text(component.content)}"
            elif isinstance(component, MiniApp):
                text = f"[MiniApp]\n{_limited_text(component.data)}"
            elif isinstance(component, Music):
                text = (
                    f"[Music: {component.title or component.sub_type or component.id}]"
                )
            elif isinstance(component, Contact):
                text = f"[Contact: {component.sub_type} {component.id}]"
            elif isinstance(component, Location):
                text = (
                    f"[Location: {component.title or ''} "
                    f"({component.lat}, {component.lon}) {component.content or ''}]"
                )
            elif isinstance(component, Share):
                text = f"[Share: {component.title} {component.url}]"
            elif isinstance(component, MFace):
                text = component.summary or "[Market Face]"
            elif isinstance(component, Face):
                text = f"[Face: {component.id}]"
            elif isinstance(component, Poke):
                text = f"[Poke: {component.id}]"
            elif isinstance(component, Dice):
                text = "[Dice]"
            elif isinstance(component, RPS):
                text = "[Rock Paper Scissors]"
            elif isinstance(component, Shake):
                text = "[Window Shake]"
            elif isinstance(component, OnlineFile):
                text = f"[Online File: {component.file_name}]"
            elif isinstance(component, FlashTransfer):
                text = f"[Flash Transfer: {component.file_set_id}]"
            elif isinstance(component, Reply):
                if include_plain:
                    text = component.message_str or "[Quoted Message]"
            elif isinstance(component, Unknown):
                text = component.text or f"[Unsupported: {component.segment_type}]"

            if text:
                text_parts.append(text)

        if text_parts:
            rendered = "\n".join(text_parts)
            result.text = "\n".join(part for part in (result.text, rendered) if part)
        return result
