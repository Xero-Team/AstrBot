import hashlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.knowledge_base._kb_helper_url_import import (
    build_url_document_name,
    canonical_url,
    hash_extracted_text,
    url_identity_key,
)


@pytest.fixture
def stub_provider_manager_module():
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager: ...

    setattr(stub_module, "ProviderManager", ProviderManager)
    sys.modules["astrbot.core.provider.manager"] = stub_module

    try:
        yield
    finally:
        if original_module is not None:
            sys.modules["astrbot.core.provider.manager"] = original_module
        else:
            sys.modules.pop("astrbot.core.provider.manager", None)


@pytest.mark.asyncio
async def test_upload_from_url_requires_tavily_key(
    stub_provider_manager_module,
) -> None:
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.prov_mgr = MagicMock()
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {}

    with pytest.raises(ValueError, match="Tavily API key"):
        await helper.upload_from_url("https://example.com/page")


@pytest.mark.asyncio
async def test_upload_from_url_uses_extracted_chunks(
    stub_provider_manager_module,
) -> None:
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.prov_mgr = MagicMock()
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {
        "provider_settings": {"websearch_tavily_key": ["test-key"]}
    }
    helper._clean_and_rechunk_content = AsyncMock(return_value=["chunk-a", "chunk-b"])
    helper.upload_document = AsyncMock(return_value="uploaded")

    with patch(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        new=AsyncMock(return_value="content"),
    ):
        result = await helper.upload_from_url("https://example.com/article")

    assert result == "uploaded"
    helper.upload_document.assert_awaited_once()
    _, kwargs = helper.upload_document.await_args
    assert kwargs["pre_chunked_text"] == ["chunk-a", "chunk-b"]
    assert kwargs["file_name"] == "article.url"
    assert kwargs["source_kind"] == "url"
    assert kwargs["source_url"] == "https://example.com/article"
    assert kwargs["identity_key"] == url_identity_key("https://example.com/article")
    assert kwargs["content_hash"] == hash_extracted_text("content")
    assert kwargs["source_bytes"] == b"content"


@pytest.mark.asyncio
async def test_upload_from_url_rejects_empty_cleaned_chunks(
    stub_provider_manager_module,
) -> None:
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    helper = KBHelper.__new__(KBHelper)
    helper.prov_mgr = MagicMock()
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {
        "provider_settings": {"websearch_tavily_key": ["test-key"]}
    }
    helper._clean_and_rechunk_content = AsyncMock(return_value=[])
    helper.upload_document = AsyncMock()

    with patch(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        new=AsyncMock(return_value="content"),
    ):
        with pytest.raises(ValueError, match="内容清洗后未提取到有效文本"):
            await helper.upload_from_url(
                "https://example.com/article",
                enable_cleaning=True,
                cleaning_provider_id="provider-1",
            )

    helper.upload_document.assert_not_called()


def test_build_url_document_name_adds_suffix_when_missing() -> None:
    assert build_url_document_name("https://example.com/article") == "article.url"
    assert build_url_document_name("https://example.com/file.md") == "file.md"


def test_canonical_url_normalizes_host_port_fragment_and_query() -> None:
    assert canonical_url("http://Example.com/a#frag") == "http://example.com/a"
    assert canonical_url("http://example.com/a#x") == "http://example.com/a"
    assert canonical_url("https://example.com:443/a") == "https://example.com/a"
    assert canonical_url("http://example.com:80/a") == "http://example.com/a"
    assert canonical_url("http://example.com") == "http://example.com/"
    assert (
        canonical_url("http://example.com/a?b=2&a=1") == "http://example.com/a?a=1&b=2"
    )
    http_key = url_identity_key(canonical_url("http://Example.com/a"))
    https_key = url_identity_key(canonical_url("https://example.com/a#frag"))
    assert http_key != https_key
    assert url_identity_key(canonical_url("http://example.com/a#x")) == http_key


def test_canonical_url_rejects_non_http_and_overlong() -> None:
    with pytest.raises(ValueError, match="Only http and https"):
        canonical_url("ftp://example.com/a")
    with pytest.raises(ValueError, match="too long"):
        canonical_url("https://example.com/" + ("a" * 2100))


@pytest.mark.asyncio
async def test_extract_url_content_does_not_leak_query_on_failure(
    caplog, monkeypatch
) -> None:
    from astrbot.core.knowledge_base._kb_helper_url_import import extract_url_content

    async def boom(_url: str, _keys: list[str]) -> str:
        raise RuntimeError("upstream failed")

    monkeypatch.setattr(
        "astrbot.core.knowledge_base._kb_helper_url_import.extract_text_from_url",
        boom,
    )
    caplog.set_level("ERROR")
    with pytest.raises(OSError, match="Failed to extract content from URL"):
        await extract_url_content(
            url="https://example.com/page?token=secret-token",
            tavily_keys=["k"],
        )
    rendered = " ".join(record.getMessage() for record in caplog.records)
    assert "token=secret-token" not in rendered
    assert "secret-token" not in rendered


def test_hash_extracted_text_is_sha256() -> None:
    assert hash_extracted_text("hello") == hashlib.sha256(b"hello").hexdigest()
