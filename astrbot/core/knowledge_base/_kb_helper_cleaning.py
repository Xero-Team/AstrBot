import asyncio
import re
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from astrbot.core import logger
from astrbot.core.provider.provider import Provider as LLMProvider

from .chunking.base import BaseChunker
from .chunking.recursive import RecursiveCharacterChunker
from .prompts import TEXT_REPAIR_SYSTEM_PROMPT

if TYPE_CHECKING:
    from astrbot.core.provider.manager import ProviderManager


class RateLimiter:
    """A minimal async rate limiter for chunk repair calls."""

    def __init__(self, max_rpm: int) -> None:
        self.max_per_minute = max_rpm
        self.interval = 60.0 / max_rpm if max_rpm > 0 else 0
        self.last_call_time = 0.0

    async def __aenter__(self) -> None:
        if self.interval == 0:
            return

        elapsed = time.monotonic() - self.last_call_time
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)

        self.last_call_time = time.monotonic()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None


async def repair_and_translate_chunk_with_retry(
    chunk: str,
    repair_llm_service: LLMProvider,
    rate_limiter: RateLimiter,
    max_retries: int = 2,
) -> list[str]:
    """Repair, translate, and normalize a chunk through the configured LLM.

    Args:
        chunk: Source chunk to repair.
        repair_llm_service: LLM provider used for repair.
        rate_limiter: Shared limiter controlling request pace.
        max_retries: Maximum retry count after the first attempt.

    Returns:
        Repaired chunk list, or the original chunk when every attempt fails.
    """

    user_prompt = f"""IGNORE ALL PREVIOUS INSTRUCTIONS. Your ONLY task is to process the following text chunk according to the system prompt provided.

Text chunk to process:
---
{chunk}
---
"""
    for attempt in range(max_retries + 1):
        try:
            async with rate_limiter:
                response = await repair_llm_service.text_chat(
                    prompt=user_prompt,
                    system_prompt=TEXT_REPAIR_SYSTEM_PROMPT,
                )
            repaired_chunks = _extract_repaired_chunks(response.completion_text)
            if repaired_chunks is not None:
                return repaired_chunks
        except Exception as exc:
            logger.warning(
                "  - LLM call failed on attempt %d/%d. Error: %s",
                attempt + 1,
                max_retries + 1,
                exc,
            )

    logger.error(
        "  - Failed to process chunk after %d attempts. Using original text.",
        max_retries + 1,
    )
    return [chunk]


def compact_chunks(chunks: list[str]) -> list[str]:
    """Strip and drop empty chunks.

    Args:
        chunks: Raw chunks.

    Returns:
        Compact non-empty chunks.
    """

    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


async def chunk_content_without_cleaning(
    *,
    content: str,
    chunker: BaseChunker,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Chunk content directly without running LLM-based cleaning.

    Args:
        content: Raw text content.
        chunker: Chunker instance to use.
        chunk_size: Desired chunk size.
        chunk_overlap: Desired chunk overlap.

    Returns:
        Generated chunks.
    """

    logger.info(
        "内容清洗未启用，使用指定参数进行分块: chunk_size=%d, chunk_overlap=%d",
        chunk_size,
        chunk_overlap,
    )
    return await chunker.chunk(
        content,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


async def get_cleaning_provider(
    provider_manager: ProviderManager,
    cleaning_provider_id: str,
) -> LLMProvider:
    """Resolve the cleaning provider.

    Args:
        provider_manager: Provider manager instance.
        cleaning_provider_id: Provider ID used for content cleaning.

    Returns:
        Resolved LLM provider.

    Raises:
        ValueError: If the provider is missing or has the wrong type.
    """

    llm_provider = await provider_manager.get_provider_by_id(cleaning_provider_id)
    if llm_provider and isinstance(llm_provider, LLMProvider):
        return llm_provider
    raise ValueError(
        f"无法找到 ID 为 {cleaning_provider_id} 的 LLM Provider 或类型不正确"
    )


async def repair_chunks_with_provider(
    *,
    content: str,
    llm_provider: LLMProvider,
    repair_max_rpm: int,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Repair chunks with an LLM after an initial recursive split.

    Args:
        content: Source text content.
        llm_provider: Cleaning provider.
        repair_max_rpm: Request-per-minute limit for repair calls.
        chunk_size: Initial chunk size.
        chunk_overlap: Initial chunk overlap.

    Returns:
        Final repaired chunk list.
    """

    text_splitter = RecursiveCharacterChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " "],
    )
    initial_chunks = await text_splitter.chunk(content)
    logger.info("初步分块完成，生成 %d 个块用于修复。", len(initial_chunks))

    rate_limiter = RateLimiter(repair_max_rpm)
    repaired_results = await asyncio.gather(
        *[
            repair_and_translate_chunk_with_retry(chunk, llm_provider, rate_limiter)
            for chunk in initial_chunks
        ],
        return_exceptions=True,
    )
    final_chunks = _merge_repaired_chunks(initial_chunks, repaired_results)
    logger.info(
        "文本修复完成: %d 个原始块 -> %d 个最终块。",
        len(initial_chunks),
        len(final_chunks),
    )
    return final_chunks


async def clean_and_rechunk_content(
    *,
    content: str,
    url: str,
    chunker: BaseChunker,
    provider_manager: ProviderManager,
    progress_callback: Any = None,
    report_progress: Any,
    enable_cleaning: bool = False,
    cleaning_provider_id: str | None = None,
    repair_max_rpm: int = 60,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[str]:
    """Clean and rechunk URL content with optional LLM-based repair.

    Args:
        content: Extracted raw URL text.
        url: Source URL for logging.
        chunker: Default chunker instance.
        provider_manager: Provider manager used to resolve the cleaning LLM.
        progress_callback: Optional progress callback.
        report_progress: Helper used to emit progress events.
        enable_cleaning: Whether cleaning is enabled.
        cleaning_provider_id: Selected cleaning provider ID.
        repair_max_rpm: Repair request rate limit.
        chunk_size: Desired chunk size.
        chunk_overlap: Desired chunk overlap.

    Returns:
        Final chunk list.
    """

    if not enable_cleaning:
        return await chunk_content_without_cleaning(
            content=content,
            chunker=chunker,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    if not cleaning_provider_id:
        logger.warning(
            "启用了内容清洗，但未提供 cleaning_provider_id，跳过清洗并使用默认分块。"
        )
        return await chunker.chunk(content)

    if progress_callback:
        await progress_callback("cleaning", 0, 100)

    try:
        llm_provider = await get_cleaning_provider(
            provider_manager,
            cleaning_provider_id,
        )
        final_chunks = await repair_chunks_with_provider(
            content=content,
            llm_provider=llm_provider,
            repair_max_rpm=repair_max_rpm,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        await report_progress(progress_callback, "cleaning", 100, 100)
        return final_chunks
    except Exception as exc:
        logger.error(
            "使用 Provider '%s' 清洗内容失败: %s. URL=%s",
            cleaning_provider_id,
            exc,
            url,
        )
        return await chunker.chunk(content)


def _extract_repaired_chunks(llm_output: str) -> list[str] | None:
    if "<discard_chunk />" in llm_output:
        return []

    matches = re.findall(
        r"<\s*repaired_text\s*>\s*(.*?)\s*<\s*/\s*repaired_text\s*>",
        llm_output,
        re.DOTALL,
    )
    if matches:
        return [match.strip() for match in matches if match.strip()]
    return []


def _merge_repaired_chunks(
    initial_chunks: list[str],
    repaired_results: Sequence[list[str] | BaseException],
) -> list[str]:
    final_chunks: list[str] = []
    for index, repaired_result in enumerate(repaired_results):
        if isinstance(repaired_result, Exception):
            logger.warning("块 %d 处理异常: %s. 回退到原始块。", index, repaired_result)
            final_chunks.append(initial_chunks[index])
            continue
        if isinstance(repaired_result, list):
            final_chunks.extend(repaired_result)
    return compact_chunks(final_chunks)
