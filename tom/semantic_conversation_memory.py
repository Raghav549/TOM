from __future__ import annotations

from typing import Any


class SemanticConversationMemory:
    """Semantic retrieval over TOM's durable conversation JSONL history.

    The existing JSONL memory remains the source of truth. Embeddings are optional;
    lexical matching is used when the embedding dependency/model is unavailable.
    """

    def __init__(self, memory: Any, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.memory = memory
        self.model_name = model_name
        self._model: Any | None = None

    def _load(self) -> Any | None:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return None
        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception:  # noqa: BLE001 - optional model boundary
            return None
        return self._model

    @staticmethod
    def _text(item: dict[str, Any]) -> str:
        return str(item.get("content", ""))

    def search(self, conversation_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        rows = list(self.memory.recent(conversation_id, limit=200))
        if not rows:
            return []
        model = self._load()
        if model is None:
            terms = {part.casefold() for part in query.split() if len(part) > 2}
            ranked = []
            for row in rows:
                text = self._text(row).casefold()
                score = sum(1 for term in terms if term in text)
                if score:
                    ranked.append((score, row))
            ranked.sort(key=lambda pair: pair[0], reverse=True)
            return [row for _, row in ranked[: max(1, min(limit, 20))]]

        import numpy as np

        matrix = np.asarray(model.encode([self._text(row) for row in rows], normalize_embeddings=True), dtype=np.float32)
        query_vec = np.asarray(model.encode(query, normalize_embeddings=True), dtype=np.float32)
        scores = matrix @ query_vec
        ranked = sorted(zip(rows, scores.tolist()), key=lambda pair: pair[1], reverse=True)
        return [row for row, score in ranked[: max(1, min(limit, 20))] if float(score) >= 0.25]
