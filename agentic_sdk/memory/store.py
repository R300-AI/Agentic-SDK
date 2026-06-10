"""M6-1 — Memory Stream:SQLite 後端的跨 run 記憶層。

對齊 [R07] Generative Agents 的 Memory Stream 概念,以 workflow 名稱為隔離單位:
同一 workflow 的不同 run 共享記憶,不同 workflow 互不干擾。

Schema 刻意極簡(PoC 階段):一張表 + workflow_name 索引。
embedding 以 little-endian float32 序列化為 BLOB;為 None 時走純文字 fallback。

語意查詢結合三項分數,對齊 Generative Agents §4.1:
- similarity:embedding cosine,無 embedding 時為 0
- recency:以 last_accessed_at 與當前時間差套用半衰指數
- importance:寫入時由節點宣告(預設 1.0)
"""

from __future__ import annotations

import json
import math
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MemoryEntry:
    workflow_name: str
    entry_type: str
    content: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None
    importance: float = 1.0
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)


@dataclass
class ScoredMemory:
    entry: MemoryEntry
    score: float
    similarity: float
    recency: float
    importance: float


class MemoryStore:
    """SQLite-backed Memory Stream;以 workflow_name 為隔離單位。"""

    def __init__(self, db_path: str | Path = ".memory/store.sqlite") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _init_schema(self) -> None:
        with self._connect() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    entry_id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    embedding BLOB,
                    importance REAL NOT NULL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow ON memory_entries(workflow_name)"
            )

    def append(self, entry: MemoryEntry) -> None:
        emb_blob = _pack_embedding(entry.embedding) if entry.embedding else None
        with self._connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO memory_entries"
                " (entry_id, workflow_name, entry_type, content, metadata,"
                "  embedding, importance, created_at, last_accessed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    entry.entry_id,
                    entry.workflow_name,
                    entry.entry_type,
                    entry.content,
                    json.dumps(entry.metadata, ensure_ascii=False),
                    emb_blob,
                    entry.importance,
                    entry.created_at,
                    entry.last_accessed_at,
                ),
            )

    def all_for_workflow(self, workflow_name: str) -> list[MemoryEntry]:
        with self._connect() as c:
            rows = c.execute(
                "SELECT entry_id, workflow_name, entry_type, content, metadata,"
                " embedding, importance, created_at, last_accessed_at"
                " FROM memory_entries WHERE workflow_name = ? ORDER BY created_at DESC",
                (workflow_name,),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def clear_workflow(self, workflow_name: str) -> int:
        with self._connect() as c:
            cur = c.execute(
                "DELETE FROM memory_entries WHERE workflow_name = ?", (workflow_name,)
            )
            return cur.rowcount

    def search(
        self,
        workflow_name: str,
        *,
        query_text: str = "",
        query_embedding: list[float] | None = None,
        top_k: int = 3,
        recency_weight: float = 0.3,
        importance_weight: float = 0.2,
        similarity_weight: float = 0.5,
        half_life_sec: float = 86_400.0,
    ) -> list[ScoredMemory]:
        entries = self.all_for_workflow(workflow_name)
        if not entries:
            return []

        now = time.time()
        scored: list[ScoredMemory] = []
        query_terms = _tokenize(query_text) if query_text else set()

        for e in entries:
            if query_embedding and e.embedding:
                sim = _cosine(query_embedding, e.embedding)
            elif query_terms:
                sim = _jaccard(query_terms, _tokenize(e.content))
            else:
                sim = 0.0

            recency = _recency_score(e.last_accessed_at, now, half_life_sec)
            score = (
                similarity_weight * sim
                + recency_weight * recency
                + importance_weight * e.importance
            )
            scored.append(
                ScoredMemory(
                    entry=e,
                    score=score,
                    similarity=sim,
                    recency=recency,
                    importance=e.importance,
                )
            )

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]


def _pack_embedding(emb: list[float]) -> bytes:
    return struct.pack(f"{len(emb)}f", *emb)


def _unpack_embedding(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _row_to_entry(row: tuple) -> MemoryEntry:
    return MemoryEntry(
        entry_id=row[0],
        workflow_name=row[1],
        entry_type=row[2],
        content=row[3],
        metadata=json.loads(row[4]) if row[4] else {},
        embedding=_unpack_embedding(row[5]),
        importance=row[6],
        created_at=row[7],
        last_accessed_at=row[8],
    )


def _tokenize(text: str) -> set[str]:
    import re

    return {t for t in re.split(r"\W+", text.lower()) if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _recency_score(last_accessed_at: float, now: float, half_life_sec: float) -> float:
    if half_life_sec <= 0:
        return 1.0
    elapsed = max(0.0, now - last_accessed_at)
    return math.pow(0.5, elapsed / half_life_sec)
