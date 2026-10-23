from collections.abc import Callable

from .base import BaseChunker


class RecursiveCharacterChunker(BaseChunker):
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        length_function: Callable[[str], int] = len,
        is_separator_regex: bool = False,
        separators: list[str] | None = None,
    ) -> None:
        """初始化递归字符文本分割器

        Args:
            chunk_size: 每个文本块的最大大小
            chunk_overlap: 每个文本块之间的重叠部分大小
            length_function: 计算文本长度的函数
            is_separator_regex: 分隔符是否为正则表达式
            separators: 用于分割文本的分隔符列表，按优先级排序

        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.is_separator_regex = is_separator_regex

        # 默认分隔符列表，按优先级从高到低
        self.separators = separators or [
            "\n\n",  # 段落
            "\n",  # 换行
            "。",  # 中文句子
            "，",  # 中文逗号
            ". ",  # 句子
            ", ",  # 逗号分隔
            " ",  # 单词
            "",  # 字符
        ]

    async def chunk(self, text: str, **kwargs) -> list[str]:
        """递归地将文本分割成块

        Args:
            text: 要分割的文本
            chunk_size: 每个文本块的最大大小
            chunk_overlap: 每个文本块之间的重叠部分大小

        Returns:
            分割后的文本块列表

        """
        if not text:
            return []

        overlap = kwargs.get("chunk_overlap", self.chunk_overlap)
        chunk_size = kwargs.get("chunk_size", self.chunk_size)

        text_length = self.length_function(text)
        if text_length <= chunk_size:
            return [text]

        for separator in self.separators:
            chunks = await self._chunk_with_separator(
                text,
                separator=separator,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            if chunks is not None:
                return chunks

        return [text]

    def _split_with_preserved_separator(self, text: str, separator: str) -> list[str]:
        splits = text.split(separator)
        return [part + separator for part in splits[:-1]] + [splits[-1]]

    def _build_overlap_state(
        self,
        combined_text: str,
        split: str,
        overlap: int,
    ) -> tuple[list[str], int]:
        overlap = min(overlap, max(0, len(split) - 1))
        overlap_start = max(0, len(combined_text) - overlap)
        if overlap_start <= 0:
            return [split], self.length_function(split)
        overlap_text = combined_text[overlap_start:]
        return [overlap_text, split], self.length_function(
            overlap_text
        ) + self.length_function(split)

    @staticmethod
    def _reset_chunk_state() -> tuple[list[str], int]:
        return [], 0

    async def _flush_current_chunk(
        self,
        final_chunks: list[str],
        current_chunk: list[str],
        *,
        chunk_size: int,
        overlap: int,
    ) -> tuple[list[str], int]:
        if current_chunk:
            final_chunks.extend(
                await self.chunk(
                    "".join(current_chunk),
                    chunk_size=chunk_size,
                    chunk_overlap=overlap,
                )
            )
        return self._reset_chunk_state()

    async def _append_recursive_split(
        self,
        final_chunks: list[str],
        split: str,
        *,
        chunk_size: int,
        overlap: int,
    ) -> None:
        final_chunks.extend(
            await self.chunk(
                split,
                chunk_size=chunk_size,
                chunk_overlap=overlap,
            )
        )

    async def _chunk_with_separator(
        self,
        text: str,
        separator: str,
        chunk_size: int,
        overlap: int,
    ) -> list[str] | None:
        if separator == "":
            return self._split_by_character(text, chunk_size, overlap)
        splits = self._get_separator_splits(text, separator, chunk_size, overlap)
        if splits is None:
            return None
        final_chunks: list[str] = []
        current_chunk: list[str] = []
        current_chunk_length = 0

        for split in splits:
            split_length = self.length_function(split)
            if split_length > chunk_size:
                current_chunk, current_chunk_length = await self._flush_current_chunk(
                    final_chunks,
                    current_chunk,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                await self._append_recursive_split(
                    final_chunks,
                    split,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                continue
            if current_chunk_length + split_length > chunk_size:
                combined_text = "".join(current_chunk)
                final_chunks.append(combined_text)
                current_chunk, current_chunk_length = self._build_overlap_state(
                    combined_text,
                    split,
                    overlap,
                )
                continue
            current_chunk.append(split)
            current_chunk_length += split_length

        if current_chunk:
            final_chunks.append("".join(current_chunk))
        return final_chunks

    def _get_separator_splits(
        self,
        text: str,
        separator: str,
        chunk_size: int,
        overlap: int,
    ) -> list[str] | None:
        if separator not in text:
            return None
        splits = [
            split
            for split in self._split_with_preserved_separator(text, separator)
            if split
        ]
        if len(splits) == 1:
            return None
        return splits

    def _split_by_character(
        self,
        text: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[str]:
        """按字符级别分割文本

        Args:
            text: 要分割的文本

        Returns:
            分割后的文本块列表

        """
        chunk_size, overlap = self._resolve_character_split_params(
            chunk_size,
            overlap,
        )
        result = []
        for i in range(0, len(text), chunk_size - overlap):
            end = min(i + chunk_size, len(text))
            result.append(text[i:end])
            if end == len(text):
                break

        return result

    def _resolve_character_split_params(
        self,
        chunk_size: int | None,
        overlap: int | None,
    ) -> tuple[int, int]:
        chunk_size = self.chunk_size if chunk_size is None else chunk_size
        overlap = self.chunk_overlap if overlap is None else overlap
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return chunk_size, overlap
