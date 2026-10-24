"""PDF 文件解析器

支持解析 PDF 文件中的文本和图片资源。
"""

import io

from pypdf import PdfReader

from astrbot.core.knowledge_base.parsers.base import (
    BaseParser,
    MediaItem,
    ParseResult,
)


class PDFParser(BaseParser):
    """PDF 文档解析器

    提取 PDF 中的文本内容和嵌入的图片资源。
    """

    @staticmethod
    def _extract_text_parts(reader: PdfReader) -> list[str]:
        text_parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return text_parts

    @staticmethod
    def _resolve_image_format(filter_type: object) -> tuple[str, str] | None:
        if isinstance(filter_type, str):
            filters: list[object] = [filter_type]
        else:
            try:
                filters = list(filter_type)  # type: ignore[arg-type]
            except TypeError:
                filters = [filter_type]
        if "/DCTDecode" in filters:
            return "jpg", "image/jpeg"
        if "/JPXDecode" in filters:
            return "jp2", "image/jp2"
        return None

    @staticmethod
    def _iter_page_xobjects(page) -> list:
        if "/Resources" not in page:
            return []
        resources = page["/Resources"]
        if not resources or "/XObject" not in resources:  # type: ignore
            return []
        xobjects = resources["/XObject"].get_object()  # type: ignore
        if not xobjects:
            return []
        return [xobjects[obj_name] for obj_name in xobjects]

    def _extract_page_media_items(
        self, page, page_num: int, image_counter: int
    ) -> tuple[list[MediaItem], int]:
        media_items: list[MediaItem] = []
        for obj in self._iter_page_xobjects(page):
            media_item = self._build_media_item(
                obj,
                page_num=page_num,
                image_counter=image_counter + 1,
            )
            if media_item is None:
                continue
            image_counter += 1
            media_items.append(media_item)
        return media_items, image_counter

    def _build_media_item(
        self,
        obj,
        *,
        page_num: int,
        image_counter: int,
    ) -> MediaItem | None:
        try:
            if obj.get("/Subtype") != "/Image":
                return None
            image_format = self._resolve_image_format(obj.get("/Filter", ""))
            if image_format is None:
                return None
            ext, mime_type = image_format
            image_data = obj.get_data()
        except Exception:
            return None
        return MediaItem(
            media_type="image",
            file_name=f"page_{page_num}_img_{image_counter}.{ext}",
            content=image_data,
            mime_type=mime_type,
        )

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        """解析 PDF 文件

        Args:
            file_content: 文件内容
            file_name: 文件名

        Returns:
            ParseResult: 包含文本和图片的解析结果

        """
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        text_parts = self._extract_text_parts(reader)
        media_items: list[MediaItem] = []
        image_counter = 0
        for page_num, page in enumerate(reader.pages):
            try:
                page_media_items, image_counter = self._extract_page_media_items(
                    page, page_num, image_counter
                )
                media_items.extend(page_media_items)
            except Exception:
                # 页面处理失败不影响其他页面
                pass

        full_text = "\n\n".join(text_parts)
        return ParseResult(text=full_text, media=media_items)
