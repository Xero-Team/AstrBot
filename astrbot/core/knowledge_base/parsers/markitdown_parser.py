import asyncio
import io
import os

from markitdown_no_magika import MarkItDown, StreamInfo

from astrbot.core.knowledge_base.parsers.base import (
    BaseParser,
    ParseResult,
)


class MarkitdownParser(BaseParser):
    """解析 docx, xls, xlsx 格式"""

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        def _convert() -> str:
            md = MarkItDown(enable_plugins=False)
            bio = io.BytesIO(file_content)
            stream_info = StreamInfo(
                extension=os.path.splitext(file_name)[1].lower(),
                filename=file_name,
            )
            return md.convert(bio, stream_info=stream_info).markdown

        return ParseResult(text=await asyncio.to_thread(_convert), media=[])
