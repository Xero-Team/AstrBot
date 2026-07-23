"""WebChat response emission shared by the adapter and its message events."""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import uuid
from pathlib import Path, PurePosixPath

from astrbot import logger
from astrbot.core.message.components import File, Image, Json, Plain, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.media_utils import (
    MEDIA_MIME_EXTENSIONS,
    detect_image_mime_type_async,
)

from .queue_manager import WebChatQueueManager


async def emit_webchat_response(
    queue_manager: WebChatQueueManager,
    message_id: str,
    message: MessageChain | None,
    *,
    attachments_dir: str | Path,
    streaming: bool = False,
    emit_complete: bool = False,
) -> str | None:
    """Write a WebChat message chain to its request-scoped response queue.

    Args:
        queue_manager: Runtime-owned WebChat queue manager.
        message_id: Request identifier used by the transport protocol.
        message: Message chain to serialize, or ``None`` to finish the request.
        attachments_dir: Directory that receives generated attachment files.
        streaming: Whether the response belongs to a stream.
        emit_complete: Whether to append a ``complete`` payload after the chain.

    Returns:
        The final serialized payload text, if the request queue accepted it.
    """
    request_id = str(message_id)
    if not message:
        await queue_manager.put_back_queue(
            request_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": message_id,
            },
        )
        return None

    target_dir = Path(attachments_dir)
    await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)
    data = ""
    for comp in message.chain:
        if isinstance(comp, Plain):
            data = comp.text
            accepted = await queue_manager.put_back_queue(
                request_id,
                {
                    "type": "plain",
                    "data": data,
                    "streaming": streaming,
                    "chain_type": message.type,
                    "message_id": message_id,
                },
            )
            if not accepted:
                return None
        elif isinstance(comp, Json):
            if message.type == "llm_sources":
                raw_sources = comp.data if isinstance(comp.data, dict) else {}
                used: list[dict] = []
                used_by_url: dict[str, dict] = {}
                for item in [
                    *(raw_sources.get("citations", []) or []),
                    *(raw_sources.get("sources", []) or []),
                ]:
                    if not isinstance(item, dict):
                        continue
                    url = item.get("url")
                    if not isinstance(url, str) or not url:
                        continue
                    candidate = {
                        "url": url,
                        "title": item.get("title"),
                        "snippet": item.get("snippet"),
                        "start_index": item.get("start_index"),
                        "end_index": item.get("end_index"),
                        "source_type": item.get("source_type"),
                    }
                    existing = used_by_url.get(url)
                    if existing is None:
                        used_by_url[url] = candidate
                        used.append(candidate)
                        continue
                    for key, value in candidate.items():
                        if existing.get(key) is None and value is not None:
                            existing[key] = value
                accepted = await queue_manager.put_back_queue(
                    request_id,
                    {
                        "type": "refs",
                        "data": {"used": used},
                        "streaming": streaming,
                        "chain_type": message.type,
                        "message_id": message_id,
                    },
                )
                if not accepted:
                    return None
                continue
            accepted = await queue_manager.put_back_queue(
                request_id,
                {
                    "type": "plain",
                    "data": json.dumps(comp.data, ensure_ascii=False),
                    "streaming": streaming,
                    "chain_type": message.type,
                    "message_id": message_id,
                },
            )
            if not accepted:
                return None
        elif isinstance(comp, Image):
            image_base64 = await comp.convert_to_base64()
            image_bytes = base64.b64decode(image_base64)
            mime_type = await detect_image_mime_type_async(
                image_bytes,
                default_mime_type=None,
            )
            suffix = MEDIA_MIME_EXTENSIONS.get(mime_type or "", ".jpg")
            filename = f"{uuid.uuid4()!s}{suffix}"
            await asyncio.to_thread((target_dir / filename).write_bytes, image_bytes)
            data = f"[IMAGE]{filename}"
            accepted = await queue_manager.put_back_queue(
                request_id,
                {
                    "type": "image",
                    "data": data,
                    "streaming": streaming,
                    "message_id": message_id,
                },
            )
            if not accepted:
                return None
        elif isinstance(comp, Record):
            filename = f"{uuid.uuid4()!s}.wav"
            record_base64 = await comp.convert_to_base64()
            record_bytes = base64.b64decode(record_base64)
            await asyncio.to_thread((target_dir / filename).write_bytes, record_bytes)
            data = f"[RECORD]{filename}"
            accepted = await queue_manager.put_back_queue(
                request_id,
                {
                    "type": "record",
                    "data": data,
                    "streaming": streaming,
                    "message_id": message_id,
                },
            )
            if not accepted:
                return None
        elif isinstance(comp, File):
            file_path = await comp.get_file()
            raw_original_name = comp.name or Path(file_path).name
            original_name = (
                PurePosixPath(str(raw_original_name).replace("\\", "/"))
                .name.replace("\x00", "")
                .strip()
            )
            if original_name in {"", ".", ".."}:
                original_name = Path(file_path).name or "file"
            filename = f"{uuid.uuid4()!s}{Path(original_name).suffix}"
            await asyncio.to_thread(shutil.copy2, file_path, target_dir / filename)
            data = f"[FILE]{filename}|{original_name}"
            accepted = await queue_manager.put_back_queue(
                request_id,
                {
                    "type": "file",
                    "data": data,
                    "streaming": streaming,
                    "message_id": message_id,
                },
            )
            if not accepted:
                return None
        else:
            logger.debug("webchat ignores component type %s", comp.type)

    if emit_complete:
        await queue_manager.put_back_queue(
            request_id,
            {
                "type": "complete",
                "data": data,
                "streaming": streaming,
                "chain_type": message.type,
                "message_id": message_id,
            },
        )

    return data
