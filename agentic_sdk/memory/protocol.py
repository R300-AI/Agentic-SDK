from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class MemoryEntry:
    content: str
    workflow_name: str = "default"
    entry_type: str = "memory"
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    importance: float = 1.0
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)


@dataclass
class MemorySearchResult:
    entry: MemoryEntry
    score: float
    similarity: float = 0.0
    recency: float = 0.0
    importance: float = 0.0


class MemoryStore(Protocol):
    def append(self, entry: MemoryEntry) -> None: ...

    def search(
        self,
        workflow_name: str,
        *,
        query_text: str = "",
        query_embedding: list[float] | None = None,
        top_k: int = 3,
        similarity_weight: float = 0.5,
        recency_weight: float = 0.3,
        importance_weight: float = 0.2,
    ) -> list[MemorySearchResult]: ...