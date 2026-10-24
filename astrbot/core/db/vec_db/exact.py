"""Dependency-free exact vector backend.

``ExactVecDB`` reuses the FAISS orchestration (document storage, validation,
rollback) but replaces the index with an in-memory NumPy matrix persisted as a
single ``.npz`` file. It is a drop-in, dependency-free alternative for small
knowledge bases and a reference implementation of the ``VectorStore`` contract.
"""

from __future__ import annotations

import os
import uuid

import numpy as np

from .faiss import FaissVecDB


class ExactEmbeddingStorage:
    """In-memory exact L2 index with the same surface as ``EmbeddingStorage``."""

    def __init__(self, dimension: int, path: str | None = None) -> None:
        if dimension <= 0:
            raise ValueError(
                "无效的嵌入向量维度: "
                f"{dimension}。请检查该知识库使用的 Embedding Provider "
                "是否正确配置了 embedding_dimensions。",
            )
        self.dimension = dimension
        self.path = path
        self._ids: list[int] = []
        self._vectors: np.ndarray = np.zeros((0, dimension), dtype=np.float32)
        if path and os.path.exists(path):
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        with np.load(self.path) as data:
            ids = np.asarray(data["ids"], dtype=np.int64)
            vectors = np.asarray(data["vectors"], dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise ValueError("Exact index dimension does not match the provider")
        self._ids = [int(item) for item in ids]
        self._vectors = vectors

    def _save(self) -> None:
        if not self.path:
            return
        dirname = os.path.dirname(self.path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        temporary = f"{self.path}.{uuid.uuid4().hex}.tmp.npz"
        try:
            np.savez(
                temporary,
                ids=np.asarray(self._ids, dtype=np.int64),
                vectors=self._vectors,
            )
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _append(self, vectors: np.ndarray, ids: list[int]) -> None:
        self._vectors = np.vstack([self._vectors, vectors])
        self._ids.extend(int(item) for item in ids)

    def _validate(self, vectors: np.ndarray) -> None:
        if vectors.ndim != 2:
            raise ValueError(f"向量必须是二维数组, 当前维度: {vectors.ndim}")
        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
            )

    async def insert(self, vector: np.ndarray, id: int) -> None:
        matrix = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        self._validate(matrix)
        self._append(matrix, [id])
        self._save()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        matrix = np.asarray(vectors, dtype=np.float32)
        self._validate(matrix)
        self._append(matrix, ids)
        self._save()

    async def search(self, vector: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        query = np.asarray(vector, dtype=np.float32).ravel()
        if query.shape[0] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {query.shape[0]}",
            )
        if not self._ids or k <= 0:
            empty = np.full((1, max(k, 0)), -1, dtype=np.int64)
            return np.full((1, max(k, 0)), np.inf, dtype=np.float32), empty

        # Squared L2 distances keep the shared ``retrieve()`` normalization
        # (``1 - distance / 2``) consistent with the FAISS backend.
        distances = np.square(self._vectors - query).sum(axis=1)
        order = np.argsort(distances, kind="stable")[:k]
        indices = np.array([[self._ids[i] for i in order]], dtype=np.int64)
        return distances[order].reshape(1, -1).astype(np.float32), indices

    async def delete(self, ids: list[int]) -> None:
        remove = {int(item) for item in ids}
        if not remove:
            return
        keep = [i for i, item in enumerate(self._ids) if item not in remove]
        self._ids = [self._ids[i] for i in keep]
        self._vectors = self._vectors[keep] if keep else self._vectors[:0]
        self._save()

    async def save_index(self) -> None:
        self._save()


class ExactVecDB(FaissVecDB):
    """A ``VectorStore`` backend that needs no FAISS installation.

    It reuses ``FaissVecDB``'s document storage, validation, and rollback, and
    only swaps the vector index for a dependency-free NumPy implementation via
    ``_create_embedding_storage``.
    """

    def _create_embedding_storage(
        self,
        dimension: int,
        index_store_path: str,
    ) -> ExactEmbeddingStorage:
        return ExactEmbeddingStorage(dimension, index_store_path)
