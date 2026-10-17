"""Normalize coding-agent JSON streams and persist one run's visibility.

The delegated CLIs do not share an event protocol.  Claude Code emits its own
``stream-json`` messages, Codex emits ``item.*`` events, and OpenCode emits
message/part events.  The rest of AstrBot should not need to know any of that:
each adapter turns one CLI line into zero or more :class:`CodingAgentEvent`
objects, and one observer writes those objects to the task folder and forwards
them to Trace and the work-session progress record.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from astrbot import logger
from astrbot.core.log import sanitize_log_payload
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error

EVENTS_LOG_NAME = "events.jsonl"
RUN_SUMMARY_NAME = "run.json"
MAX_SUMMARY_CHARS = 240
MAX_EVENT_DETAIL_CHARS = 4000

EventCallback = Callable[["CodingAgentEvent"], Awaitable[None]]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _bounded(text: object, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[{len(value) - limit} characters truncated]"


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _json_payload(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return ""


def _first_nonempty(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _tool_path(tool: str, payload: Mapping[str, Any]) -> str:
    direct = _first_nonempty(payload, "file_path", "filePath", "path", "filename")
    if direct:
        return direct
    # OpenCode wraps tool input under ``state.input``; the caller passes that
    # mapping here, but keeping the lookup tolerant costs nothing.
    nested = payload.get("input")
    if isinstance(nested, Mapping):
        return _first_nonempty(nested, "file_path", "filePath", "path", "filename")
    return ""


def _tool_command(tool: str, payload: Mapping[str, Any]) -> str:
    return _first_nonempty(
        payload,
        "command",
        "cmd",
        "query",
        "pattern",
        "url",
        "description",
    )


def _tool_summary(tool: str, payload: Mapping[str, Any]) -> str:
    command = _tool_command(tool, payload)
    path = _tool_path(tool, payload)
    detail = command or path
    if detail:
        return _bounded(f"{tool}: {detail}", MAX_SUMMARY_CHARS)
    return _bounded(tool or "tool call", MAX_SUMMARY_CHARS)


def _tool_detail(payload: Mapping[str, Any]) -> str:
    try:
        return _bounded(json.dumps(payload, ensure_ascii=False), MAX_EVENT_DETAIL_CHARS)
    except TypeError, ValueError:
        return _bounded(payload, MAX_EVENT_DETAIL_CHARS)


def _file_paths(tool: str, payload: Mapping[str, Any]) -> list[str]:
    normalized = tool.casefold()
    if not any(
        marker in normalized
        for marker in ("write", "edit", "patch", "notebook", "file_change")
    ):
        return []
    path = _tool_path(tool, payload)
    return [path] if path else []


@dataclass(slots=True)
class CodingAgentEvent:
    """One normalized event from a delegated coding-agent run."""

    type: str
    summary: str
    detail: str = ""
    tool: str = ""
    call_id: str = ""
    status: str = ""
    paths: list[str] = field(default_factory=list)
    usage: dict[str, int | float] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "timestamp": self.timestamp,
            "summary": _bounded(self.summary, MAX_SUMMARY_CHARS),
        }
        if self.detail:
            payload["detail"] = _bounded(self.detail, MAX_EVENT_DETAIL_CHARS)
        if self.tool:
            payload["tool"] = self.tool
        if self.call_id:
            payload["call_id"] = self.call_id
        if self.status:
            payload["status"] = self.status
        if self.paths:
            payload["paths"] = list(self.paths)
        if self.usage:
            payload["usage"] = dict(self.usage)
        return payload


class CodingStreamAdapter:
    """Base adapter for one CLI's line-oriented JSON stream."""

    def __init__(self) -> None:
        self._last_text = ""
        self._texts: list[tuple[str, str]] = []
        self.usage: dict[str, int | float] = {}

    @property
    def final_text(self) -> str:
        return self._last_text.strip()

    def _remember_text(self, text: object, *, message_id: str = "") -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        if message_id and self._texts and self._texts[-1][0] == message_id:
            previous = self._texts[-1][1]
            # A stream may repeat or grow the same text part.  Replacing the
            # previous part keeps a growing message from being duplicated.
            if value == previous or value.startswith(previous):
                self._texts[-1] = (message_id, value)
                self._last_text = value
                return value
        self._texts.append((message_id, value))
        self._last_text = value
        return value

    def feed(self, line: str) -> list[CodingAgentEvent]: ...

    def _merge_usage(self, usage: Mapping[str, Any]) -> None:
        for key, value in usage.items():
            number = _float(value)
            if number is None:
                continue
            self.usage[key] = int(number) if number.is_integer() else number


class ClaudeStreamAdapter(CodingStreamAdapter):
    """Adapter for Claude Code ``--output-format stream-json``."""

    def feed(self, line: str) -> list[CodingAgentEvent]:
        payload = _json_payload(line)
        if payload is None:
            return []
        event_type = str(payload.get("type", ""))
        events: list[CodingAgentEvent] = []

        if event_type == "system":
            subtype = str(payload.get("subtype", ""))
            if subtype:
                events.append(
                    CodingAgentEvent(
                        type="lifecycle",
                        summary=_bounded(f"Claude Code: {subtype}", MAX_SUMMARY_CHARS),
                        status=subtype,
                    )
                )
            return events

        if event_type == "assistant":
            message = payload.get("message")
            if not isinstance(message, Mapping):
                return events
            usage = message.get("usage")
            if isinstance(usage, Mapping):
                self._merge_usage(usage)
                events.append(
                    CodingAgentEvent(
                        type="usage",
                        summary="Claude Code token usage",
                        usage={str(k): v for k, v in self.usage.items()},
                    )
                )
            content = message.get("content")
            for part in content if isinstance(content, list) else []:
                if not isinstance(part, Mapping):
                    continue
                part_type = str(part.get("type", ""))
                if part_type == "text":
                    text = self._remember_text(part.get("text"))
                    if text:
                        events.append(
                            CodingAgentEvent(
                                type="message",
                                summary=_bounded(text, MAX_SUMMARY_CHARS),
                                detail=text,
                            )
                        )
                elif part_type in {"thinking", "reasoning"}:
                    text = str(part.get("thinking") or part.get("text") or "").strip()
                    if text:
                        events.append(
                            CodingAgentEvent(
                                type="reasoning",
                                summary=_bounded(text, MAX_SUMMARY_CHARS),
                                detail=text,
                            )
                        )
                elif part_type == "tool_use":
                    tool = str(part.get("name", "tool"))
                    tool_input = part.get("input")
                    input_payload = (
                        tool_input if isinstance(tool_input, Mapping) else {}
                    )
                    events.append(
                        CodingAgentEvent(
                            type="tool_call",
                            summary=_tool_summary(tool, input_payload),
                            detail=_tool_detail(input_payload),
                            tool=tool,
                            call_id=str(part.get("id", "")),
                            status="running",
                        )
                    )
                    paths = _file_paths(tool, input_payload)
                    if paths:
                        events.append(
                            CodingAgentEvent(
                                type="file_change",
                                summary=_bounded(
                                    f"{tool}: {', '.join(paths)}", MAX_SUMMARY_CHARS
                                ),
                                paths=paths,
                                tool=tool,
                                status="changed",
                            )
                        )
            return events

        if event_type == "user":
            message = payload.get("message")
            content = message.get("content") if isinstance(message, Mapping) else None
            for part in content if isinstance(content, list) else []:
                if not isinstance(part, Mapping) or part.get("type") != "tool_result":
                    continue
                text = _content_text(part.get("content"))
                is_error = bool(part.get("is_error"))
                events.append(
                    CodingAgentEvent(
                        type="tool_result",
                        summary=_bounded(
                            text or ("tool failed" if is_error else "tool completed"),
                            MAX_SUMMARY_CHARS,
                        ),
                        detail=text,
                        call_id=str(part.get("tool_use_id", "")),
                        status="failed" if is_error else "completed",
                    )
                )
            return events

        if event_type == "result":
            result = payload.get("result")
            text = str(result).strip() if isinstance(result, str) else ""
            if text:
                self._remember_text(text)
            usage = payload.get("usage")
            if isinstance(usage, Mapping):
                self._merge_usage(usage)
            for key in ("total_cost_usd", "duration_ms", "num_turns"):
                value = _float(payload.get(key))
                if value is not None:
                    self.usage[key] = int(value) if value.is_integer() else value
            if payload.get("is_error"):
                logger.warning("Claude Code reported an error result.")
                events.append(
                    CodingAgentEvent(
                        type="error",
                        summary=_bounded(text or "Claude Code reported an error", 240),
                        detail=text,
                        status="failed",
                    )
                )
            elif text:
                events.append(
                    CodingAgentEvent(
                        type="message",
                        summary=_bounded(text, MAX_SUMMARY_CHARS),
                        detail=text,
                        status="final",
                    )
                )
            events.append(
                CodingAgentEvent(
                    type="usage",
                    summary="Claude Code run usage",
                    usage={str(k): v for k, v in self.usage.items()},
                )
            )
            return events

        return events


class CodexStreamAdapter(CodingStreamAdapter):
    """Adapter for Codex ``exec --json`` events."""

    def feed(self, line: str) -> list[CodingAgentEvent]:
        payload = _json_payload(line)
        if payload is None:
            return []
        event_type = str(payload.get("type", ""))
        events: list[CodingAgentEvent] = []

        if event_type in {"thread.started", "turn.started"}:
            events.append(
                CodingAgentEvent(
                    type="lifecycle",
                    summary=f"Codex: {event_type.replace('.', ' ')}",
                    status=event_type,
                )
            )
            return events

        if event_type == "turn.completed":
            usage = payload.get("usage")
            if isinstance(usage, Mapping):
                self._merge_usage(usage)
            events.append(
                CodingAgentEvent(
                    type="usage",
                    summary="Codex turn usage",
                    usage={str(k): v for k, v in self.usage.items()},
                )
            )
            return events

        if event_type == "turn.failed":
            error = payload.get("error")
            message = error.get("message") if isinstance(error, Mapping) else error
            events.append(
                CodingAgentEvent(
                    type="error",
                    summary=_bounded(message or "Codex turn failed", MAX_SUMMARY_CHARS),
                    detail=str(message or ""),
                    status="failed",
                )
            )
            return events

        item = payload.get("item")
        if not isinstance(item, Mapping):
            return events
        item_type = str(item.get("type", ""))
        status = str(item.get("status", ""))
        completed = (
            not event_type
            or event_type == "item.completed"
            or status in {"completed", "failed"}
        )

        if item_type == "agent_message":
            text = str(item.get("text", "")).strip()
            if completed and text:
                self._remember_text(text)
                events.append(
                    CodingAgentEvent(
                        type="message",
                        summary=_bounded(text, MAX_SUMMARY_CHARS),
                        detail=text,
                        status="final" if event_type == "item.completed" else "running",
                    )
                )
            return events

        if item_type == "reasoning":
            text = str(item.get("text", "")).strip()
            if text:
                events.append(
                    CodingAgentEvent(
                        type="reasoning",
                        summary=_bounded(text, MAX_SUMMARY_CHARS),
                        detail=text,
                    )
                )
            return events

        if item_type == "command_execution":
            command = str(item.get("command", "")).strip()
            output = str(item.get("aggregated_output", "")).strip()
            exit_code = _int(item.get("exit_code"))
            if event_type == "item.started":
                events.append(
                    CodingAgentEvent(
                        type="tool_call",
                        summary=_bounded(f"shell: {command}", MAX_SUMMARY_CHARS),
                        detail=command,
                        tool="shell",
                        call_id=str(item.get("id", "")),
                        status="running",
                    )
                )
            elif completed:
                events.append(
                    CodingAgentEvent(
                        type="tool_result",
                        summary=_bounded(
                            f"shell exit {exit_code}: {output or command}",
                            MAX_SUMMARY_CHARS,
                        ),
                        detail=output,
                        tool="shell",
                        call_id=str(item.get("id", "")),
                        status="failed" if exit_code not in {None, 0} else "completed",
                    )
                )
            return events

        if item_type == "file_change":
            changes = item.get("changes")
            paths: list[str] = []
            for change in changes if isinstance(changes, list) else []:
                if isinstance(change, Mapping):
                    path = change.get("path")
                    if isinstance(path, str) and path:
                        paths.append(path)
            if paths:
                events.append(
                    CodingAgentEvent(
                        type="file_change",
                        summary=_bounded(
                            f"files changed: {', '.join(paths)}", MAX_SUMMARY_CHARS
                        ),
                        paths=paths,
                        status="changed" if completed else "running",
                    )
                )
            return events

        if item_type in {"mcp_tool_call", "web_search"}:
            tool = str(
                item.get("tool")
                or item.get("server")
                or ("web_search" if item_type == "web_search" else "mcp")
            )
            if event_type == "item.started":
                events.append(
                    CodingAgentEvent(
                        type="tool_call",
                        summary=_bounded(f"{tool} started", MAX_SUMMARY_CHARS),
                        detail=_tool_detail(item),
                        tool=tool,
                        call_id=str(item.get("id", "")),
                        status="running",
                    )
                )
            elif completed:
                result = item.get("result") or item.get("error")
                events.append(
                    CodingAgentEvent(
                        type="tool_result",
                        summary=_bounded(f"{tool} completed", MAX_SUMMARY_CHARS),
                        detail=_tool_detail(
                            result if isinstance(result, Mapping) else item
                        ),
                        tool=tool,
                        call_id=str(item.get("id", "")),
                        status="failed" if item.get("error") else "completed",
                    )
                )
            return events

        if item_type == "error":
            message = str(item.get("message", "")).strip()
            events.append(
                CodingAgentEvent(
                    type="error",
                    summary=_bounded(message or "Codex error", MAX_SUMMARY_CHARS),
                    detail=message,
                    status="failed",
                )
            )
        return events


class OpenCodeStreamAdapter(CodingStreamAdapter):
    """Adapter for OpenCode ``run --format json`` events."""

    def _add_usage(self, key: str, value: float) -> None:
        current = _float(self.usage.get(key, 0)) or 0.0
        total = current + value
        self.usage[key] = int(total) if total.is_integer() else round(total, 6)

    def _accumulate_usage(self, usage: Mapping[str, Any]) -> None:
        """Add one step's usage to the run total.

        OpenCode reports tokens and cost per ``step_finish`` instead of once
        for the whole run, so each step is an increment; replacing the totals
        would keep only the final step.
        """
        for key, value in usage.items():
            if key == "cache" and isinstance(value, Mapping):
                for cache_key, cache_value in value.items():
                    number = _float(cache_value)
                    if number is not None:
                        self._add_usage(f"cache_{cache_key}", number)
                continue
            number = _float(value)
            if number is not None:
                self._add_usage(str(key), number)

    def feed(self, line: str) -> list[CodingAgentEvent]:
        payload = _json_payload(line)
        if payload is None:
            return []
        event_type = str(payload.get("type", ""))
        part = payload.get("part")
        part_payload = part if isinstance(part, Mapping) else {}
        events: list[CodingAgentEvent] = []

        if event_type == "step_start":
            events.append(
                CodingAgentEvent(
                    type="lifecycle",
                    summary="OpenCode step started",
                    status="running",
                )
            )
            return events

        if event_type == "step_finish":
            tokens = part_payload.get("tokens")
            if isinstance(tokens, Mapping):
                self._accumulate_usage(tokens)
            cost = _float(part_payload.get("cost"))
            if cost is not None:
                self._add_usage("cost", cost)
            events.append(
                CodingAgentEvent(
                    type="usage",
                    summary="OpenCode step usage",
                    usage={str(k): v for k, v in self.usage.items()},
                )
            )
            return events

        if event_type == "text":
            message_id = str(part_payload.get("messageID", ""))
            text = self._remember_text(part_payload.get("text"), message_id=message_id)
            if text:
                events.append(
                    CodingAgentEvent(
                        type="message",
                        summary=_bounded(text, MAX_SUMMARY_CHARS),
                        detail=text,
                    )
                )
            return events

        if event_type == "reasoning":
            text = str(part_payload.get("text", "")).strip()
            if text:
                events.append(
                    CodingAgentEvent(
                        type="reasoning",
                        summary=_bounded(text, MAX_SUMMARY_CHARS),
                        detail=text,
                    )
                )
            return events

        if event_type == "tool_use":
            tool = str(part_payload.get("tool") or "tool")
            state = part_payload.get("state")
            state_payload = state if isinstance(state, Mapping) else {}
            status = str(state_payload.get("status", ""))
            tool_input = state_payload.get("input")
            input_payload = tool_input if isinstance(tool_input, Mapping) else {}
            if status in {"pending", "running", ""}:
                events.append(
                    CodingAgentEvent(
                        type="tool_call",
                        summary=_tool_summary(tool, input_payload),
                        detail=_tool_detail(input_payload),
                        tool=tool,
                        call_id=str(part_payload.get("callID", "")),
                        status="running",
                    )
                )
            elif status in {"completed", "error", "failed"}:
                output = state_payload.get("output") or state_payload.get("error")
                output_text = _content_text(output)
                events.append(
                    CodingAgentEvent(
                        type="tool_result",
                        summary=_bounded(
                            output_text or f"{tool} {status}", MAX_SUMMARY_CHARS
                        ),
                        detail=output_text,
                        tool=tool,
                        call_id=str(part_payload.get("callID", "")),
                        status="failed"
                        if status in {"error", "failed"}
                        else "completed",
                    )
                )
                paths = _file_paths(tool, input_payload)
                if paths:
                    events.append(
                        CodingAgentEvent(
                            type="file_change",
                            summary=_bounded(
                                f"{tool}: {', '.join(paths)}", MAX_SUMMARY_CHARS
                            ),
                            paths=paths,
                            tool=tool,
                            call_id=str(part_payload.get("callID", "")),
                            status="changed",
                        )
                    )
            return events

        if event_type == "error":
            error = payload.get("error")
            if isinstance(error, Mapping):
                data = error.get("data")
                message = data.get("message") if isinstance(data, Mapping) else None
                message = message or error.get("name") or "OpenCode error"
            else:
                message = error or "OpenCode error"
            events.append(
                CodingAgentEvent(
                    type="error",
                    summary=_bounded(message, MAX_SUMMARY_CHARS),
                    detail=str(message),
                    status="failed",
                )
            )
        return events


def adapter_for(agent_type: str) -> CodingStreamAdapter | None:
    """Return the stream adapter for one configured agent type."""
    if agent_type == "claude_code":
        return ClaudeStreamAdapter()
    if agent_type == "codex":
        return CodexStreamAdapter()
    if agent_type == "opencode":
        return OpenCodeStreamAdapter()
    return None


class CodingRunObserver:
    """Write one run's normalized events and summary into its task folder."""

    def __init__(
        self,
        *,
        agent: Mapping[str, Any],
        workspace: Path,
        run_id: str,
        on_event: EventCallback | None = None,
        trace: Any = None,
    ) -> None:
        self.agent = agent
        self.workspace = workspace
        self.run_id = run_id
        self.on_event = on_event
        self.trace = trace
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.status = "running"
        self.exit_code: int | None = None
        self.detail = ""
        self.artifacts: list[str] = []
        self.events = 0
        self.tool_calls = 0
        self._tool_call_ids: set[str] = set()
        self.latest_action = "starting"
        self.usage: dict[str, int | float] = {}
        self._sequence = 0
        self._events_path = workspace / EVENTS_LOG_NAME
        self._summary_path = workspace / RUN_SUMMARY_NAME
        self._events_file = self._events_path.open("w", encoding="utf-8")
        self._write_summary()
        self._trace(
            "coding_agent_start",
            agent_id=str(agent.get("id", "")),
            agent_type=str(agent.get("type", "")),
            agent_name=str(agent.get("name", "")),
            run_id=run_id,
            workspace=workspace.name,
        )

    def _trace(self, action: str, **fields: Any) -> None:
        """Record progress without letting a trace sink break the run."""
        if self.trace is None:
            return
        try:
            self.trace.record(action, **fields)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Coding trace record failed: %s", safe_error("", exc))

    def _summary(self) -> dict[str, Any]:
        finished = self.finished_at
        duration_ms = int(((finished or time.time()) - self.started_at) * 1000)
        return {
            "run_id": self.run_id,
            "agent": {
                "id": str(self.agent.get("id", "")),
                "name": str(self.agent.get("name", "")),
                "type": str(self.agent.get("type", "")),
                "command": str(self.agent.get("command", "")),
            },
            "status": self.status,
            "started_at": datetime.fromtimestamp(self.started_at, tz=UTC).isoformat(),
            "finished_at": (
                datetime.fromtimestamp(finished, tz=UTC).isoformat()
                if finished is not None
                else None
            ),
            "duration_ms": max(0, duration_ms),
            "exit_code": self.exit_code,
            "workspace": self.workspace.name,
            "event_count": self.events,
            "tool_call_count": self.tool_calls,
            "latest_action": _bounded(
                redact_sensitive_text(self.latest_action), MAX_SUMMARY_CHARS
            ),
            "usage": dict(self.usage),
            "detail": redact_sensitive_text(self.detail),
            "artifacts": list(self.artifacts),
            "files": {
                "task": "TASK.md",
                "output": "output.log",
                "events": EVENTS_LOG_NAME,
                "summary": RUN_SUMMARY_NAME,
            },
        }

    def _write_summary(self) -> None:
        payload = sanitize_log_payload(self._summary())
        temporary = self._summary_path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self._summary_path)
        except OSError as exc:
            logger.debug("Could not write coding run summary: %s", safe_error("", exc))

    def _counts_tool_call(self, event: CodingAgentEvent) -> bool:
        """Count each call once, including completed-only CLI events."""
        if event.type not in {"tool_call", "tool_result"}:
            return False
        if event.call_id:
            if event.call_id in self._tool_call_ids:
                return False
            self._tool_call_ids.add(event.call_id)
            return True
        return event.type == "tool_call"

    async def record(self, event: CodingAgentEvent) -> None:
        """Persist one event and forward it to the live consumers."""
        self._sequence += 1
        payload = sanitize_log_payload(event.as_dict())
        payload["seq"] = self._sequence
        try:
            self._events_file.write(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            self._events_file.flush()
        except OSError as exc:
            logger.debug("Could not write coding run event: %s", safe_error("", exc))

        self.events += 1
        if self._counts_tool_call(event):
            self.tool_calls += 1
        if event.type == "usage":
            self.usage.update(event.usage)
        self.latest_action = event.summary or event.type
        self._write_summary()

        self._trace(
            "coding_agent_event",
            agent_id=str(self.agent.get("id", "")),
            run_id=self.run_id,
            event_type=event.type,
            tool=event.tool,
            call_id=event.call_id,
            status=event.status,
            summary=event.summary,
            paths=event.paths,
            usage=event.usage,
        )
        if self.on_event is not None:
            try:
                await self.on_event(event)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Coding event progress callback failed: %s", safe_error("", exc)
                )

    def finish(
        self,
        *,
        status: str,
        exit_code: int | None,
        artifacts: list[str],
        detail: str = "",
        latest_action: str = "",
    ) -> dict[str, Any]:
        """Seal the summary and return it for the work-session record."""
        self.status = status
        self.exit_code = exit_code
        self.artifacts = list(artifacts)
        self.detail = detail
        if latest_action:
            self.latest_action = latest_action
        self.finished_at = time.time()
        self._write_summary()
        summary = sanitize_log_payload(self._summary())
        self._trace(
            "coding_agent_end",
            agent_id=str(self.agent.get("id", "")),
            run_id=self.run_id,
            status=status,
            exit_code=exit_code,
            artifact_count=len(artifacts),
            event_count=self.events,
            tool_call_count=self.tool_calls,
            usage=self.usage,
            detail=detail,
        )
        return summary

    def close(self) -> None:
        self._events_file.close()


__all__ = [
    "CodingAgentEvent",
    "CodingRunObserver",
    "CodingStreamAdapter",
    "ClaudeStreamAdapter",
    "CodexStreamAdapter",
    "OpenCodeStreamAdapter",
    "EVENTS_LOG_NAME",
    "RUN_SUMMARY_NAME",
    "adapter_for",
]
