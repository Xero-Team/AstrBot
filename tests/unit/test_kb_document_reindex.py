"""Tests for knowledge-base document reindex from stored source bytes."""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KnowledgeBase
from astrbot.core.provider.provider import EmbeddingProvider
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = 8) -> None:
        super().__init__({"embedding_dimensions": dim}, {})
        self.embed_calls = 0

    async def get_embedding(self, text: str) -> list[float]:
        self.embed_calls += 1
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index] / 255.0 for index in range(self.get_dim())]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [await self.get_embedding(item) for item in text]


@pytest_asyncio.fixture
async def kb_helper(tmp_path):
    db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await db.initialize()
    kb = KnowledgeBase(
        kb_name="Reindex KB",
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


async def _chunk_ids(helper: KBHelper, doc_id: str) -> list[str]:
    chunks = await helper.get_chunks_by_doc_id(doc_id, offset=0, limit=1000)
    return [chunk["chunk_id"] for chunk in chunks]


@pytest.mark.asyncio
async def test_reindex_applies_new_chunk_size_and_drops_old_ids(kb_helper):
    helper, _embedding = kb_helper
    body = b"one two three four five six seven eight nine ten " * 8
    uploaded = await helper.upload_document(
        file_name="handbook.md",
        file_content=body,
        file_type="md",
        chunk_size=64,
        chunk_overlap=0,
    )
    old_ids = await _chunk_ids(helper, uploaded.document.doc_id)
    helper.kb.chunk_size = 16
    helper.chunker = RecursiveCharacterChunker(chunk_size=16, chunk_overlap=0)
    result = await helper.reindex_document(uploaded.document.doc_id)
    new_ids = await _chunk_ids(helper, uploaded.document.doc_id)
    assert result.document.doc_id == uploaded.document.doc_id
    assert result.document.chunk_count != uploaded.document.chunk_count
    assert set(old_ids).isdisjoint(set(new_ids))
    assert new_ids
    chunks = await helper.get_chunks_by_doc_id(uploaded.document.doc_id, 0, 1000)
    assert {chunk["doc_id"] for chunk in chunks} == {uploaded.document.doc_id}


@pytest.mark.asyncio
async def test_reindex_missing_blob_keeps_old_index(kb_helper):
    helper, embedding = kb_helper
    uploaded = await helper.upload_document(
        file_name="missing.md",
        file_content=b"stored unique body for missing blob",
        file_type="md",
    )
    blob = helper.kb_files_dir / uploaded.document.doc_id
    blob.unlink()
    calls = embedding.embed_calls
    old_ids = await _chunk_ids(helper, uploaded.document.doc_id)
    with pytest.raises(KnowledgeBaseUploadError, match="source file is not stored"):
        await helper.reindex_document(uploaded.document.doc_id)
    assert embedding.embed_calls == calls
    assert await _chunk_ids(helper, uploaded.document.doc_id) == old_ids


@pytest.mark.asyncio
async def test_reindex_dimension_mismatch_does_not_write_faiss(kb_helper):
    helper, embedding = kb_helper
    uploaded = await helper.upload_document(
        file_name="dim.md",
        file_content=b"dimension mismatch unique body",
        file_type="md",
    )
    old_ids = await _chunk_ids(helper, uploaded.document.doc_id)
    calls = embedding.embed_calls
    helper.prov_mgr.get_provider_by_id = AsyncMock(
        return_value=HashEmbeddingProvider(dim=16)
    )
    with pytest.raises(
        KnowledgeBaseUploadError,
        match="embedding settings are incompatible",
    ):
        await helper.reindex_document(uploaded.document.doc_id)
    assert embedding.embed_calls == calls
    assert await _chunk_ids(helper, uploaded.document.doc_id) == old_ids


@pytest.mark.asyncio
async def test_service_reindex_maps_missing_source_to_400():
    helper = AsyncMock()
    helper.reindex_document = AsyncMock(
        side_effect=KnowledgeBaseUploadError(
            stage="reindex",
            user_message="source file is not stored; upload again",
        )
    )
    manager = MagicMock(get_kb=AsyncMock(return_value=helper))
    service = KnowledgeBaseService(manager)
    with pytest.raises(
        KnowledgeBaseServiceError, match="source file is not stored"
    ) as exc:
        await service.reindex_document(kb_id="kb-1", doc_id="doc-1")
    assert exc.value.status_code == 400
    assert "/" not in str(exc.value) or "upload again" in str(exc.value)
