import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from astrbot import logger
from astrbot.core.utils.error_redaction import safe_error

from .parsers.url_parser import extract_text_from_url

_MAX_CANONICAL_URL_LENGTH = 2048


def get_tavily_keys(config: dict[str, Any]) -> list[str]:
    """Read Tavily API keys from provider config.

    Args:
        config: Provider configuration dictionary.

    Returns:
        Configured Tavily keys.

    Raises:
        ValueError: If no Tavily key is configured.
    """

    tavily_keys = config.get("provider_settings", {}).get("websearch_tavily_key", [])
    if tavily_keys:
        return tavily_keys
    raise ValueError("Error: Tavily API key is not configured in provider_settings.")


async def extract_url_content(
    *,
    url: str,
    tavily_keys: list[str],
    progress_callback: Any = None,
) -> str:
    """Extract text content from a URL with progress reporting.

    Args:
        url: Source URL.
        tavily_keys: Tavily API keys.
        progress_callback: Optional progress callback.

    Returns:
        Extracted page content.

    Raises:
        OSError: If extraction fails.
        ValueError: If extraction returns no content.
    """

    if progress_callback:
        await progress_callback("extracting", 0, 100)

    try:
        text_content = await extract_text_from_url(url, tavily_keys)
    except Exception as exc:
        logger.error("Failed to extract content from URL: %s", safe_error("", exc))
        raise OSError("Failed to extract content from URL") from exc

    if not text_content:
        raise ValueError("No content extracted from URL")

    if progress_callback:
        await progress_callback("extracting", 100, 100)

    return text_content


def canonical_url(url: str) -> str:
    """Return the canonical http(s) URL used as a document identity.

    Args:
        url: Operator-supplied URL.

    Returns:
        Canonical URL with a lowercase host, no fragment, and sorted query.

    Raises:
        ValueError: If the URL is not http(s) or the canonical form exceeds 2048
            characters.
    """
    parts = urlsplit(str(url).strip())
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")
    hostname = (parts.hostname or "").lower()
    if not hostname:
        raise ValueError("URL host is missing.")
    port = parts.port
    drop_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is None or drop_port:
        netloc = host
    else:
        netloc = f"{host}:{port}"
    path = parts.path if parts.path else "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    if len(canonical) > _MAX_CANONICAL_URL_LENGTH:
        raise ValueError("URL is too long.")
    return canonical


def url_identity_key(canonical: str) -> str:
    """Build a URL identity key from a canonical URL.

    Args:
        canonical: Canonical URL string.

    Returns:
        ``url:sha256:{digest}``.
    """
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"url:sha256:{digest}"


def hash_extracted_text(text: str) -> str:
    """Hash extracted URL text before cleaning.

    Args:
        text: Extracted page text.

    Returns:
        SHA-256 hex digest of the UTF-8 text.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_url_document_name(url: str) -> str:
    """Build a synthetic file name for URL-based uploads.

    Args:
        url: Source URL.

    Returns:
        Derived file name with a fallback ``.url`` suffix.
    """
    try:
        path = urlsplit(canonical_url(url)).path.rstrip("/")
    except ValueError:
        path = ""
    file_name = path.split("/")[-1] if path else "document"
    if Path(file_name).suffix:
        return file_name
    return f"{file_name}.url"
