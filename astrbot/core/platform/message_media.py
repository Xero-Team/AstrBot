"""Delivery-scoped materialization of source-adapter media references."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import MediaResolver

from .message_i18n import DEFAULT_LOCALE, localize, localize_kind, localize_value
from .message_protocol import (
    ContentKind,
    MediaReference,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    NativeContent,
    PortablePart,
)


@asynccontextmanager
async def materialize_message_media(
    envelope: MessageEnvelope,
    capabilities: MessageDeliveryCapabilities,
    *,
    locale: str = DEFAULT_LOCALE,
) -> AsyncIterator[MessageEnvelope]:
    """Keep owned media files alive until all target submissions have finished.

    Adapter loaders resolve credentials and private file IDs at the source.
    Only filesystem references reach the target. Unsupported or unavailable
    attachments degrade in place without exposing their URI or credentials.
    """
    content: list[PortablePart | NativeContent] = []
    async with AsyncExitStack() as stack:
        directory: Path | None = None
        for index, part in enumerate(envelope.content):
            if (
                not isinstance(part, PortablePart)
                or not isinstance(part.value, MediaReference)
                or (
                    part.kind.value not in capabilities.media
                    and "file" not in capabilities.media
                )
            ):
                content.append(part)
                continue
            reference = part.value
            try:
                async with asyncio.timeout(60):
                    source = (
                        await reference.resolve_source()
                        if reference.resolve_source
                        else reference.uri
                    )
                    if not source:
                        raise ValueError("Media source is unavailable")
                    resolved = await stack.enter_async_context(
                        MediaResolver(source).as_path()
                    )
                    size = resolved.path.stat().st_size
                    limit = capabilities.max_media_size or 50 * 1024 * 1024
                    if size > limit:
                        raise ValueError("Media exceeds target limit")
                    if directory is None:
                        root = Path(get_astrbot_temp_path())
                        root.mkdir(parents=True, exist_ok=True)
                        directory = Path(
                            stack.enter_context(
                                TemporaryDirectory(prefix="bridge-", dir=root)
                            )
                        )
                    destination = directory / f"{index}{resolved.path.suffix}"
                    task = asyncio.create_task(
                        asyncio.to_thread(shutil.copyfile, resolved.path, destination)
                    )
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        # The worker must finish before its directory is removed.
                        await task
                        raise
                    content.append(
                        replace(
                            part,
                            value=replace(
                                reference,
                                uri=destination.as_uri(),
                                size=size,
                                resolve_source=None,
                            ),
                        )
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                label = (
                    localize_value(locale, part.alt_text)
                    if part.alt_text
                    else localize_kind(locale, part.kind.value)
                )
                content.append(
                    PortablePart(
                        ContentKind.TEXT,
                        localize(locale, "astrbot.msg.unavailable", label=label),
                    )
                )
        yield replace(envelope, content=tuple(content))


__all__ = ["materialize_message_media"]
