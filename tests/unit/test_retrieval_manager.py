from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.db.vec_db import Result
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.rank_fusion import FusedResult
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


def _make_kb_helper(*, kb_id: str, kb_name: str, rerank_provider=None):
    kb = SimpleNamespace(
        kb_id=kb_id,
        kb_name=kb_name,
        top_k_dense=3,
        top_k_sparse=2,
        top_m_final=2,
        rerank_provider_id=(
            rerank_provider.meta().id if rerank_provider is not None else None
        ),
    )
    vec_db = SimpleNamespace(rerank_provider=rerank_provider)
    return SimpleNamespace(kb=kb, vec_db=vec_db)


def _make_metadata_map(doc_id: str, doc_name: str, kb_name: str):
    return {
        doc_id: {
            "document": SimpleNamespace(doc_name=doc_name),
            "knowledge_base": SimpleNamespace(kb_name=kb_name),
        }
    }


@pytest.mark.asyncio
async def test_retrieval_manager_skips_missing_kb_helpers():
    sparse_retriever = AsyncMock()
    sparse_retriever.retrieve.return_value = []
    rank_fusion = AsyncMock()
    rank_fusion.fuse.return_value = []
    kb_db = AsyncMock()
    kb_db.get_documents_with_metadata_batch.return_value = {}
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=rank_fusion,
        kb_db=kb_db,
    )
    kb_helper = _make_kb_helper(kb_id="kb-1", kb_name="Knowledge Base 1")
    dense_result = Result(
        similarity=0.9,
        data={"doc_id": "chunk-1", "metadata": "{}", "text": "dense chunk"},
    )
    manager._dense_retrieve = AsyncMock(return_value=[dense_result])

    await manager.retrieve(
        query="test query",
        kb_ids=["kb-1", "kb-missing"],
        kb_id_helper_map={"kb-1": kb_helper},
    )

    sparse_retriever.retrieve.assert_awaited_once()
    sparse_call = sparse_retriever.retrieve.await_args.kwargs
    assert sparse_call["kb_ids"] == ["kb-1"]
    assert "kb-missing" not in sparse_call["kb_options"]


@pytest.mark.asyncio
async def test_retrieval_manager_reranks_results_when_provider_matches():
    rerank_provider = MagicMock()
    rerank_provider.meta.return_value = SimpleNamespace(id="rerank-1")
    rerank_provider.rerank = AsyncMock(
        return_value=[
            SimpleNamespace(index=1, relevance_score=0.95),
            SimpleNamespace(index=0, relevance_score=0.80),
        ]
    )
    sparse_retriever = AsyncMock()
    sparse_retriever.retrieve.return_value = [
        SparseResult(
            chunk_id="chunk-1",
            doc_id="doc-1",
            kb_id="kb-1",
            content="first result",
            chunk_index=0,
            score=0.4,
        ),
        SparseResult(
            chunk_id="chunk-2",
            doc_id="doc-2",
            kb_id="kb-1",
            content="second result",
            chunk_index=1,
            score=0.3,
        ),
    ]
    rank_fusion = AsyncMock()
    rank_fusion.fuse.return_value = [
        FusedResult(
            chunk_id="chunk-1",
            chunk_index=0,
            doc_id="doc-1",
            kb_id="kb-1",
            content="first result",
            score=0.5,
        ),
        FusedResult(
            chunk_id="chunk-2",
            chunk_index=1,
            doc_id="doc-2",
            kb_id="kb-1",
            content="second result",
            score=0.4,
        ),
    ]
    kb_db = AsyncMock()
    kb_db.get_documents_with_metadata_batch.return_value = {
        **_make_metadata_map("doc-1", "Doc 1", "Knowledge Base 1"),
        **_make_metadata_map("doc-2", "Doc 2", "Knowledge Base 1"),
    }
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=rank_fusion,
        kb_db=kb_db,
    )
    manager._dense_retrieve = AsyncMock(return_value=[])
    kb_helper = _make_kb_helper(
        kb_id="kb-1",
        kb_name="Knowledge Base 1",
        rerank_provider=rerank_provider,
    )

    results = await manager.retrieve(
        query="test query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_m_final=2,
    )

    assert [result.doc_id for result in results] == ["doc-2", "doc-1"]
    assert [result.score for result in results] == [0.95, 0.80]
    rerank_provider.rerank.assert_awaited_once_with(
        query="test query",
        documents=["first result", "second result"],
    )
