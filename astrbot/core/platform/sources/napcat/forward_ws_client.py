from __future__ import annotations

import asyncio
import json
import ssl
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from astrbot.api import logger

from .exceptions import NapCatApiError, NapCatTransportError
from .generated import ob11_events as ob11_models
from .generated.ob11_events import OB11AllEvent
from .types import (
    NapCatFetchedMessage,
    NapCatLoginInfo,
    NapCatSendMessageResult,
    NapCatStatus,
    NapCatVersionInfo,
)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


MESSAGE_EVENT_MODELS: dict[str, type[ob11_models.BaseModel]] = {
    "private": ob11_models.OB11PrivateMessage,
    "group": ob11_models.OB11GroupMessage,
}

NOTICE_EVENT_MODELS: dict[tuple[str, str | None], type[ob11_models.BaseModel]] = {
    ("bot_offline", None): ob11_models.OneBot11BotOffline,
    ("group_upload", None): ob11_models.OneBot11GroupUpload,
    ("group_admin", None): ob11_models.OneBot11GroupAdmin,
    ("group_decrease", None): ob11_models.OneBot11GroupDecrease,
    ("group_increase", None): ob11_models.OneBot11GroupIncrease,
    ("group_ban", None): ob11_models.OneBot11GroupBan,
    ("friend_add", None): ob11_models.OneBot11FriendAdd,
    ("group_recall", None): ob11_models.OneBot11GroupRecall,
    ("friend_recall", None): ob11_models.OneBot11FriendRecall,
    ("group_msg_emoji_like", None): ob11_models.OneBot11GroupMessageReaction,
    ("reaction", None): ob11_models.OneBot11GroupMessageReactionLagrange,
    ("essence", None): ob11_models.OneBot11GroupEssence,
    ("group_card", None): ob11_models.OneBot11GroupCard,
    ("notify", "poke"): ob11_models.OneBot11Poke,
    ("notify", "lucky_king"): ob11_models.OneBot11LuckyKing,
    ("notify", "honor"): ob11_models.OneBot11Honor,
    ("notify", "gray_tip"): ob11_models.OneBot11GroupGrayTip,
    ("notify", "group_name"): ob11_models.OneBot11GroupName,
    ("notify", "title"): ob11_models.OneBot11GroupTitle,
    ("notify", "input_status"): ob11_models.OneBot11InputStatus,
    ("notify", "profile_like"): ob11_models.OneBot11ProfileLike,
    ("online_file_receive", None): ob11_models.OneBot11OnlineFileReceive,
    ("online_file_send", None): ob11_models.OneBot11OnlineFileSend,
}

REQUEST_EVENT_MODELS: dict[str, type[ob11_models.BaseModel]] = {
    "friend": ob11_models.OneBot11FriendRequest,
    "group": ob11_models.OneBot11GroupRequest,
}

META_EVENT_MODELS: dict[str, type[ob11_models.BaseModel]] = {
    "lifecycle": ob11_models.OneBot11Lifecycle,
    "heartbeat": ob11_models.OneBot11Heartbeat,
}

GROUP_SENDER_ROLE_VALUES = frozenset({"owner", "admin", "member"})
FRIEND_SENDER_KEYS = frozenset(
    {"age", "card", "group_id", "nickname", "sex", "user_id"}
)
GROUP_SENDER_KEYS = frozenset(
    {"age", "area", "card", "level", "nickname", "role", "sex", "title", "user_id"}
)

NONSTANDARD_MESSAGE_SEGMENT_FALLBACK_TEXT: dict[str, str] = {
    "flash": "[FlashTransfer]",
}


def _normalize_message_segment_for_validation(
    segment: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    normalized_segment = dict(segment)
    segment_type = _string_or_none(normalized_segment.get("type"))
    if not segment_type:
        return normalized_segment, None

    fallback_text = NONSTANDARD_MESSAGE_SEGMENT_FALLBACK_TEXT.get(segment_type)
    if fallback_text is None:
        return normalized_segment, None

    raw_data = normalized_segment.get("data")
    data = dict(raw_data) if isinstance(raw_data, Mapping) else {}
    if segment_type == "markdown":
        fallback_text = _string_or_none(data.get("content")) or fallback_text
    elif segment_type == "mface":
        fallback_text = _string_or_none(data.get("summary")) or fallback_text
    elif segment_type == "onlinefile":
        file_name = _string_or_none(data.get("fileName"))
        if file_name:
            fallback_text = f"[OnlineFile:{file_name}]"

    return (
        {
            "type": "text",
            "data": {"text": fallback_text},
        },
        segment_type,
    )


def _normalize_inbound_message_payload_for_validation(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    normalized_payload = dict(payload)
    normalization_notes: list[str] = []

    message_type = _string_or_none(normalized_payload.get("message_type"))
    sender = normalized_payload.get("sender")
    sender_dict = dict(sender) if isinstance(sender, Mapping) else {}

    sender_user_id = sender_dict.get("user_id", normalized_payload.get("user_id"))
    if sender_user_id is not None and sender_dict.get("user_id") != sender_user_id:
        sender_dict["user_id"] = sender_user_id
        normalization_notes.append("filled sender.user_id from user_id")

    allowed_sender_keys = (
        GROUP_SENDER_KEYS if message_type == "group" else FRIEND_SENDER_KEYS
    )
    sender_extra_keys = sorted(
        key
        for key in sender_dict
        if isinstance(key, str) and key not in allowed_sender_keys
    )
    if sender_extra_keys:
        sender_dict = {
            key: value
            for key, value in sender_dict.items()
            if not isinstance(key, str) or key in allowed_sender_keys
        }
        normalization_notes.append(
            "dropped sender extra fields: " + ", ".join(sender_extra_keys)
        )

    if sender_dict.get("nickname") is None:
        sender_dict["nickname"] = ""
        normalization_notes.append("filled missing sender.nickname")

    if message_type == "group":
        role = _string_or_none(sender_dict.get("role"))
        if role not in GROUP_SENDER_ROLE_VALUES:
            sender_dict["role"] = "member"
            normalization_notes.append("defaulted sender.role to member")

    if sender_dict:
        normalized_payload["sender"] = sender_dict

    raw_segments = normalized_payload.get("message")
    if isinstance(raw_segments, list):
        normalized_segments: list[dict[str, Any] | Any] = []
        normalized_segment_types: list[str] = []
        for segment in raw_segments:
            if not isinstance(segment, Mapping):
                normalized_segments.append(segment)
                continue
            normalized_segment, normalized_segment_type = (
                _normalize_message_segment_for_validation(segment)
            )
            normalized_segments.append(normalized_segment)
            if normalized_segment_type is not None:
                normalized_segment_types.append(normalized_segment_type)
        if normalized_segment_types:
            normalized_payload["message"] = normalized_segments
            normalization_notes.append(
                "normalized nonstandard message segments: "
                + ", ".join(normalized_segment_types)
            )

    return normalized_payload, normalization_notes


def _select_event_model(
    payload: Mapping[str, Any],
) -> type[ob11_models.BaseModel] | None:
    post_type = _string_or_none(payload.get("post_type"))
    if post_type in {"message", "message_sent"}:
        return MESSAGE_EVENT_MODELS.get(
            _string_or_none(payload.get("message_type")) or ""
        )

    if post_type == "notice":
        notice_type = _string_or_none(payload.get("notice_type"))
        if not notice_type:
            return None
        sub_type = _string_or_none(payload.get("sub_type"))
        return NOTICE_EVENT_MODELS.get(
            (notice_type, sub_type)
        ) or NOTICE_EVENT_MODELS.get((notice_type, None))

    if post_type == "request":
        return REQUEST_EVENT_MODELS.get(
            _string_or_none(payload.get("request_type")) or ""
        )

    if post_type == "meta_event":
        return META_EVENT_MODELS.get(
            _string_or_none(payload.get("meta_event_type")) or ""
        )

    return None


def _validate_ob11_event(payload: Mapping[str, Any]) -> tuple[OB11AllEvent, str]:
    payload_dict = dict(payload)
    model_class = _select_event_model(payload_dict)
    if model_class is None:
        return OB11AllEvent.model_validate(payload_dict, extra="ignore"), "OB11AllEvent"
    typed_event = model_class.model_validate(payload_dict, extra="ignore")
    return OB11AllEvent(root=typed_event), model_class.__name__


@dataclass(frozen=True)
class _RawMessageSegment:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.payload


class NapCatForwardWebSocketClient:
    def __init__(
        self,
        *,
        ws_url: str,
        token: str | None = None,
        action_timeout_seconds: float = 30.0,
        reconnect_interval_seconds: float = 5.0,
        verify_ssl: bool = True,
        max_size_bytes: int = 50 * 1024 * 1024,
        on_event: Callable[[OB11AllEvent], Awaitable[None]],
    ) -> None:
        self.ws_url = ws_url.strip()
        self.token = token.strip() if token else ""
        self.action_timeout_seconds = action_timeout_seconds
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.verify_ssl = verify_ssl
        self.max_size_bytes = max_size_bytes
        self.on_event = on_event

        self._runner_task: asyncio.Task[None] | None = None
        self._socket: ClientConnection | None = None
        self._connected_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def _build_api_error(
        self, operation: str, payload: Mapping[str, Any]
    ) -> NapCatApiError:
        status = payload.get("status")
        retcode = _coerce_int(payload.get("retcode"))
        message = payload.get("message")
        wording = payload.get("wording")
        return NapCatApiError(
            operation,
            status=str(status) if status is not None else None,
            retcode=retcode,
            message=str(message) if isinstance(message, str) else None,
            wording=str(wording) if isinstance(wording, str) else None,
        )

    async def start(self) -> None:
        if self._runner_task is not None:
            return
        if not self.ws_url.startswith(("ws://", "wss://")):
            raise ValueError(
                f"NapCat forward WebSocket URL must start with ws:// or wss://: {self.ws_url}"
            )

        self._stop_event.clear()
        self._runner_task = asyncio.create_task(self._run_loop())
        await self._wait_until_connected("start")

    async def close(self) -> None:
        self._stop_event.set()
        socket = self._socket
        if socket is not None:
            await socket.close(code=1000, reason="Adapter shutdown")
        if self._runner_task is not None:
            await self._runner_task
            self._runner_task = None
        self._connected_event.clear()

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self._connect_and_listen()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if self._stop_event.is_set():
                        break
                    logger.warning(
                        "[NapCat] Forward WebSocket disconnected from %s: %s. Retrying in %.1fs.",
                        self.ws_url,
                        exc,
                        self.reconnect_interval_seconds,
                    )

                if self._stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.reconnect_interval_seconds,
                    )
                except TimeoutError:
                    pass
        finally:
            self._fail_pending("client stopped")
            self._socket = None
            self._connected_event.clear()

    async def _connect_and_listen(self) -> None:
        ssl_context: ssl.SSLContext | bool | None = None
        if self.ws_url.startswith("wss://"):
            if self.verify_ssl:
                ssl_context = True
            else:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        logger.info("[NapCat] Connecting forward WebSocket to %s", self.ws_url)
        async with connect(
            self.ws_url,
            additional_headers=headers or None,
            max_size=self.max_size_bytes,
            compression=None,
            ssl=ssl_context,
        ) as websocket:
            self._socket = websocket
            self._connected_event.set()
            logger.info("[NapCat] Forward WebSocket connected to %s", self.ws_url)

            try:
                async for payload in websocket:
                    await self._handle_ws_payload(payload)
            except ConnectionClosed as exc:
                raise NapCatTransportError(
                    "forward_ws",
                    f"connection closed code={exc.code} reason={exc.reason}",
                ) from exc
            finally:
                self._socket = None
                self._connected_event.clear()
                self._fail_pending("connection lost")

    async def _handle_ws_payload(self, payload: str | bytes) -> None:
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(
                    "[NapCat] Forward WebSocket received non-UTF8 binary frame"
                )
                return

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "[NapCat] Forward WebSocket received non-JSON payload: %r", payload
            )
            return

        if not isinstance(parsed, dict):
            logger.debug(
                "[NapCat] Forward WebSocket ignored non-object payload: %r", parsed
            )
            return

        if "post_type" in parsed:
            validation_payload = parsed
            normalization_notes: list[str] = []
            if parsed.get("post_type") in {"message", "message_sent"}:
                validation_payload, normalization_notes = (
                    _normalize_inbound_message_payload_for_validation(parsed)
                )
                if normalization_notes:
                    logger.info(
                        "[NapCat] Forward WebSocket normalized inbound %s payload before validation: %s",
                        parsed.get("message_type", "message"),
                        "; ".join(normalization_notes),
                    )

            event_model = _select_event_model(validation_payload)
            try:
                event, event_model_name = _validate_ob11_event(validation_payload)
            except ValidationError as exc:
                first_error = exc.errors()[0] if exc.errors() else {}
                error_location = ".".join(
                    str(part) for part in first_error.get("loc", ())
                )
                payload_excerpt = json.dumps(validation_payload, ensure_ascii=False)[
                    :1200
                ]
                logger.warning(
                    "[NapCat] Forward WebSocket rejected event payload: model=%s post_type=%s message_type=%s notice_type=%s request_type=%s meta_event_type=%s error=%s loc=%s payload=%s",
                    event_model.__name__ if event_model is not None else "OB11AllEvent",
                    validation_payload.get("post_type"),
                    validation_payload.get("message_type"),
                    validation_payload.get("notice_type"),
                    validation_payload.get("request_type"),
                    validation_payload.get("meta_event_type"),
                    first_error.get("msg", exc),
                    error_location or "<unknown>",
                    payload_excerpt,
                )
                return
            logger.debug(
                "[NapCat] Forward WebSocket validated event with %s",
                event_model_name,
            )
            await self.on_event(event)
            return

        echo = parsed.get("echo")
        if echo is None:
            if parsed.get("status") == "failed":
                error = self._build_api_error("forward_ws", parsed)
                logger.warning(
                    "[NapCat] Forward WebSocket received failed response without echo: %s",
                    error,
                )
                self._fail_pending_with_exception(error)
                return
            logger.debug(
                "[NapCat] Forward WebSocket ignored response without echo: %s", parsed
            )
            return

        future = self._pending.pop(str(echo), None)
        if future is None:
            logger.debug(
                "[NapCat] Forward WebSocket ignored unmatched echo response: %s", echo
            )
            return
        if not future.done():
            future.set_result(parsed)

    async def call_action(self, action: str, **params: Any) -> dict[str, Any]:
        await self._wait_until_connected(action)
        socket = self._socket
        if socket is None:
            raise NapCatTransportError(action, "forward websocket is not connected")

        payload = {
            "action": action,
            "params": _strip_none_values(params),
            "echo": uuid.uuid4().hex,
        }
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[payload["echo"]] = future

        try:
            async with self._send_lock:
                await socket.send(json.dumps(payload, ensure_ascii=False))
            return await asyncio.wait_for(future, timeout=self.action_timeout_seconds)
        except TimeoutError as exc:
            self._pending.pop(payload["echo"], None)
            if not future.done():
                future.cancel()
            raise NapCatTransportError(
                action,
                f"timed out waiting for response after {self.action_timeout_seconds:.1f}s",
            ) from exc
        except ConnectionClosed as exc:
            self._pending.pop(payload["echo"], None)
            if not future.done():
                future.cancel()
            raise NapCatTransportError(
                action,
                f"forward websocket closed code={exc.code} reason={exc.reason}",
            ) from exc

    async def _wait_until_connected(self, operation: str) -> None:
        if self._connected_event.is_set():
            return
        try:
            await asyncio.wait_for(
                self._connected_event.wait(),
                timeout=self.action_timeout_seconds,
            )
        except TimeoutError as exc:
            raise NapCatTransportError(
                operation,
                f"forward websocket did not connect within {self.action_timeout_seconds:.1f}s",
            ) from exc

    def _fail_pending(self, detail: str) -> None:
        self._fail_pending_with_exception(
            NapCatTransportError("forward_ws", f"pending action failure: {detail}")
        )

    def _fail_pending_with_exception(self, exc: Exception) -> None:
        for echo, future in list(self._pending.items()):
            if future.done():
                continue
            if isinstance(exc, NapCatTransportError):
                error: Exception = NapCatTransportError(
                    exc.operation,
                    f"pending action {echo} failed: {exc.detail}",
                )
            elif isinstance(exc, NapCatApiError):
                error = NapCatApiError(
                    exc.operation,
                    status=exc.status,
                    retcode=exc.retcode,
                    message=exc.message,
                    wording=exc.wording,
                )
            else:
                error = exc
            future.set_exception(error)
        self._pending.clear()

    def text(self, content: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "text", "data": {"text": content}})

    def at(self, qq: int | str, *, name: str | None = None) -> _RawMessageSegment:
        data = {"qq": str(qq)}
        if name:
            data["name"] = name
        return _RawMessageSegment({"type": "at", "data": data})

    def at_all(self) -> _RawMessageSegment:
        return self.at("all")

    def reply(self, message_id: int | str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "reply", "data": {"id": str(message_id)}})

    def face(self, face_id: int | str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "face", "data": {"id": str(face_id)}})

    def mface(
        self,
        *,
        emoji_package_id: int | float,
        emoji_id: str,
        key: str,
        summary: str,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "mface",
                "data": {
                    "emoji_package_id": int(emoji_package_id),
                    "emoji_id": emoji_id,
                    "key": key,
                    "summary": summary,
                },
            }
        )

    def contact(
        self, *, contact_type: str, contact_id: int | str
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {"type": "contact", "data": {"type": contact_type, "id": str(contact_id)}}
        )

    def location(
        self,
        *,
        lat: float,
        lon: float,
        title: str | None = None,
        content: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "location",
                "data": _strip_none_values(
                    {
                        "lat": str(lat),
                        "lon": str(lon),
                        "title": title,
                        "content": content,
                    }
                ),
            }
        )

    def poke(
        self,
        *,
        target_id: int | str | None = None,
        poke_type: int | str | None = None,
        user_id: int | str | None = None,
    ) -> _RawMessageSegment:
        resolved_target_id = target_id if target_id is not None else user_id
        if resolved_target_id is None:
            raise ValueError("poke segments require target_id or user_id")
        return _RawMessageSegment(
            {
                "type": "poke",
                "data": _strip_none_values(
                    {
                        "type": str(poke_type) if poke_type is not None else None,
                        "id": str(resolved_target_id),
                    }
                ),
            }
        )

    def json_message(self, data: Any) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "json", "data": {"data": data}})

    def markdown_message(self, content: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "markdown", "data": {"content": content}})

    def mini_app_message(self, data: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "miniapp", "data": {"data": data}})

    def online_file(
        self,
        *,
        msg_id: str,
        element_id: str,
        file_name: str,
        file_size: str,
        is_dir: bool,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "onlinefile",
                "data": {
                    "msgId": msg_id,
                    "elementId": element_id,
                    "fileName": file_name,
                    "fileSize": file_size,
                    "isDir": is_dir,
                },
            }
        )

    def xml_message(self, data: str) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "xml", "data": {"data": data}})

    def flash_transfer(self, *, file_set_id: str) -> _RawMessageSegment:
        return _RawMessageSegment(
            {"type": "flashtransfer", "data": {"fileSetId": file_set_id}}
        )

    def share(
        self,
        *,
        url: str,
        title: str,
        content: str | None = None,
        image: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "share",
                "data": _strip_none_values(
                    {
                        "url": url,
                        "title": title,
                        "content": content,
                        "image": image,
                    }
                ),
            }
        )

    def dice(self) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "dice", "data": {}})

    def rps(self) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "rps", "data": {}})

    def shake(self) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "shake", "data": {}})

    def music(
        self,
        *,
        music_type: str,
        music_id: int | str | None = None,
        url: str | None = None,
        audio: str | None = None,
        title: str | None = None,
        content: str | None = None,
        image: str | None = None,
    ) -> _RawMessageSegment:
        if music_type == "custom":
            if not url or not image:
                raise ValueError(
                    "custom music segments require both url and image fields"
                )
            return _RawMessageSegment(
                {
                    "type": "music",
                    "data": {
                        "type": music_type,
                        "id": None,
                        "url": url,
                        "audio": audio,
                        "title": title,
                        "content": content,
                        "image": image,
                    },
                }
            )
        if music_id is None:
            raise ValueError("id music segments require a music_id")
        return _RawMessageSegment(
            {"type": "music", "data": {"type": music_type, "id": str(music_id)}}
        )

    def forward(self, forward_id: str | int) -> _RawMessageSegment:
        return _RawMessageSegment({"type": "forward", "data": {"id": str(forward_id)}})

    def image(
        self,
        *,
        file: str,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "image",
                "data": _strip_none_values(
                    {"file": file, "url": url, "path": path, "name": name}
                ),
            }
        )

    def record(
        self,
        *,
        file: str,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "record",
                "data": _strip_none_values(
                    {"file": file, "url": url, "path": path, "name": name}
                ),
            }
        )

    def video(
        self,
        *,
        file: str,
        url: str | None = None,
        path: str | None = None,
        name: str | None = None,
        thumb: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "video",
                "data": _strip_none_values(
                    {
                        "file": file,
                        "url": url,
                        "path": path,
                        "name": name,
                        "thumb": thumb,
                    }
                ),
            }
        )

    def file(
        self,
        *,
        file: str,
        file_id: str | None = None,
        name: str | None = None,
        path: str | None = None,
        url: str | None = None,
    ) -> _RawMessageSegment:
        return _RawMessageSegment(
            {
                "type": "file",
                "data": _strip_none_values(
                    {
                        "file": file,
                        "file_id": file_id,
                        "name": name,
                        "path": path,
                        "url": url,
                    }
                ),
            }
        )

    async def get_login_info(self) -> NapCatLoginInfo:
        payload = await self.call_action("get_login_info")
        data = self._require_data_dict("get_login_info", payload)
        user_id = _coerce_int(data.get("user_id"))
        if user_id is None:
            raise NapCatTransportError(
                "get_login_info",
                "successful response did not contain numeric user_id",
            )
        nickname = _string_or_none(data.get("nickname"))
        if nickname is None:
            raise NapCatTransportError(
                "get_login_info",
                "successful response did not contain nickname",
            )
        return NapCatLoginInfo(
            user_id=user_id,
            nickname=nickname,
            qid=_string_or_none(data.get("qid")),
            remark=_string_or_none(data.get("remark")),
            sex=_string_or_none(data.get("sex")),
            age=_coerce_int(data.get("age")),
            level=_coerce_int(data.get("level")),
            login_days=_coerce_int(data.get("login_days")),
            extra={
                key: value
                for key, value in data.items()
                if key
                not in {
                    "user_id",
                    "nickname",
                    "qid",
                    "remark",
                    "sex",
                    "age",
                    "level",
                    "login_days",
                }
            },
        )

    async def get_status(self) -> NapCatStatus:
        payload = await self.call_action("get_status")
        data = self._require_data_dict("get_status", payload)
        stats = data.get("stat")
        if not isinstance(stats, dict):
            stats = {}
        return NapCatStatus(
            online=bool(data.get("online", False)),
            good=bool(data.get("good", False)),
            stats=stats,
            extra={key: value for key, value in data.items() if key != "stat"},
        )

    async def get_version_info(self) -> NapCatVersionInfo:
        payload = await self.call_action("get_version_info")
        data = self._require_data_dict("get_version_info", payload)
        app_name = _string_or_none(data.get("app_name"))
        app_version = _string_or_none(data.get("app_version"))
        protocol_version = _string_or_none(data.get("protocol_version"))
        if app_name is None or app_version is None or protocol_version is None:
            raise NapCatTransportError(
                "get_version_info",
                "successful response did not contain app_name/app_version/protocol_version",
            )
        return NapCatVersionInfo(
            app_name=app_name,
            app_version=app_version,
            protocol_version=protocol_version,
            extra={
                key: value
                for key, value in data.items()
                if key not in {"app_name", "app_version", "protocol_version"}
            },
        )

    async def get_message(self, message_id: int | str) -> NapCatFetchedMessage:
        payload = await self.call_action("get_msg", message_id=str(message_id))
        data = self._require_data_dict("get_message", payload)
        sender = data.get("sender")
        if not isinstance(sender, dict):
            sender = {}
        sender_nickname = (
            sender.get("card") or sender.get("nickname") or sender.get("nick")
        )
        raw_message = data.get("raw_message")
        return NapCatFetchedMessage(
            message_id=_coerce_int(data.get("message_id")) or int(message_id),
            sender_id=_coerce_int(data.get("user_id")),
            sender_nickname=str(sender_nickname) if sender_nickname else None,
            time=_coerce_int(data.get("time")),
            message_str=str(raw_message) if isinstance(raw_message, str) else "",
            raw_message=str(raw_message) if isinstance(raw_message, str) else "",
            message_payload=data.get("message"),
            extra={
                "sender": sender,
                "message": data.get("message"),
                **{
                    key: value
                    for key, value in data.items()
                    if key not in {"sender", "message"}
                },
            },
        )

    async def get_group_info(self, group_id: int | str) -> dict[str, Any]:
        return self._require_data_dict(
            "get_group_info",
            await self.call_action("get_group_info", group_id=str(group_id)),
        )

    async def get_group_member_info(
        self,
        group_id: int | str,
        user_id: int | str,
        *,
        no_cache: bool | None = None,
    ) -> dict[str, Any]:
        return self._require_data_dict(
            "get_group_member_info",
            await self.call_action(
                "get_group_member_info",
                group_id=str(group_id),
                user_id=str(user_id),
                no_cache=no_cache,
            ),
        )

    async def get_group_member_list(
        self,
        group_id: int | str,
        *,
        no_cache: bool | None = None,
    ) -> list[Any]:
        payload = await self.call_action(
            "get_group_member_list",
            group_id=str(group_id),
            no_cache=no_cache,
        )
        data = self._require_data("get_group_member_list", payload)
        if not isinstance(data, list):
            raise NapCatTransportError(
                "get_group_member_list",
                "successful response did not contain a member list",
            )
        return data

    async def get_stranger_info(
        self,
        user_id: int | str,
        *,
        no_cache: bool = False,
    ) -> dict[str, Any]:
        return self._require_data_dict(
            "get_stranger_info",
            await self.call_action(
                "get_stranger_info",
                user_id=str(user_id),
                no_cache=no_cache,
            ),
        )

    async def get_forward_message(self, forward_id: int | str) -> dict[str, Any]:
        forward_id_str = str(forward_id).strip()
        if not forward_id_str:
            raise ValueError("forward_id must not be empty")
        payload = await self.call_action("get_forward_msg", message_id=forward_id_str)
        data = self._require_data("get_forward_message", payload)
        if isinstance(data, list):
            payload["data"] = {"messages": data}
            return payload
        if not isinstance(data, dict):
            raise NapCatTransportError(
                "get_forward_message",
                "successful response did not contain object or list data payload",
            )
        return payload

    async def get_image(
        self,
        *,
        file: str | None = None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_image", file=file, file_id=file_id)
        )

    async def get_file(
        self,
        *,
        file: str | None = None,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_file", file=file, file_id=file_id)
        )

    async def get_group_file_url(
        self, *, group_id: int | str, file_id: str
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "get_group_file_url",
                group_id=str(group_id),
                file_id=file_id,
            )
        )

    async def get_private_file_url(self, *, file_id: str) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_private_file_url", file_id=file_id)
        )

    async def get_online_file_messages(self, *, user_id: int | str) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_online_file_msg", user_id=str(user_id))
        )

    async def create_flash_task(
        self,
        *,
        files: list[str] | str,
        name: str | None = None,
        thumb_path: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "create_flash_task",
                files=files,
                name=name,
                thumb_path=thumb_path,
            )
        )

    async def get_flash_file_list(self, *, fileset_id: str) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("get_flash_file_list", fileset_id=fileset_id)
        )

    async def get_flash_file_url(
        self,
        *,
        fileset_id: str,
        file_name: str | None = None,
        file_index: int | float | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "get_flash_file_url",
                fileset_id=fileset_id,
                file_name=file_name,
                file_index=float(file_index) if file_index is not None else None,
            )
        )

    async def receive_online_file(
        self,
        *,
        user_id: int | str,
        msg_id: str,
        element_id: str,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "receive_online_file",
                user_id=str(user_id),
                msg_id=msg_id,
                element_id=element_id,
            )
        )

    async def refuse_online_file(
        self,
        *,
        user_id: int | str,
        msg_id: str,
        element_id: str,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "refuse_online_file",
                user_id=str(user_id),
                msg_id=msg_id,
                element_id=element_id,
            )
        )

    async def cancel_online_file(
        self, *, user_id: int | str, msg_id: str
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "cancel_online_file",
                user_id=str(user_id),
                msg_id=msg_id,
            )
        )

    async def send_online_file(
        self,
        *,
        user_id: int | str,
        file_path: str,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_online_file",
                user_id=str(user_id),
                file_path=file_path,
                file_name=file_name,
            )
        )

    async def send_online_folder(
        self,
        *,
        user_id: int | str,
        folder_path: str,
        folder_name: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_online_folder",
                user_id=str(user_id),
                folder_path=folder_path,
                folder_name=folder_name,
            )
        )

    async def send_flash_message(
        self,
        *,
        fileset_id: str,
        user_id: int | str | None = None,
        group_id: int | str | None = None,
    ) -> dict[str, Any]:
        if (user_id is None) == (group_id is None):
            raise ValueError("Exactly one of user_id or group_id must be provided.")
        return self._build_action_payload(
            await self.call_action(
                "send_flash_msg",
                fileset_id=fileset_id,
                user_id=str(user_id) if user_id is not None else None,
                group_id=str(group_id) if group_id is not None else None,
            )
        )

    async def send_message(
        self,
        *,
        message: Any,
        user_id: int | str | None = None,
        group_id: int | str | None = None,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        if (user_id is None) == (group_id is None):
            raise ValueError("Exactly one of user_id or group_id must be provided.")
        payload = await self.call_action(
            "send_msg",
            message=self._normalize_message(message),
            message_type="private" if user_id is not None else "group",
            user_id=str(user_id) if user_id is not None else None,
            group_id=str(group_id) if group_id is not None else None,
            auto_escape=auto_escape,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_message", payload)

    async def send_private_message(
        self,
        *,
        user_id: int | str,
        message: Any,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_private_msg",
            message=self._normalize_message(message),
            message_type="private",
            user_id=str(user_id),
            auto_escape=auto_escape,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_private_message", payload)

    async def send_private_forward_message(
        self,
        *,
        user_id: int | str,
        messages: list[object],
        source: str | None = None,
        summary: str | None = None,
        prompt: str | None = None,
        news: list[object] | None = None,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_private_forward_msg",
            message_type="private",
            user_id=str(user_id),
            message=self._normalize_message(messages),
            messages=self._normalize_message(messages),
            source=source,
            summary=summary,
            prompt=prompt,
            news=news,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_private_forward_message", payload)

    async def send_group_message(
        self,
        *,
        group_id: int | str,
        message: Any,
        auto_escape: bool = False,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_group_msg",
            message=self._normalize_message(message),
            message_type="group",
            group_id=str(group_id),
            auto_escape=auto_escape,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_group_message", payload)

    async def send_group_forward_message(
        self,
        *,
        group_id: int | str,
        messages: list[object],
        source: str | None = None,
        summary: str | None = None,
        prompt: str | None = None,
        news: list[object] | None = None,
        timeout_ms: float | None = None,
    ) -> NapCatSendMessageResult:
        payload = await self.call_action(
            "send_group_forward_msg",
            message_type="group",
            group_id=str(group_id),
            message=self._normalize_message(messages),
            messages=self._normalize_message(messages),
            source=source,
            summary=summary,
            prompt=prompt,
            news=news,
            timeout=float(timeout_ms) if timeout_ms is not None else None,
        )
        return self._build_send_result("send_group_forward_message", payload)

    async def delete_message(self, message_id: int | str) -> None:
        self._require_success_payload(
            "delete_message",
            await self.call_action("delete_msg", message_id=str(message_id)),
        )

    async def set_group_admin(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        enable: bool = True,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_admin",
                group_id=str(group_id),
                user_id=str(user_id),
                enable=enable,
            )
        )

    async def set_group_ban(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        duration: int | float = 0,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_ban",
                group_id=str(group_id),
                user_id=str(user_id),
                duration=float(duration),
            )
        )

    async def set_group_card(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        card: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_card",
                group_id=str(group_id),
                user_id=str(user_id),
                card=card,
            )
        )

    async def set_group_kick(
        self,
        *,
        group_id: int | str,
        user_id: int | str,
        reject_add_request: bool | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_kick",
                group_id=str(group_id),
                user_id=str(user_id),
                reject_add_request=reject_add_request,
            )
        )

    async def set_group_kick_members(
        self,
        *,
        group_id: int | str,
        user_ids: list[int | str],
        reject_add_request: bool | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_kick_members",
                group_id=str(group_id),
                user_id=[str(user_id) for user_id in user_ids],
                reject_add_request=reject_add_request,
            )
        )

    async def set_group_leave(
        self,
        *,
        group_id: int | str,
        is_dismiss: bool | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_leave",
                group_id=str(group_id),
                is_dismiss=is_dismiss,
            )
        )

    async def set_group_whole_ban(
        self,
        *,
        group_id: int | str,
        enable: bool = True,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_group_whole_ban",
                group_id=str(group_id),
                enable=enable,
            )
        )

    async def set_essence_message(
        self,
        *,
        message_id: int | float | str,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action("set_essence_msg", message_id=message_id)
        )

    async def delete_essence_message(
        self,
        *,
        message_id: int | float | str | None = None,
        msg_seq: str | None = None,
        msg_random: str | None = None,
        group_id: int | str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "delete_essence_msg",
                message_id=message_id,
                msg_seq=msg_seq,
                msg_random=msg_random,
                group_id=str(group_id) if group_id is not None else None,
            )
        )

    async def send_like(
        self,
        *,
        user_id: int | str,
        times: int | float = 1,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_like",
                user_id=str(user_id),
                times=float(times),
            )
        )

    async def friend_poke(
        self,
        *,
        user_id: int | str,
        group_id: int | str | None = None,
        target_id: int | str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "friend_poke",
                user_id=str(user_id),
                group_id=str(group_id) if group_id is not None else None,
                target_id=str(target_id) if target_id is not None else None,
            )
        )

    async def group_poke(
        self,
        *,
        user_id: int | str,
        group_id: int | str | None = None,
        target_id: int | str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "group_poke",
                user_id=str(user_id),
                group_id=str(group_id) if group_id is not None else None,
                target_id=str(target_id) if target_id is not None else None,
            )
        )

    async def send_group_notice(
        self,
        *,
        group_id: int | str,
        content: str,
        pinned: int | float | None = None,
        type_: int | float | None = None,
        confirm_required: int | float | None = None,
        is_show_edit_card: int | float | None = None,
        tip_window_type: int | float | None = None,
        image: str | None = None,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_group_notice",
                group_id=str(group_id),
                content=content,
                pinned=float(pinned) if pinned is not None else 0.0,
                type=float(type_) if type_ is not None else 1.0,
                confirm_required=(
                    float(confirm_required) if confirm_required is not None else 1.0
                ),
                is_show_edit_card=(
                    float(is_show_edit_card) if is_show_edit_card is not None else 0.0
                ),
                tip_window_type=(
                    float(tip_window_type) if tip_window_type is not None else 0.0
                ),
                image=image,
            )
        )

    async def set_input_status(
        self,
        *,
        user_id: int | str,
        event_type: int | float = 1,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "set_input_status",
                user_id=str(user_id),
                event_type=int(event_type),
            )
        )

    async def get_group_msg_history(
        self,
        *,
        group_id: int | str,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._get_message_history(
            operation="get_group_msg_history",
            base_params={"group_id": str(group_id)},
            count=count,
            message_seq=message_seq,
        )

    async def get_friend_msg_history(
        self,
        *,
        user_id: int | str,
        count: int = 20,
        message_seq: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._get_message_history(
            operation="get_friend_msg_history",
            base_params={"user_id": str(user_id)},
            count=count,
            message_seq=message_seq,
        )

    async def fetch_custom_face(self, *, count: int = 48) -> list[Any]:
        payload = await self.call_action("fetch_custom_face", count=int(count))
        data = self._require_data("fetch_custom_face", payload)
        if not isinstance(data, list):
            raise NapCatTransportError(
                "fetch_custom_face",
                "successful response did not contain a custom face list",
            )
        return data

    async def get_ai_characters(
        self,
        *,
        group_id: int | str,
        chat_type: int | float = 1,
    ) -> list[Any]:
        payload = await self.call_action(
            "get_ai_characters",
            group_id=str(group_id),
            chat_type=int(chat_type),
        )
        data = self._require_data("get_ai_characters", payload)
        if not isinstance(data, list):
            raise NapCatTransportError(
                "get_ai_characters",
                "successful response did not contain an AI character list",
            )
        return data

    async def send_group_ai_record(
        self,
        *,
        group_id: int | str,
        character: str,
        text: str,
        chat_type: int | float = 1,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        return self._build_action_payload(
            await self.call_action(
                "send_group_ai_record",
                group_id=str(group_id),
                character=character,
                text=text,
            )
        )

    async def set_friend_add_request(
        self,
        *,
        flag: str,
        approve: bool = True,
        remark: str | None = None,
    ) -> None:
        self._require_success_payload(
            "set_friend_add_request",
            await self.call_action(
                "set_friend_add_request",
                flag=flag,
                approve=approve,
                remark=remark,
            ),
        )

    async def set_group_add_request(
        self,
        *,
        flag: str,
        approve: bool = True,
        reason: str | None = None,
        count: float | None = None,
    ) -> None:
        self._require_success_payload(
            "set_group_add_request",
            await self.call_action(
                "set_group_add_request",
                flag=flag,
                approve=approve,
                reason=reason,
                count=float(count) if count is not None else None,
            ),
        )

    def _normalize_message(self, message: Any) -> Any:
        if isinstance(message, str):
            return message
        if isinstance(message, Sequence) and not isinstance(
            message, str | bytes | bytearray
        ):
            normalized: list[Any] = []
            for item in message:
                if isinstance(item, str):
                    normalized.append(self.text(item).to_dict())
                elif hasattr(item, "to_dict") and callable(item.to_dict):
                    normalized.append(item.to_dict())
                else:
                    normalized.append(item)
            return normalized
        if hasattr(message, "to_dict") and callable(message.to_dict):
            return message.to_dict()
        return message

    def _require_data_dict(
        self, operation: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._require_data(operation, payload)
        if not isinstance(data, dict):
            raise NapCatTransportError(
                operation,
                "successful response did not contain object data payload",
            )
        return data

    def _require_data(self, operation: str, payload: dict[str, Any]) -> Any:
        if not isinstance(payload, dict):
            raise NapCatTransportError(
                operation,
                f"action returned non-object payload: {type(payload).__name__}",
            )
        self._require_success_payload(operation, payload)
        if "data" not in payload:
            raise NapCatTransportError(
                operation,
                "successful response did not contain data payload",
            )
        return payload.get("data")

    async def _get_message_history(
        self,
        *,
        operation: str,
        base_params: dict[str, str],
        count: int,
        message_seq: int | str | None,
    ) -> list[dict[str, Any]]:
        page_size = 200
        total_needed = max(1, min(int(count), 999))

        def _build_params(
            seq: int | str | None,
            *,
            reverse_order: bool,
        ) -> dict[str, Any]:
            params: dict[str, Any] = dict(base_params)
            if seq is not None:
                params["message_seq"] = seq
            params["count"] = min(page_size, total_needed)
            params["reverse_order"] = reverse_order
            params["reverseOrder"] = reverse_order
            params["disable_get_url"] = False
            params["parse_mult_msg"] = True
            params["quick_reply"] = False
            return params

        async def _fetch_page(
            seq: int | str | None,
            *,
            reverse_order: bool,
        ) -> list[dict[str, Any]]:
            payload = await self.call_action(
                operation,
                **_build_params(seq, reverse_order=reverse_order),
            )
            return self._extract_message_history_items(operation, payload)

        if message_seq is not None:
            return await _fetch_page(message_seq, reverse_order=False)

        batch = await _fetch_page(None, reverse_order=False)
        if not batch:
            return []

        all_messages = list(batch)
        newest_id = max(self._history_message_id(item) for item in batch)

        while newest_id > 0:
            newer_batch = await _fetch_page(newest_id, reverse_order=False)
            if not newer_batch:
                break
            new_items = newer_batch
            if self._history_message_id(newer_batch[0]) == newest_id:
                new_items = newer_batch[1:]
            if not new_items:
                break
            all_messages.extend(new_items)
            newest_id = max(self._history_message_id(item) for item in new_items)

        while len(all_messages) < total_needed:
            oldest_id = self._history_message_id(all_messages[0])
            if oldest_id <= 0:
                break
            older_batch = await _fetch_page(oldest_id, reverse_order=True)
            if not older_batch:
                break
            older_items = older_batch
            if self._history_message_id(older_batch[-1]) == oldest_id:
                older_items = older_batch[:-1]
            if not older_items:
                break
            all_messages = list(reversed(older_items)) + all_messages
            if len(older_batch) < page_size:
                break

        return all_messages[-total_needed:]

    def _extract_message_history_items(
        self,
        operation: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self._require_success_payload(operation, payload)

        messages = payload.get("messages")
        if isinstance(messages, list):
            return [item for item in messages if isinstance(item, dict)]

        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            nested_messages = data.get("messages")
            if isinstance(nested_messages, list):
                return [item for item in nested_messages if isinstance(item, dict)]

        raise NapCatTransportError(
            operation,
            "successful response did not contain a message history list",
        )

    def _history_message_id(self, item: Mapping[str, Any]) -> int:
        return _coerce_int(item.get("message_id")) or 0

    def _require_success_payload(self, operation: str, payload: dict[str, Any]) -> None:
        status = payload.get("status")
        retcode = _coerce_int(payload.get("retcode"))
        message = payload.get("message")
        wording = payload.get("wording")

        if status != "ok" or retcode not in (None, 0):
            raise NapCatApiError(
                operation,
                status=str(status) if status is not None else None,
                retcode=retcode,
                message=str(message) if isinstance(message, str) else None,
                wording=str(wording) if isinstance(wording, str) else None,
            )

    def _build_send_result(
        self, operation: str, payload: dict[str, Any]
    ) -> NapCatSendMessageResult:
        data = self._require_data_dict(operation, payload)
        message_id = _coerce_int(data.get("message_id"))
        if message_id is None:
            raise NapCatTransportError(
                operation,
                "successful response did not contain message_id",
            )
        return NapCatSendMessageResult(
            message_id=message_id,
            res_id=_string_or_none(data.get("res_id")),
            forward_id=_string_or_none(data.get("forward_id")),
            extra={
                key: value
                for key, value in data.items()
                if key not in {"message_id", "res_id", "forward_id"}
            },
        )

    def _build_action_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_success_payload("action", payload)
        result = {
            "status": cast(str, payload.get("status", "ok")),
            "retcode": _coerce_int(payload.get("retcode")) or 0,
            "data": payload.get("data"),
        }
        if isinstance(payload.get("message"), str):
            result["message"] = payload["message"]
        if isinstance(payload.get("wording"), str):
            result["wording"] = payload["wording"]
        return result
