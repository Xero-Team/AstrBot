from __future__ import annotations

import pytest

from astrbot.core.knowledge_base.parsers import ocr_parser, tika_parser
from astrbot.core.knowledge_base.parsers.ocr import OCREngineUnavailable
from astrbot.core.knowledge_base.parsers.ocr_parser import ImageOCRParser
from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser
from astrbot.core.knowledge_base.parsers.tika_parser import TikaParser
from astrbot.core.knowledge_base.parsers.util import select_parser


@pytest.mark.asyncio
async def test_select_parser_prefers_tika_when_configured() -> None:
    parser = await select_parser(
        ".pdf",
        extraction_config={"tika_url": "http://tika.local:9998"},
    )

    assert isinstance(parser, TikaParser)
    assert parser.base_url == "http://tika.local:9998"


@pytest.mark.asyncio
async def test_select_parser_routes_images_to_ocr() -> None:
    parser = await select_parser(
        ".png",
        extraction_config={"ocr_enable": True, "ocr_languages": "chi_sim"},
    )

    assert isinstance(parser, ImageOCRParser)
    assert parser.languages == "chi_sim"


@pytest.mark.asyncio
async def test_select_parser_skips_ocr_when_disabled() -> None:
    with pytest.raises(ValueError):
        await select_parser(".png", extraction_config={"ocr_enable": False})


@pytest.mark.asyncio
async def test_select_parser_keeps_builtin_pdf_parser() -> None:
    assert isinstance(await select_parser(".pdf"), PDFParser)


@pytest.mark.asyncio
async def test_select_parser_rejects_unknown_extension() -> None:
    with pytest.raises(ValueError):
        await select_parser(".xyz")


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, content: bytes = b"extracted text"):
        self.status_code = status_code
        self.content = content

    async def aiter_bytes(self):
        if self.content:
            yield self.content


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> _FakeResponse:
        return self.response

    async def __aexit__(self, *_args) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, **_kwargs) -> None:
        self.calls: list[dict] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def stream(self, method, url, *, content, headers):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "content": content,
                "headers": headers,
            }
        )
        return _FakeStream(_FakeResponse())


@pytest.mark.asyncio
async def test_tika_parser_posts_file(monkeypatch) -> None:
    client = _FakeAsyncClient()
    monkeypatch.setattr(tika_parser.httpx, "AsyncClient", lambda **kwargs: client)

    parser = TikaParser("http://tika.local:9998/")
    result = await parser.parse(b"raw-bytes", "doc.pdf")

    assert result.text == "extracted text"
    assert result.media == []
    assert client.calls[0]["method"] == "PUT"
    assert client.calls[0]["url"] == "http://tika.local:9998/tika"
    assert client.calls[0]["content"] == b"raw-bytes"


@pytest.mark.asyncio
async def test_image_ocr_parser_uses_ocr(monkeypatch) -> None:
    async def fake_ocr(content: bytes, languages: str) -> str:
        assert content == b"image-bytes"
        assert languages == "eng"
        return "recognized"

    monkeypatch.setattr(ocr_parser, "ocr_image_bytes", fake_ocr)

    result = await ImageOCRParser().parse(b"image-bytes", "scan.png")

    assert result.text == "recognized"
    assert result.media and result.media[0].media_type == "image"


@pytest.mark.asyncio
async def test_image_ocr_parser_propagates_missing_engine(monkeypatch) -> None:
    async def missing(_content: bytes, _languages: str) -> str:
        raise OCREngineUnavailable("missing")

    monkeypatch.setattr(ocr_parser, "ocr_image_bytes", missing)

    with pytest.raises(OCREngineUnavailable):
        await ImageOCRParser().parse(b"image-bytes", "scan.png")


def test_pdf_filter_arrays_resolve_to_the_real_image_encoding():
    from pypdf.generic import ArrayObject, NameObject

    assert PDFParser._resolve_image_format(
        ArrayObject([NameObject("/ASCII85Decode"), NameObject("/DCTDecode")])
    ) == ("jpg", "image/jpeg")
    assert PDFParser._resolve_image_format("/JPXDecode") == ("jp2", "image/jp2")
    assert PDFParser._resolve_image_format("/FlateDecode") is None


@pytest.mark.asyncio
async def test_tika_parser_caps_streaming_response(monkeypatch) -> None:
    response = _FakeResponse(content=b"x" * 64)

    class CappedClient(_FakeAsyncClient):
        def stream(self, method, url, *, content, headers):
            return _FakeStream(response)

    monkeypatch.setattr(
        tika_parser.httpx, "AsyncClient", lambda **kwargs: CappedClient()
    )
    monkeypatch.setattr(tika_parser, "_MAX_TIKA_RESPONSE_BYTES", 16)

    result = await TikaParser("http://tika.local:9998").parse(b"raw", "doc.pdf")

    assert result.text == "x" * 16


@pytest.mark.asyncio
async def test_tika_parser_rejects_error_status(monkeypatch) -> None:
    class ErrorClient(_FakeAsyncClient):
        def stream(self, method, url, *, content, headers):
            return _FakeStream(_FakeResponse(status_code=500))

    monkeypatch.setattr(
        tika_parser.httpx, "AsyncClient", lambda **kwargs: ErrorClient()
    )

    with pytest.raises(RuntimeError, match="status 500"):
        await TikaParser("http://tika.local:9998").parse(b"raw", "doc.pdf")
