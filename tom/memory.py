from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryStore:
    """Small local JSONL memory store; replaceable by vector/graph backends."""

    def __init__(self, directory: str = ".tom-data") -> None:
        self.path = Path(directory) / "memory.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        record = {"conversation_id": conversation_id, "role": role, "content": content, "metadata": metadata or {}}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("conversation_id") == conversation_id:
                rows.append(item)
        return rows[-limit:]
