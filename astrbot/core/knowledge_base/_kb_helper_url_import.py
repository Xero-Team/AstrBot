from pathlib import Path
from typing import Any

from astrbot.core import logger

from .parsers.url_parser import extract_text_from_url


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
        logger.error("Failed to extract content from URL %s: %s", url, exc)
        raise OSError(f"Failed to extract content from URL {url}: {exc}") from exc

    if not text_content:
        raise ValueError(f"No content extracted from URL: {url}")

    if progress_callback:
        await progress_callback("extracting", 100, 100)

    return text_content


def build_url_document_name(url: str) -> str:
    """Build a synthetic file name for URL-based uploads.

    Args:
        url: Source URL.

    Returns:
        Derived file name with a fallback ``.url`` suffix.
    """

    file_name = url.split("/")[-1] or f"document_from_{url}"
    if Path(file_name).suffix:
        return file_name
    return f"{file_name}.url"
