"""Pluggable document extraction through an external Apache Tika server.

Operators can point AstrBot at a Tika (or Tika-compatible) service instead of
bundling heavy extraction models. The parser sends the raw file to the server's
``/tika`` endpoint and returns the plain-text response.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult

_MAX_TIKA_RESPONSE_BYTES = 16 * 1024 * 1024


class TikaParser(BaseParser):
    """Extract text from any document by calling an external Tika server."""

    def __init__(self, base_url: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        """Extract text by POSTing the file to the configured Tika server.

        Args:
            file_content: Raw file bytes.
            file_name: Original file name, sent as ``resourceName`` metadata.

        Returns:
            ParseResult with the server's plain-text response and no media.

        Raises:
            RuntimeError: If the server rejects the request or is unreachable.
        """
        url = f"{self.base_url}/tika"
        headers = {
            "Accept": "text/plain",
            "Content-Type": "application/octet-stream",
            "Content-Disposition": _content_disposition(_safe_name(file_name)),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "PUT",
                    url,
                    content=file_content,
                    headers=headers,
                ) as response:
                    if response.status_code >= 400:
                        raise RuntimeError(
                            f"Tika extraction failed with status {response.status_code}"
                        )
                    content = await _read_bounded(response)
        except httpx.HTTPError as exc:
            raise RuntimeError("Tika extraction service is unreachable") from exc

        return ParseResult(text=content.decode("utf-8", errors="replace"), media=[])


async def _read_bounded(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        if not chunk or total >= _MAX_TIKA_RESPONSE_BYTES:
            break
        remaining = _MAX_TIKA_RESPONSE_BYTES - total
        chunks.append(chunk[:remaining])
        total += min(len(chunk), remaining)
    return b"".join(chunks)


def _safe_name(file_name: str) -> str:
    return (
        file_name.replace('"', "")
        .replace("\\", "")
        .replace("\r", "")
        .replace("\n", "")[:200]
    )


def _content_disposition(file_name: str) -> str:
    fallback = file_name.encode("ascii", "replace").decode("ascii").replace("?", "_")
    encoded = quote(file_name, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
