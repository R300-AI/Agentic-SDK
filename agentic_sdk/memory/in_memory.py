from __future__ import annotations

import math
import re
import time

from agentic_sdk.memory.protocol import MemoryEntry, MemorySearchResult


class InMemoryStore:
    def __init__(self) -> None:
        self._entries: list[MemoryEntry] = []

    def append(self, entry: MemoryEntry) -> None:
        self._entries.append(entry)

    def clear(self, workflow_name: str | None = None) -> None:
        if workflow_name is None:
            self._entries.clear()
            return
        self._entries = [entry for entry in self._entries if entry.workflow_name != workflow_name]

    def all_for_workflow(self, workflow_name: str) -> list[MemoryEntry]:
        return [entry for entry in self._entries if entry.workflow_name == workflow_name]

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
    ) -> list[MemorySearchResult]:
        now = time.time()
        terms = _tokenize(query_text) if query_text else set()
        results: list[MemorySearchResult] = []
        for entry in self.all_for_workflow(workflow_name):
            if query_embedding and entry.embedding:
                similarity = _cosine(query_embedding, entry.embedding)
            elif terms:
                similarity = _jaccard(terms, _tokenize(entry.content))
            else:
                similarity = 0.0
            recency = _recency(entry.last_accessed_at, now)
            score = similarity_weight * similarity + recency_weight * recency + importance_weight * entry.importance
            results.append(
                MemorySearchResult(
                    entry=entry,
                    score=score,
                    similarity=similarity,
                    recency=recency,
                    importance=entry.importance,
                )
            )
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"\W+", text.lower()) if token}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(left * right for left, right in zip(a, b))
    left_norm = math.sqrt(sum(value * value for value in a))
    right_norm = math.sqrt(sum(value * value for value in b))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _recency(last_accessed_at: float, now: float, half_life_sec: float = 86400.0) -> float:
    elapsed = max(0.0, now - last_accessed_at)
    return math.pow(0.5, elapsed / half_life_sec)