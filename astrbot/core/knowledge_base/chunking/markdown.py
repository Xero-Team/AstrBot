"""Markdown 感知分块器

根据 Markdown 标题层级结构进行分块，保持每个章节的语义完整性。
对于超过 chunk_size 的章节，内部使用递归字符分割。
"""

import re
from dataclasses import dataclass
from typing import TypedDict

from .base import BaseChunker
from .recursive import RecursiveCharacterChunker


@dataclass
class _Section:
    """解析后的 Markdown 章节"""

    heading_path: list[str]
    text: str
    has_body: bool


class _Heading(TypedDict):
    level: int
    title: str
    start: int
    end: int


class _HeadingPathItem(TypedDict):
    level: int
    title: str


class MarkdownChunker(BaseChunker):
    """Markdown 感知分块器

    按照 Markdown 标题层级切分文档，每个章节作为独立的 chunk。
    如果某个章节内容超过 chunk_size，则在该章节内部进行递归分割。
    子章节可选继承父级标题作为上下文前缀。
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 50,
        include_heading_context: bool = True,
        max_heading_depth: int = 4,
        min_chunk_size: int = 0,
        continuation_prefix: str = "...",
    ) -> None:
        """初始化 Markdown 分块器

        Args:
            chunk_size: 每个 chunk 的最大字符数
            chunk_overlap: 递归分割时的重叠字符数
            include_heading_context: 是否在子章节 chunk 前附加父级标题路径
            max_heading_depth: 最大识别的标题深度 (1-6)
            min_chunk_size: 最小 chunk 大小，低于此值的相邻同级 chunk 会被合并
            continuation_prefix: 续接 chunk 的前缀标记（默认 "..."）

        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_heading_context = include_heading_context
        # 限制 max_heading_depth 在 1-6 之间，防止无效值导致正则错误
        self.max_heading_depth = max(1, min(int(max_heading_depth), 6))
        self.min_chunk_size = min_chunk_size
        self.continuation_prefix = continuation_prefix
        self._fallback_chunker = RecursiveCharacterChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def chunk(self, text: str, **kwargs) -> list[str]:
        """按 Markdown 标题层级分块

        Args:
            text: Markdown 格式的输入文本
            chunk_size: 覆盖默认的 chunk 大小
            chunk_overlap: 覆盖默认的重叠大小

        Returns:
            list[str]: 分块后的文本列表

        """
        if not text or not text.strip():
            return []

        chunk_size = kwargs.get("chunk_size", self.chunk_size)
        chunk_overlap = kwargs.get("chunk_overlap", self.chunk_overlap)

        # 解析 Markdown 结构
        sections = self._parse_sections(text)

        if not sections:
            # 没有识别到标题结构，回退到递归分割
            return await self._fallback_chunker.chunk(
                text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

        # 将 sections 转换为 raw chunks
        raw_chunks = await self._sections_to_chunks(sections, chunk_size, chunk_overlap)

        # 合并纯标题节到下一个有内容的 chunk
        merged = self._merge_heading_only_chunks(raw_chunks, chunk_size)

        # 合并过短的相邻 chunk
        merged = self._merge_short_chunks(merged, chunk_size)

        return merged

    def _estimate_prefix_length(self, heading_path: list[str]) -> int:
        """估算标题上下文前缀的最大长度（用于扣除子块可用空间）"""
        if not self.include_heading_context or not heading_path:
            return 0
        title = " > ".join(heading_path)
        # 续接前缀格式: "{continuation_prefix} {title}\n\n"
        continuation = f"{self.continuation_prefix} {title}\n\n"
        return len(continuation)

    async def _sections_to_chunks(
        self, sections: list[_Section], chunk_size: int, chunk_overlap: int
    ) -> list[tuple[str, bool]]:
        """将解析后的 sections 转换为 (chunk_text, has_body) 列表"""
        raw_chunks: list[tuple[str, bool]] = []

        for section in sections:
            section_text = section.text
            heading_path = section.heading_path
            has_body = section.has_body

            # 构建带上下文的文本
            context_prefix = self._build_context_prefix(heading_path)
            full_text = context_prefix + section_text

            if len(full_text) <= chunk_size:
                raw_chunks.append((full_text.strip(), has_body))
            else:
                # 章节过长，内部递归分割
                # 扣除前缀长度，确保添加前缀后不超过 chunk_size
                prefix_len = self._estimate_prefix_length(heading_path)
                effective_chunk_size = max(chunk_size // 4, chunk_size - prefix_len)
                effective_chunk_size = max(effective_chunk_size, 1)
                effective_overlap = min(
                    chunk_overlap,
                    max(0, effective_chunk_size - 1),
                )

                sub_chunks = await self._fallback_chunker.chunk(
                    section_text,
                    chunk_size=effective_chunk_size,
                    chunk_overlap=effective_overlap,
                )
                for i, sub_chunk in enumerate(sub_chunks):
                    chunk_text = self._apply_heading_context(
                        heading_path,
                        sub_chunk,
                        is_continuation=(i > 0),
                        chunk_size=chunk_size,
                    )
                    raw_chunks.append((chunk_text, True))

        return raw_chunks

    def _build_context_prefix(self, heading_path: list[str]) -> str:
        """构建标题路径前缀"""
        if self.include_heading_context and heading_path:
            return " > ".join(heading_path) + "\n\n"
        return ""

    def _apply_heading_context(
        self,
        heading_path: list[str],
        content: str,
        is_continuation: bool,
        chunk_size: int,
    ) -> str:
        """为 chunk 内容添加标题上下文，且不突破 chunk_size。"""
        if not self.include_heading_context or not heading_path:
            return content.strip()

        title = " > ".join(heading_path)
        marker = f"{self.continuation_prefix} " if is_continuation else ""
        prefix = f"{marker}{title}\n\n"
        excess = len(prefix) + len(content) - chunk_size
        if excess > 0:
            if excess >= len(title):
                return content.strip()
            title = title[:-excess]
            prefix = f"{marker}{title}\n\n"
        return f"{prefix}{content}".strip()

    def _merge_heading_only_chunks(
        self, raw_chunks: list[tuple[str, bool]], chunk_size: int
    ) -> list[str]:
        """合并没有实质正文的 chunk 到下一个有正文的 chunk"""
        merged: list[str] = []
        pending = ""

        for chunk_text, has_body in raw_chunks:
            if not chunk_text:
                continue
            if not has_body:
                pending = self._append_pending_heading_chunk(
                    merged,
                    pending,
                    chunk_text,
                    chunk_size,
                )
                continue
            pending = self._append_chunk_with_pending(
                merged,
                pending,
                chunk_text,
                chunk_size,
            )

        self._flush_pending_heading_chunk(merged, pending, chunk_size)
        return [chunk for chunk in merged if chunk.strip()]

    def _merge_short_chunks(self, chunks: list[str], chunk_size: int) -> list[str]:
        """合并过短的相邻 chunk（低于 min_chunk_size）"""
        if self.min_chunk_size <= 0 or len(chunks) <= 1:
            return chunks

        final: list[str] = []
        buf = ""

        for c in chunks:
            if buf:
                buf = self._merge_buffered_short_chunk(final, buf, c, chunk_size)
                continue
            if len(c) < self.min_chunk_size:
                buf = c
                continue
            final.append(c)

        if buf:
            self._flush_short_chunk_buffer(final, buf, chunk_size)

        return final

    def _append_pending_heading_chunk(
        self,
        merged: list[str],
        pending: str,
        chunk_text: str,
        chunk_size: int,
    ) -> str:
        if pending and len(pending) + len(chunk_text) + 2 > chunk_size:
            merged.append(pending.strip())
            pending = ""
        return pending + chunk_text + "\n\n"

    def _append_chunk_with_pending(
        self,
        merged: list[str],
        pending: str,
        chunk_text: str,
        chunk_size: int,
    ) -> str:
        if not pending:
            merged.append(chunk_text.strip())
            return ""
        combined = pending + chunk_text
        if len(combined) <= chunk_size:
            merged.append(combined.strip())
        else:
            merged.append(pending.strip())
            merged.append(chunk_text.strip())
        return ""

    def _flush_pending_heading_chunk(
        self,
        merged: list[str],
        pending: str,
        chunk_size: int,
    ) -> None:
        if not pending:
            return
        pending_text = pending.strip()
        if merged and len(merged[-1] + "\n\n" + pending_text) <= chunk_size:
            merged[-1] = merged[-1] + "\n\n" + pending_text
            return
        merged.append(pending_text)

    def _merge_buffered_short_chunk(
        self,
        final_chunks: list[str],
        buffered_chunk: str,
        chunk_text: str,
        chunk_size: int,
    ) -> str:
        combined = buffered_chunk + "\n\n" + chunk_text
        if len(combined) <= chunk_size:
            return combined
        final_chunks.append(buffered_chunk)
        if len(chunk_text) < self.min_chunk_size:
            return chunk_text
        final_chunks.append(chunk_text)
        return ""

    @staticmethod
    def _flush_short_chunk_buffer(
        final_chunks: list[str],
        buffered_chunk: str,
        chunk_size: int,
    ) -> None:
        if (
            final_chunks
            and len(final_chunks[-1] + "\n\n" + buffered_chunk) <= chunk_size
        ):
            final_chunks[-1] = final_chunks[-1] + "\n\n" + buffered_chunk
            return
        final_chunks.append(buffered_chunk)

    def _parse_sections(self, text: str) -> list[_Section]:
        """解析 Markdown 文本为章节列表

        会跳过围栏代码块（``` 或 ~~~）内的内容，避免误匹配代码中的 # 字符。

        Returns:
            list[_Section]: 章节列表

        """
        # 先标记围栏代码块的范围，解析时跳过
        fenced_ranges = self._find_fenced_code_ranges(text)

        headings = self._collect_headings(text, fenced_ranges)

        if not headings:
            return []

        sections: list[_Section] = []

        # 处理第一个标题之前的内容（如果有）
        preamble = text[: headings[0]["start"]].strip()
        if preamble:
            sections.append(_Section(heading_path=[], text=preamble, has_body=True))

        # 维护标题栈来追踪层级路径
        heading_stack: list[_HeadingPathItem] = []

        for index, heading in enumerate(headings):
            self._update_heading_stack(heading_stack, heading)
            sections.append(
                self._build_section(
                    text=text,
                    headings=headings,
                    index=index,
                    heading=heading,
                    heading_stack=heading_stack,
                )
            )

        return sections

    def _collect_headings(
        self,
        text: str,
        fenced_ranges: list[tuple[int, int]],
    ) -> list[_Heading]:
        heading_pattern = re.compile(
            r"^(#{1," + str(self.max_heading_depth) + r"})(?:[ \t]+(.+))?[ \t]*$",
            re.MULTILINE,
        )
        headings: list[_Heading] = []
        for match in heading_pattern.finditer(text):
            if self._is_in_fenced_block(match.start(), fenced_ranges):
                continue
            headings.append(
                {
                    "level": len(match.group(1)),
                    "title": (match.group(2) or "").strip(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        return headings

    @staticmethod
    def _update_heading_stack(
        heading_stack: list[_HeadingPathItem],
        heading: _Heading,
    ) -> None:
        while heading_stack and heading_stack[-1]["level"] >= heading["level"]:
            heading_stack.pop()
        heading_stack.append({"level": heading["level"], "title": heading["title"]})

    @staticmethod
    def _build_section(
        text: str,
        headings: list[_Heading],
        index: int,
        heading: _Heading,
        heading_stack: list[_HeadingPathItem],
    ) -> _Section:
        content_start = heading["end"]
        content_end = (
            headings[index + 1]["start"] if index + 1 < len(headings) else len(text)
        )
        heading_line = text[heading["start"] : heading["end"]]
        body = text[content_start:content_end].strip()
        section_text = heading_line if not body else heading_line + "\n" + body
        return _Section(
            heading_path=[item["title"] for item in heading_stack[:-1]],
            text=section_text,
            has_body=bool(body),
        )

    @staticmethod
    def _find_fenced_code_ranges(text: str) -> list[tuple[int, int]]:
        """找到所有围栏代码块的 (start, end) 范围"""
        ranges: list[tuple[int, int]] = []
        fence_pattern = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)
        matches = list(fence_pattern.finditer(text))

        i = 0
        while i < len(matches):
            open_match = matches[i]
            open_fence = open_match.group(1)
            fence_char = open_fence[0]
            fence_len = len(open_fence)

            # 找到对应的关闭围栏
            for j in range(i + 1, len(matches)):
                close_match = matches[j]
                close_fence = close_match.group(1)
                if close_fence[0] == fence_char and len(close_fence) >= fence_len:
                    ranges.append((open_match.start(), close_match.end()))
                    i = j + 1
                    break
            else:
                # 没有找到关闭围栏，剩余部分都视为代码块
                ranges.append((open_match.start(), len(text)))
                break
            continue

        return ranges

    @staticmethod
    def _is_in_fenced_block(pos: int, ranges: list[tuple[int, int]]) -> bool:
        """判断给定位置是否在围栏代码块内"""
        for start, end in ranges:
            if start <= pos < end:
                return True
        return False
