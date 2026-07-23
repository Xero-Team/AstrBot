"""Shared reduction of WebChat queue results into durable bot messages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ATTACHMENT_MARKERS = {
    "image": "[IMAGE]",
    "record": "[RECORD]",
    "file": "[FILE]",
    "video": "[VIDEO]",
}


def collect_plain_text_from_message_parts(message_parts: list[dict]) -> str:
    """Collect plain text from persisted WebChat message parts."""
    return "".join(
        text
        for part in message_parts
        if part.get("type") == "plain"
        and isinstance(text := part.get("text"), str)
        and text
    )


def normalize_reasoning_message_parts(
    message_parts: list[dict] | None,
    reasoning: str = "",
) -> list[dict]:
    """Normalize persisted reasoning parts to the WebChat storage shape."""
    parts: list[dict] = []
    for part in message_parts or []:
        if not isinstance(part, dict):
            continue
        copied = dict(part)
        if copied.get("type") == "reasoning":
            copied = {"type": "think", "think": copied.get("text", "")}
        parts.append(copied)
    if reasoning and not any(part.get("type") == "think" for part in parts):
        parts.insert(0, {"type": "think", "think": reasoning})
    return parts


def extract_reasoning_from_message_parts(message_parts: list[dict]) -> str:
    """Collect persisted reasoning text in transport order."""
    reasoning_parts: list[str] = []
    for part in message_parts:
        if part.get("type") != "think":
            continue
        think = part.get("think")
        if isinstance(think, str) and think:
            reasoning_parts.append(think)
    return "".join(reasoning_parts)


def build_bot_history_content(
    message_parts: list[dict],
    *,
    agent_stats: dict | None = None,
    refs: dict | None = None,
    include_reasoning_field: bool = True,
) -> dict[str, Any]:
    """Build the durable WebChat bot-history payload from queue results."""
    normalized_parts = normalize_reasoning_message_parts(message_parts)
    content: dict[str, Any] = {"type": "bot", "message": normalized_parts}
    reasoning = extract_reasoning_from_message_parts(normalized_parts)
    if reasoning and include_reasoning_field:
        content["reasoning"] = reasoning
    if agent_stats:
        content["agent_stats"] = agent_stats
    if refs:
        content["refs"] = refs
    return content


class BotMessageAccumulator:
    """Build persisted WebChat message parts while preserving tool-call order."""

    def __init__(self) -> None:
        self.parts: list[dict] = []
        self.pending_text = ""
        self.pending_tool_calls: dict[str, dict] = {}

    def has_content(self) -> bool:
        return bool(self.parts or self.pending_text or self.pending_tool_calls)

    def add_plain(
        self, result_text: str, *, chain_type: str | None, streaming: bool
    ) -> None:
        if chain_type == "tool_call":
            self._flush_pending_text()
            self._store_tool_call(result_text)
        elif chain_type == "tool_call_result":
            self._flush_pending_text()
            self._store_tool_call_result(result_text)
        elif chain_type == "reasoning":
            self._flush_pending_text()
            self._append_think_part(result_text)
        elif streaming:
            self.pending_text += result_text
        else:
            self.pending_text = result_text

    def add_attachment(self, part: dict | None) -> None:
        if part:
            self._flush_pending_text()
            self.parts.append(part)

    def build_message_parts(
        self, *, include_pending_tool_calls: bool = False
    ) -> list[dict]:
        self._flush_pending_text()
        if include_pending_tool_calls and self.pending_tool_calls:
            self.parts.extend(
                {"type": "tool_call", "tool_calls": [tool_call]}
                for tool_call in self.pending_tool_calls.values()
            )
            self.pending_tool_calls = {}
        return self.parts

    def plain_text(self) -> str:
        return collect_plain_text_from_message_parts(self.build_message_parts())

    def reasoning_text(self) -> str:
        return "".join(
            str(part.get("think") or "")
            for part in self.build_message_parts()
            if part.get("type") == "think"
        )

    def _flush_pending_text(self) -> None:
        if not self.pending_text:
            return
        if self.parts and self.parts[-1].get("type") == "plain":
            self.parts[-1]["text"] = (
                f"{self.parts[-1].get('text') or ''}{self.pending_text}"
            )
        else:
            self.parts.append({"type": "plain", "text": self.pending_text})
        self.pending_text = ""

    def _append_think_part(self, text: str) -> None:
        if not text:
            return
        if self.parts and self.parts[-1].get("type") == "think":
            self.parts[-1]["think"] = f"{self.parts[-1].get('think') or ''}{text}"
        else:
            self.parts.append({"type": "think", "think": text})

    def _store_tool_call(self, result_text: str) -> None:
        tool_call = self._parse_json_object(result_text)
        if tool_call and (tool_call_id := str(tool_call.get("id") or "")):
            self.pending_tool_calls[tool_call_id] = tool_call

    def _store_tool_call_result(self, result_text: str) -> None:
        tool_result = self._parse_json_object(result_text)
        if not tool_result or not (tool_call_id := str(tool_result.get("id") or "")):
            return
        tool_call = self.pending_tool_calls.pop(tool_call_id, None) or {
            "id": tool_call_id
        }
        tool_call["result"] = tool_result.get("result")
        tool_call["finished_ts"] = tool_result.get("ts")
        self.parts.append({"type": "tool_call", "tool_calls": [tool_call]})

    @staticmethod
    def _parse_json_object(raw_text: str) -> dict | None:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def merge_webchat_refs(extracted_refs: dict, native_refs: dict) -> dict:
    """Merge native LLM sources with tool-derived refs, deduplicated by URL."""
    merged = dict(extracted_refs) if isinstance(extracted_refs, dict) else {}
    used = [item for item in merged.get("used", []) if isinstance(item, dict)]
    urls = {item.get("url") for item in used if item.get("url")}
    for item in native_refs.get("used", []) if isinstance(native_refs, dict) else []:
        if not isinstance(item, dict) or not item.get("url") or item["url"] in urls:
            continue
        used.append(item)
        urls.add(item["url"])
    if used:
        merged["used"] = used
    return merged


def parse_webchat_attachment(
    result_type: str | None, data: object
) -> tuple[str, str, str | None] | None:
    """Parse a queued attachment event consistently for all WebChat consumers."""
    marker = ATTACHMENT_MARKERS.get(result_type or "")
    if marker is None or result_type is None:
        return None
    filename = str(data).replace(marker, "", 1)
    display_name = None
    if result_type in {"file", "video"} and "|" in filename:
        filename, display_name = filename.split("|", 1)
    return filename, result_type, display_name


@dataclass
class WebChatResultReducer:
    """Own the durable state common to all WebChat queue consumers."""

    accumulator: BotMessageAccumulator = field(default_factory=BotMessageAccumulator)
    agent_stats: dict = field(default_factory=dict)
    native_refs: dict = field(default_factory=dict)

    def consume_metadata(self, result: dict) -> str | None:
        """Store metadata and return its semantic kind, if the result is metadata."""
        chain_type = result.get("chain_type")
        if chain_type == "agent_stats":
            try:
                parsed = json.loads(result.get("data", ""))
            except TypeError, json.JSONDecodeError:
                self.agent_stats = {}
            else:
                self.agent_stats = parsed if isinstance(parsed, dict) else {}
            return "agent_stats"
        if result.get("type") == "refs":
            data = result.get("data")
            if isinstance(data, dict):
                self.native_refs = merge_webchat_refs(self.native_refs, data)
            return "refs"
        return None

    def accumulate_plain(self, result: dict) -> None:
        self.accumulator.add_plain(
            str(result.get("data", "")),
            chain_type=result.get("chain_type"),
            streaming=bool(result.get("streaming", False)),
        )

    def should_flush(self, result: dict) -> bool:
        result_type = result.get("type")
        if result_type == "end":
            return bool(
                self.accumulator.has_content() or self.native_refs or self.agent_stats
            )
        return (bool(result.get("streaming")) and result_type == "complete") or (
            not result.get("streaming")
            and result.get("chain_type")
            not in {"tool_call", "tool_call_result", "agent_stats"}
        )

    def reset(self) -> None:
        self.accumulator = BotMessageAccumulator()
        self.agent_stats = {}
        self.native_refs = {}
