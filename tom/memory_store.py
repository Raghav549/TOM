from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class MemoryItem:
    id: str
    kind: str
    key: str
    value: object
    confidence: float
    source: str
    created_at: str
    updated_at: str
    expires_at: str | None = None


class MemoryStore:
    """Small typed SQLite memory store with provenance and expiry."""

    def __init__(self, path: str | Path = "tom_memory.sqlite3") -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )"""
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_mem_kind_key ON memories(kind, key)")
        self._db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def put(
        self,
        *,
        kind: str,
        key: str,
        value: object,
        source: str,
        confidence: float = 1.0,
        expires_at: str | None = None,
    ) -> MemoryItem:
        if not kind or not key or not source:
            raise ValueError("kind, key and source are required")
        confidence = max(0.0, min(1.0, confidence))
        now = self._now()
        item = MemoryItem(uuid.uuid4().hex, kind, key, value, confidence, source, now, now, expires_at)
        self._db.execute(
            "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.kind,
                item.key,
                json.dumps(item.value, ensure_ascii=False),
                item.confidence,
                item.source,
                item.created_at,
                item.updated_at,
                item.expires_at,
            ),
        )
        self._db.commit()
        return item

    def latest(self, kind: str, key: str) -> MemoryItem | None:
        row = self._db.execute(
            "SELECT id, kind, key, value_json, confidence, source, created_at, updated_at, expires_at FROM memories WHERE kind=? AND key=? ORDER BY updated_at DESC LIMIT 1",
            (kind, key),
        ).fetchone()
        if not row:
            return None
        item = self._from_row(row)
        if item.expires_at and item.expires_at <= self._now():
            return None
        return item

    def search(self, kind: str | None = None, text: str = "", limit: int = 20) -> list[MemoryItem]:
        clauses: list[str] = []
        args: list[object] = []
        if kind:
            clauses.append("kind=?")
            args.append(kind)
        if text:
            clauses.append("(key LIKE ? OR value_json LIKE ?)")
            pattern = f"%{text}%"
            args.extend([pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT id, kind, key, value_json, confidence, source, created_at, updated_at, expires_at FROM memories {where} ORDER BY updated_at DESC LIMIT ?",
            (*args, max(1, min(limit, 100))),
        ).fetchall()
        now = self._now()
        return [self._from_row(row) for row in rows if not row[8] or row[8] > now]

    def _from_row(self, row: tuple[object, ...]) -> MemoryItem:
        return MemoryItem(
            id=str(row[0]),
            kind=str(row[1]),
            key=str(row[2]),
            value=json.loads(str(row[3])),
            confidence=float(row[4]),
            source=str(row[5]),
            created_at=str(row[6]),
            updated_at=str(row[7]),
            expires_at=str(row[8]) if row[8] else None,
        )

    def close(self) -> None:
        self._db.close()
