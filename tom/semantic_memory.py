from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .memory_store import MemoryItem, MemoryStore


@dataclass(frozen=True)
class SemanticHit:
    item: MemoryItem
    score: float


class SemanticMemory:
    """Durable-memory search with optional sentence-transformers embeddings.

    The SQLite store remains the source of truth. Embeddings are computed on
    demand so the feature degrades cleanly to the existing lexical store when
    the optional model is not installed.
    """

    def __init__(self, store: MemoryStore | None = None, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.store = store or MemoryStore()
        self.model_name = model_name
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Install TOM semantic memory with the memory extra") from exc
        self._model = SentenceTransformer(self.model_name)
        return self._model

    @staticmethod
    def _text(item: MemoryItem) -> str:
        return f"{item.kind}: {item.key}\n{item.value}"

    def search(self, query: str, *, kind: str | None = None, limit: int = 8) -> list[SemanticHit]:
        if not query.strip():
            return []
        model = self._load()
        candidates = self.store.search(kind=kind, limit=100)
        if not candidates:
            return []
        import numpy as np

        query_vec = np.asarray(model.encode(query, normalize_embeddings=True), dtype=np.float32)
        matrix = np.asarray(model.encode([self._text(item) for item in candidates], normalize_embeddings=True), dtype=np.float32)
        scores = matrix @ query_vec
        ranked = sorted(zip(candidates, scores.tolist()), key=lambda pair: pair[1], reverse=True)
        return [SemanticHit(item, float(score)) for item, score in ranked[: max(1, min(limit, 50))]]
