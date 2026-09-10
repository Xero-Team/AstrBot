"""Tests for knowledge-base document replace-by-identity ingest."""

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker
from astrbot.core.knowledge_base.kb_db_sqlite import (
    KBSQLiteDatabase,
    file_identity_key,
    posix_identity_input,
)
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KnowledgeBase
from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = 8) -> None:
        super().__init__({"embedding_dimensions": dim}, {})
        self.embed_calls = 0
        self.fail_next = False

    async def get_embedding(self, text: str) -> list[float]:
        self.embed_calls += 1
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index] / 255.0 for index in range(self.get_dim())]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        if self.fail_next:
            raise RuntimeError("embedding failed")
        return [await self.get_embedding(item) for item in text]


@pytest_asyncio.fixture
async def kb_helper(tmp_path):
    db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await db.initialize()
    kb = KnowledgeBase(
        kb_name="Replace KB",
        embedding_provider_id="emb-1",
        chunk_size=64,
        chunk_overlap=0,
    )
    async with db.get_db() as session, session.begin():
        session.add(kb)
        await session.flush()
    embedding = HashEmbeddingProvider()
    provider_manager = MagicMock()
    provider_manager.get_provider_by_id = AsyncMock(return_value=embedding)
    helper = KBHelper(
        kb_db=db,
        kb=kb,
        provider_manager=provider_manager,
        kb_root_dir=str(tmp_path / "kbs"),
        chunker=RecursiveCharacterChunker(chunk_size=64, chunk_overlap=0),
    )
    await helper.initialize()
    try:
        yield helper, embedding
    finally:
        await helper.terminate()
        await db.close()


async def _chunk_texts(helper: KBHelper, doc_id: str) -> list[str]:
    chunks = await helper.get_chunks_by_doc_id(doc_id, offset=0, limit=1000)
    return [chunk["content"] for chunk in chunks]


@pytest.mark.asyncio
async def test_same_relative_name_replaces_chunks_and_keeps_doc_id(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="handbook.md",
        file_content=b"alpha unique body for the first generation",
        file_type="md",
        chunk_size=64,
        chunk_overlap=0,
    )
    created_at = first.document.created_at
    second = await helper.upload_document(
        file_name="handbook.md",
        file_content=b"beta unique body for the second generation",
        file_type="md",
        chunk_size=64,
        chunk_overlap=0,
    )
    assert second.ingest_status == "replaced"
    assert second.document.doc_id == first.document.doc_id
    assert second.document.created_at.replace(tzinfo=None) == created_at.replace(
        tzinfo=None
    )
    texts = await _chunk_texts(helper, first.document.doc_id)
    joined = "\n".join(texts)
    assert "beta unique body" in joined
    assert "alpha unique body" not in joined


@pytest.mark.asyncio
async def test_long_relative_paths_keep_distinct_identities(kb_helper):
    helper, _embedding = kb_helper
    path_a = "dir-a/" + ("x" * 300) + "/note.md"
    path_b = "dir-b/" + ("y" * 300) + "/note.md"
    display = KnowledgeBaseService.sanitize_upload_filename(path_a)
    assert display == KnowledgeBaseService.sanitize_upload_filename(path_b)
    first = await helper.upload_document(
        file_name=display,
        file_content=b"content from path a unique",
        file_type="md",
        identity_key=file_identity_key(posix_identity_input(path_a)),
    )
    second = await helper.upload_document(
        file_name=display,
        file_content=b"content from path b unique",
        file_type="md",
        identity_key=file_identity_key(posix_identity_input(path_b)),
    )
    assert first.ingest_status == "created"
    assert second.ingest_status == "created"
    assert first.document.doc_id != second.document.doc_id
    assert "path a unique" in "\n".join(
        await _chunk_texts(helper, first.document.doc_id)
    )
    assert "path b unique" in "\n".join(
        await _chunk_texts(helper, second.document.doc_id)
    )


@pytest.mark.asyncio
async def test_unchanged_hash_skips_embedding(kb_helper):
    helper, embedding = kb_helper
    payload = b"same bytes for both uploads unique"
    first = await helper.upload_document(
        file_name="stable.md",
        file_content=payload,
        file_type="md",
    )
    calls = embedding.embed_calls
    second = await helper.upload_document(
        file_name="stable.md",
        file_content=payload,
        file_type="md",
    )
    assert second.ingest_status == "unchanged"
    assert second.document.doc_id == first.document.doc_id
    assert embedding.embed_calls == calls


@pytest.mark.asyncio
async def test_replace_embed_failure_keeps_previous_chunks(kb_helper):
    helper, embedding = kb_helper
    first = await helper.upload_document(
        file_name="live.md",
        file_content=b"previous generation unique body",
        file_type="md",
    )
    embedding.fail_next = True
    with pytest.raises((KnowledgeBaseUploadError, RuntimeError)):
        await helper.upload_document(
            file_name="live.md",
            file_content=b"incoming generation unique body",
            file_type="md",
        )
    texts = await _chunk_texts(helper, first.document.doc_id)
    joined = "\n".join(texts)
    assert "previous generation unique body" in joined
    assert "incoming generation unique body" not in joined
    live = await helper.get_document(first.document.doc_id)
    assert live is not None


@pytest.mark.asyncio
async def test_concurrent_uploads_of_same_identity_serialize(kb_helper):
    helper, _embedding = kb_helper
    first, second = await asyncio.gather(
        helper.upload_document(
            file_name="shared.md",
            file_content=b"concurrent generation one unique",
            file_type="md",
        ),
        helper.upload_document(
            file_name="shared.md",
            file_content=b"concurrent generation two unique",
            file_type="md",
        ),
    )
    assert {first.ingest_status, second.ingest_status} <= {"created", "replaced"}
    assert first.document.doc_id == second.document.doc_id
    texts = await _chunk_texts(helper, first.document.doc_id)
    joined = "\n".join(texts)
    has_one = "generation one unique" in joined
    has_two = "generation two unique" in joined
    assert has_one ^ has_two


@pytest.mark.asyncio
async def test_listed_document_omits_file_path_and_marks_source_stored(kb_helper):
    helper, _embedding = kb_helper
    result = await helper.upload_document(
        file_name="listed.md",
        file_content=b"listed document unique body",
        file_type="md",
    )
    payload = KnowledgeBaseService.document_public_payload(result)
    assert "file_path" not in payload
    assert payload["source_stored"] is True
    assert payload["identity_key"] == "file:listed.md"
    assert payload["ingest_status"] == "created"
    blob = helper.kb_files_dir / result.document.doc_id
    assert blob.is_file()


def _enable_tavily(helper: KBHelper) -> None:
    helper.prov_mgr.acm = MagicMock()
    helper.prov_mgr.acm.default_conf = {
        "provider_settings": {"websearch_tavily_key": ["test-key"]}
    }


@pytest.mark.asyncio
async def test_url_import_replaces_by_canonical_url(kb_helper, monkeypatch):
    helper, _embedding = kb_helper
    _enable_tavily(helper)
    pages = iter(["first extracted unique page", "second extracted unique page"])

    async def fake_extract(
        *, url, tavily_keys, progress_callback=None, max_response_bytes=None
    ):
        return next(pages)

    monkeypatch.setattr(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        fake_extract,
    )
    first = await helper.upload_from_url("http://example.com/a")
    second = await helper.upload_from_url("http://example.com/a#x")
    assert first.document.doc_id == second.document.doc_id
    assert second.ingest_status == "replaced"
    assert second.document.source_url == "http://example.com/a"
    joined = "\n".join(await _chunk_texts(helper, first.document.doc_id))
    assert "second extracted unique page" in joined
    assert "first extracted unique page" not in joined


@pytest.mark.asyncio
async def test_url_scheme_keeps_http_and_https_distinct(kb_helper, monkeypatch):
    helper, _embedding = kb_helper
    _enable_tavily(helper)
    pages = iter(["http page unique", "https page unique"])

    async def fake_extract(
        *, url, tavily_keys, progress_callback=None, max_response_bytes=None
    ):
        return next(pages)

    monkeypatch.setattr(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        fake_extract,
    )
    http_doc = await helper.upload_from_url("http://Example.com/a")
    https_doc = await helper.upload_from_url("https://example.com/a#frag")
    assert http_doc.document.doc_id != https_doc.document.doc_id
    assert http_doc.ingest_status == "created"
    assert https_doc.ingest_status == "created"


@pytest.mark.asyncio
async def test_url_extract_failure_does_not_delete_previous(kb_helper, monkeypatch):
    helper, _embedding = kb_helper
    _enable_tavily(helper)

    async def first_extract(
        *, url, tavily_keys, progress_callback=None, max_response_bytes=None
    ):
        return "keep this extracted unique page"

    monkeypatch.setattr(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        first_extract,
    )
    first = await helper.upload_from_url("https://example.com/keep")

    async def fail_extract(
        *, url, tavily_keys, progress_callback=None, max_response_bytes=None
    ):
        raise OSError("Failed to extract content from URL")

    monkeypatch.setattr(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        fail_extract,
    )
    with pytest.raises(OSError, match="Failed to extract content from URL"):
        await helper.upload_from_url("https://example.com/keep")
    joined = "\n".join(await _chunk_texts(helper, first.document.doc_id))
    assert "keep this extracted unique page" in joined
    live = await helper.get_document(first.document.doc_id)
    assert live is not None


@pytest.mark.asyncio
async def test_overlong_canonical_url_fails_before_replace(kb_helper, monkeypatch):
    helper, embedding = kb_helper
    _enable_tavily(helper)
    extract = AsyncMock(return_value="should not extract")
    monkeypatch.setattr(
        "astrbot.core.knowledge_base.kb_helper.extract_url_content",
        extract,
    )
    helper.upload_document = AsyncMock()
    with pytest.raises(ValueError, match="too long"):
        await helper.upload_from_url("https://example.com/" + ("a" * 2100))
    extract.assert_not_awaited()
    helper.upload_document.assert_not_awaited()
    assert embedding.embed_calls == 0


def test_url_ingest_without_identity_key_raises():
    with pytest.raises(ValueError, match="identity_key"):
        KBHelper._identity_key_for("url", "https://example.com/a")


@pytest.mark.asyncio
async def test_reembed_from_stored_blob_uses_original_file_type(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="handbook.md",
        file_content=b"# heading unique markdown body",
        file_type="md",
    )
    captured: dict[str, object] = {}

    async def fake_ingest(**kwargs):
        captured.update(kwargs)
        return ["chunk"], [], 1

    helper._ingest_chunks_for_doc_id = fake_ingest
    await helper._reembed_from_stored_blob(
        first.document.doc_id,
        helper._doc_blob_path(first.document.doc_id),
    )
    assert captured["file_name"] == "handbook.md"
    assert captured["file_type"] == "md"
    assert captured["doc_id"] == first.document.doc_id


@pytest.mark.asyncio
async def test_recover_interrupted_replace_drops_orphans_and_rebuilds(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="live.md",
        file_content=b"recoverable unique live body",
        file_type="md",
    )
    live_id = first.document.doc_id
    await helper.vec_db.insert_batch(
        contents=["orphan staging unique chunk"],
        metadatas=[
            {
                "kb_id": helper.kb.kb_id,
                "kb_doc_id": "orphan-staging",
                "chunk_index": 0,
            }
        ],
    )
    await helper.vec_db.delete_documents(metadata_filters={"kb_doc_id": live_id})
    assert await _chunk_texts(helper, live_id) == []
    await helper.initialize()
    orphans = await helper.vec_db.document_storage.get_documents(
        metadata_filters={"kb_doc_id": "orphan-staging"},
        offset=None,
        limit=None,
    )
    assert orphans == []
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "recoverable unique live body" in joined
