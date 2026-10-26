"""Tests for knowledge-base document replace-by-identity ingest."""

import asyncio
import hashlib
import uuid
from pathlib import Path
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
from astrbot.core.knowledge_base.models import KBMedia, KnowledgeBase
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


@pytest.mark.asyncio
async def test_replace_media_commit_failure_rolls_back_to_previous_generation(
    kb_helper, monkeypatch
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="rollback-media.md",
        file_content=b"previous generation survives media failure",
        file_type="md",
    )
    original_commit = helper._commit_replaced_media
    calls = 0

    async def fail_once(saved_media):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("media commit failed")
        await original_commit(saved_media)

    monkeypatch.setattr(helper, "_commit_replaced_media", fail_once)

    with pytest.raises(RuntimeError, match="media commit failed"):
        await helper.upload_document(
            file_name="rollback-media.md",
            file_content=b"incoming generation must not remain",
            file_type="md",
        )

    live_id = first.document.doc_id
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "previous generation survives media failure" in joined
    assert "incoming generation must not remain" not in joined
    live = await helper.get_document(live_id)
    assert live is not None
    assert live.chunk_count == len(await _chunk_texts(helper, live_id))
    assert not helper._doc_blob_path(live_id, ".staging").exists()
    assert not helper._doc_blob_path(live_id, ".bak").exists()


@pytest.mark.asyncio
async def test_replace_metadata_failure_rolls_back_and_recovery_is_idempotent(
    kb_helper, monkeypatch
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="rollback-metadata.md",
        file_content=b"previous metadata generation survives",
        file_type="md",
    )
    original_update = helper._update_live_document_metadata
    failed = False

    async def fail_once(**kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("metadata update failed")
        return await original_update(**kwargs)

    monkeypatch.setattr(helper, "_update_live_document_metadata", fail_once)

    with pytest.raises(RuntimeError, match="metadata update failed"):
        await helper.upload_document(
            file_name="rollback-metadata.md",
            file_content=b"incoming metadata generation must not remain",
            file_type="md",
        )

    live_id = first.document.doc_id
    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == first.document.content_hash
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "previous metadata generation survives" in joined
    assert "incoming metadata generation must not remain" not in joined

    await helper.initialize()
    live = await helper.get_document(live_id)
    assert live is not None
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "previous metadata generation survives" in joined
    assert live.chunk_count == len(await _chunk_texts(helper, live_id))
    assert not helper._doc_blob_path(live_id, ".bak").exists()


@pytest.mark.asyncio
async def test_partial_relabel_failure_rolls_back_to_previous_generation(
    kb_helper, monkeypatch
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="partial-relabel.md",
        file_content=b"previous generation survives partial relabel",
        file_type="md",
    )
    original_relabel = helper._relabel_staging_generation

    async def relabel_then_fail(**kwargs):
        await original_relabel(**kwargs)
        raise RuntimeError("media directory rename failed")

    monkeypatch.setattr(helper, "_relabel_staging_generation", relabel_then_fail)

    with pytest.raises(RuntimeError, match="media directory rename failed"):
        await helper.upload_document(
            file_name="partial-relabel.md",
            file_content=b"incoming partial relabel must not remain",
            file_type="md",
        )

    live_id = first.document.doc_id
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "previous generation survives partial relabel" in joined
    assert "incoming partial relabel must not remain" not in joined
    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == first.document.content_hash
    assert not helper._doc_blob_path(live_id, ".staging").exists()
    assert not helper._doc_blob_path(live_id, ".bak").exists()


@pytest.mark.asyncio
async def test_replace_without_stored_backup_rolls_forward_consistently(
    kb_helper, monkeypatch
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="legacy-no-blob.md",
        file_content=b"legacy generation without a stored source",
        file_type="md",
    )
    live_id = first.document.doc_id
    helper._doc_blob_path(live_id).unlink()
    incoming = b"replacement generation without backup rollback"
    original_update = helper._update_live_document_metadata
    failed = False

    async def fail_once(**kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("metadata update failed")
        return await original_update(**kwargs)

    monkeypatch.setattr(helper, "_update_live_document_metadata", fail_once)

    with pytest.raises(RuntimeError, match="metadata update failed"):
        await helper.upload_document(
            file_name="legacy-no-blob.md",
            file_content=incoming,
            file_type="md",
        )

    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == hashlib.sha256(incoming).hexdigest()
    assert live.file_size == len(incoming)
    assert live.chunk_count == len(await _chunk_texts(helper, live_id))
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "replacement generation without backup rollback" in joined
    assert "legacy generation without a stored source" not in joined
    assert not helper._doc_blob_path(live_id, ".staging").exists()
    assert not helper._doc_blob_path(live_id, ".bak").exists()


@pytest.mark.asyncio
async def test_roll_forward_does_not_claim_chunks_when_rebuild_fails(
    kb_helper, monkeypatch
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="no-backup-rebuild-failure.md",
        file_content=b"previous generation without a stored source",
        file_type="md",
    )
    live_id = first.document.doc_id
    helper._doc_blob_path(live_id).unlink()
    incoming = b"incoming generation whose rebuild fails"
    original_update = helper._update_live_document_metadata
    failed = False

    async def fail_once(**kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("metadata update failed")
        return await original_update(**kwargs)

    async def broken_reembed(*_args, **_kwargs):
        return None

    monkeypatch.setattr(helper, "_update_live_document_metadata", fail_once)
    monkeypatch.setattr(helper, "_reembed_from_stored_blob", broken_reembed)

    with pytest.raises(RuntimeError, match="metadata update failed"):
        await helper.upload_document(
            file_name="no-backup-rebuild-failure.md",
            file_content=incoming,
            file_type="md",
        )

    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == hashlib.sha256(incoming).hexdigest()
    assert live.chunk_count == 0
    assert live.media_count == 0
    assert await _chunk_texts(helper, live_id) == []


@pytest.mark.asyncio
async def test_reembed_from_stored_blob_clears_stale_media(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="stale-media.md",
        file_content=b"body for the media rebuild",
        file_type="md",
    )
    doc_id = first.document.doc_id
    async with helper.kb_db.get_db() as session, session.begin():
        session.add(
            KBMedia(
                media_id="stale-media",
                doc_id=doc_id,
                kb_id=helper.kb.kb_id,
                media_type="image",
                file_name="stale.png",
                file_path=str(helper.kb_medias_dir / doc_id / "stale.png"),
                file_size=1,
                mime_type="image/png",
            ),
        )

    rebuilt = await helper._reembed_from_stored_blob(
        doc_id,
        helper._doc_blob_path(doc_id),
    )

    assert rebuilt is not None
    assert await helper.kb_db.list_media_by_doc(doc_id) == []
    live = await helper.get_document(doc_id)
    assert live is not None
    assert live.media_count == 0
    assert await _chunk_texts(helper, doc_id)


async def _stage_crashed_replacement(
    helper: KBHelper,
    document,
    incoming: bytes,
    *,
    finalize_metadata: bool,
) -> tuple[str, dict[str, object]]:
    """Leave the live state exactly where a crash can interrupt a replacement."""
    live_id = document.doc_id
    staging_id = str(uuid.uuid4())
    staging_blob = helper._doc_blob_path(live_id, ".staging")
    live_blob = helper._doc_blob_path(live_id)
    bak_blob = helper._doc_blob_path(live_id, ".bak")
    await helper._write_blob(staging_blob, incoming)
    chunks, saved_media, _ = await helper._ingest_chunks_for_doc_id(
        doc_id=staging_id,
        file_name=document.doc_name,
        file_content=incoming,
        file_type=document.file_type,
        media_paths=[],
        chunk_size=helper.kb.chunk_size or 64,
        chunk_overlap=helper.kb.chunk_overlap or 0,
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
        progress_callback=None,
        pre_chunked_text=None,
    )
    marker = {
        "file_name": document.doc_name,
        "file_type": document.file_type,
        "file_size": len(incoming),
        "chunk_count": len(chunks),
        "media_count": len(saved_media),
        "identity_key": document.identity_key,
        "content_hash": hashlib.sha256(incoming).hexdigest(),
        "source_kind": document.source_kind,
        "source_url": document.source_url,
    }
    helper._swap_live_blob(live_blob, staging_blob, bak_blob)
    await helper._write_replacement_marker(live_id, marker)
    await helper._retire_live_chunks(live_id)
    await helper._relabel_staging_generation(
        staging_id=staging_id,
        live_doc_id=live_id,
        saved_media=saved_media,
    )
    await helper._commit_replaced_media(saved_media)
    if finalize_metadata:
        await helper._update_live_document_metadata(
            live_doc_id=live_id,
            file_name=document.doc_name,
            file_type=document.file_type,
            file_size=len(incoming),
            chunk_count=len(chunks),
            media_count=len(saved_media),
            identity_key=document.identity_key,
            content_hash=marker["content_hash"],
            source_kind=document.source_kind,
            source_url=document.source_url,
        )
    return live_id, marker


@pytest.mark.asyncio
async def test_startup_rolls_back_replacement_interrupted_before_metadata(
    kb_helper,
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="interrupted.md",
        file_content=b"previous generation before the interrupted replace",
        file_type="md",
    )
    live_id, _marker = await _stage_crashed_replacement(
        helper,
        first.document,
        b"incoming generation interrupted before metadata",
        finalize_metadata=False,
    )

    await helper.initialize()

    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == first.document.content_hash
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "previous generation before the interrupted replace" in joined
    assert "incoming generation interrupted before metadata" not in joined
    assert live.chunk_count == len(await _chunk_texts(helper, live_id))
    assert not helper._doc_blob_path(live_id, ".bak").exists()
    assert not helper._replacement_marker_path(live_id).exists()


@pytest.mark.asyncio
async def test_startup_keeps_replacement_interrupted_after_metadata(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="interrupted.md",
        file_content=b"previous generation before the interrupted replace",
        file_type="md",
    )
    live_id, marker = await _stage_crashed_replacement(
        helper,
        first.document,
        b"incoming generation interrupted after metadata",
        finalize_metadata=True,
    )

    await helper.initialize()

    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == marker["content_hash"]
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "incoming generation interrupted after metadata" in joined
    assert "previous generation before the interrupted replace" not in joined
    assert live.chunk_count == len(await _chunk_texts(helper, live_id))
    assert not helper._doc_blob_path(live_id, ".bak").exists()
    assert not helper._replacement_marker_path(live_id).exists()


@pytest.mark.asyncio
async def test_startup_finishes_replacement_without_a_previous_source(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="no-backup-crash.md",
        file_content=b"legacy generation without a stored source",
        file_type="md",
    )
    live_id = first.document.doc_id
    helper._doc_blob_path(live_id).unlink()
    live_id, marker = await _stage_crashed_replacement(
        helper,
        first.document,
        b"incoming generation recovered after a crash",
        finalize_metadata=False,
    )

    await helper.initialize()

    live = await helper.get_document(live_id)
    assert live is not None
    assert live.content_hash == marker["content_hash"]
    joined = "\n".join(await _chunk_texts(helper, live_id))
    assert "incoming generation recovered after a crash" in joined
    assert "legacy generation without a stored source" not in joined
    assert live.chunk_count == len(await _chunk_texts(helper, live_id))
    assert not helper._doc_blob_path(live_id, ".bak").exists()
    assert not helper._replacement_marker_path(live_id).exists()


def _replacement_marker_for(document, incoming: bytes) -> dict[str, object]:
    return {
        "file_name": document.doc_name,
        "file_type": document.file_type,
        "file_size": len(incoming),
        "chunk_count": 1,
        "media_count": 0,
        "identity_key": document.identity_key,
        "content_hash": hashlib.sha256(incoming).hexdigest(),
        "source_kind": document.source_kind,
        "source_url": document.source_url,
        "blob_sha256": hashlib.sha256(incoming).hexdigest(),
    }


@pytest.mark.asyncio
async def test_startup_restores_backup_when_swap_stopped_after_live_rename(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="half-swap.md",
        file_content=b"previous generation",
        file_type="md",
    )
    live_id = first.document.doc_id
    live = helper._doc_blob_path(live_id)
    bak = helper._doc_blob_path(live_id, ".bak")
    staging = helper._doc_blob_path(live_id, ".staging")
    live.replace(bak)
    await helper._write_blob(staging, b"incoming generation")
    await helper._write_replacement_marker(
        live_id,
        _replacement_marker_for(first.document, b"incoming generation"),
        phase="prepared",
    )

    await helper.initialize()

    assert live.read_bytes() == b"previous generation"
    assert not bak.exists()
    assert not staging.exists()
    assert not helper._replacement_marker_path(live_id).exists()
    assert "previous generation" in "\n".join(await _chunk_texts(helper, live_id))


@pytest.mark.asyncio
async def test_startup_rolls_back_when_swap_finished_before_phase_update(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="phase-lag.md",
        file_content=b"previous generation",
        file_type="md",
    )
    live_id = first.document.doc_id
    live = helper._doc_blob_path(live_id)
    bak = helper._doc_blob_path(live_id, ".bak")
    staging = helper._doc_blob_path(live_id, ".staging")
    await helper._write_blob(staging, b"incoming generation")
    await helper._write_replacement_marker(
        live_id,
        _replacement_marker_for(first.document, b"incoming generation"),
        phase="prepared",
    )
    live.replace(bak)
    staging.replace(live)

    await helper.initialize()

    assert live.read_bytes() == b"previous generation"
    assert not bak.exists()
    assert not helper._replacement_marker_path(live_id).exists()
    assert "previous generation" in "\n".join(await _chunk_texts(helper, live_id))


@pytest.mark.asyncio
async def test_startup_keeps_old_generation_when_rollback_left_a_marker(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="late-marker.md",
        file_content=b"previous generation",
        file_type="md",
    )
    live_id = first.document.doc_id
    await helper._write_replacement_marker(
        live_id,
        _replacement_marker_for(first.document, b"incoming generation"),
        phase="swapped",
    )

    await helper.initialize()

    assert helper._doc_blob_path(live_id).read_bytes() == b"previous generation"
    assert not helper._replacement_marker_path(live_id).exists()
    assert "previous generation" in "\n".join(await _chunk_texts(helper, live_id))
    current = await helper.get_document(live_id)
    assert current is not None
    assert current.content_hash == first.document.content_hash


@pytest.mark.asyncio
async def test_startup_restores_backup_for_an_unreadable_marker(kb_helper):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="torn-marker.md",
        file_content=b"previous generation",
        file_type="md",
    )
    live_id = first.document.doc_id
    live = helper._doc_blob_path(live_id)
    bak = helper._doc_blob_path(live_id, ".bak")
    live.replace(bak)
    await helper._write_blob(live, b"incoming generation")
    helper._replacement_marker_path(live_id).write_text("{not json", encoding="utf-8")

    await helper.initialize()

    assert live.read_bytes() == b"previous generation"
    assert not bak.exists()
    assert not helper._replacement_marker_path(live_id).exists()
    assert "previous generation" in "\n".join(await _chunk_texts(helper, live_id))


@pytest.mark.asyncio
async def test_partial_blob_swap_failure_restores_the_previous_source(
    kb_helper, monkeypatch
):
    helper, _embedding = kb_helper
    first = await helper.upload_document(
        file_name="partial-swap.md",
        file_content=b"previous generation",
        file_type="md",
    )
    live_id = first.document.doc_id
    live = helper._doc_blob_path(live_id)
    bak = helper._doc_blob_path(live_id, ".bak")
    original_replace = Path.replace
    calls = {"count": 0}

    def flaky_replace(source: Path, target: Path) -> Path:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("staging publish failed")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    with pytest.raises(OSError, match="staging publish failed"):
        await helper.upload_document(
            file_name="partial-swap.md",
            file_content=b"incoming generation",
            file_type="md",
        )

    assert live.read_bytes() == b"previous generation"
    assert not bak.exists()
    assert "previous generation" in "\n".join(await _chunk_texts(helper, live_id))
    assert not helper._replacement_marker_path(live_id).exists()


@pytest.mark.asyncio
async def test_failed_backup_restore_keeps_source_for_retry(kb_helper, monkeypatch):
    helper, _embedding = kb_helper
    doc_id = "doc-retry"
    live_blob = helper._doc_blob_path(doc_id)
    bak_blob = helper._doc_blob_path(doc_id, ".bak")
    staging_blob = helper._doc_blob_path(doc_id, ".staging")
    live_blob.parent.mkdir(parents=True, exist_ok=True)
    live_blob.write_bytes(b"incoming")
    bak_blob.write_bytes(b"previous")
    staging_blob.write_bytes(b"staging")

    monkeypatch.setattr(helper, "_try_relabel_staging", AsyncMock(return_value=False))
    monkeypatch.setattr(helper, "_cleanup_failed_upload", AsyncMock())
    monkeypatch.setattr(helper, "_retire_live_chunks", AsyncMock())
    monkeypatch.setattr(helper, "_reembed_from_stored_blob", AsyncMock(return_value=None))
    monkeypatch.setattr(helper, "_roll_forward_replacement", AsyncMock())

    await helper._recover_failed_replace(
        live_doc_id=doc_id,
        staging_id="staging-id",
        media_paths=[],
        swapped_blob=True,
        retired_live=True,
        relabeled=False,
        finalized=False,
        saved_media=[],
        replacement_metadata={},
        live_blob=live_blob,
        staging_blob=staging_blob,
        bak_blob=bak_blob,
    )

    assert bak_blob.read_bytes() == b"previous"
    assert live_blob.read_bytes() == b"incoming"
    assert not staging_blob.exists()
