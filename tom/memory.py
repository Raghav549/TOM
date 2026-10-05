from __future__ import annotations

import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Any


class MemoryStore:
    """Durable JSONL conversation memory with optional semantic retrieval."""

    def __init__(self, directory: str = ".tom-data") -> None:
        self.path = Path(directory) / "memory.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_query: dict[str, str] = {}
        self._semantic_model: Any | None = None
        self._semantic_disabled = False

    def add(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        record = {"conversation_id": conversation_id, "role": role, "content": content, "metadata": metadata or {}}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        if role == "user" and content.strip():
            self._last_query[conversation_id] = content.strip()

    def recent(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        if limit <= 0:
            return []
        retained: deque[dict[str, Any]] = deque(maxlen=max(limit, 2000))
        with self.path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    logging.getLogger(__name__).warning("Ignoring corrupt memory record line=%d", number)
                    continue
                if isinstance(item, dict) and item.get("conversation_id") == conversation_id:
                    retained.append(item)
        rows = list(retained)
        recent = rows[-limit:]
        if os.getenv("TOM_SEMANTIC_MEMORY_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
            return recent
        query = self._last_query.get(conversation_id, "")
        if not query or len(rows) <= len(recent):
            return recent
        semantic = self._semantic_retrieve(query, rows[:-limit], max(0, min(6, limit // 2)))
        if not semantic:
            return recent
        seen = {id(item) for item in semantic}
        return semantic + [item for item in recent if id(item) not in seen]

    def _semantic_retrieve(self, query: str, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not candidates or limit <= 0:
            return []
        if self._semantic_disabled:
            return self._lexical_retrieve(query, candidates, limit)
        try:
            if self._semantic_model is None:
                from sentence_transformers import SentenceTransformer
                self._semantic_model = SentenceTransformer(
                    os.getenv("TOM_SEMANTIC_MEMORY_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
                    local_files_only=True,
                )
            import numpy as np
            texts = [str(item.get("content", "")) for item in candidates]
            matrix = np.asarray(self._semantic_model.encode(texts, normalize_embeddings=True), dtype=np.float32)
            query_vec = np.asarray(self._semantic_model.encode(query, normalize_embeddings=True), dtype=np.float32)
            scores = matrix @ query_vec
            ranked = sorted(zip(candidates, scores.tolist(), strict=True), key=lambda pair: pair[1], reverse=True)
            return [item for item, score in ranked[:limit] if float(score) >= 0.25]
        except Exception:  # noqa: BLE001 - optional semantic backend
            self._semantic_disabled = True
            return self._lexical_retrieve(query, candidates, limit)

    @staticmethod
    def _lexical_retrieve(query: str, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        terms = {part.casefold() for part in query.split() if len(part) > 2}
        if not terms:
            return []
        ranked = []
        for item in candidates:
            text = str(item.get("content", "")).casefold()
            score = sum(1 for term in terms if term in text)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in ranked[:limit]]
