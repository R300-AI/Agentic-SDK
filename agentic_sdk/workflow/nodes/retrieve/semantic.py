"""M6-2 — 語意 Retrieve:從 Memory Stream 以 cosine + 時近性 + 重要性加權撈回。

設計:
- 預設使用 TF-IDF 風格的 Jaccard 詞集相似度(MemoryStore 內建),零外部依賴
- 若安裝了 sentence-transformers,可注入 embedder 升級為語意向量
- 沒有 Memory Store 時退回 stub 行為(保持 PoC 階段 retrieve 可獨立跑通)

下一站固定為 "plan",讓 Plan 依新撈回的上下文重新決策。
"""

from __future__ import annotations

from typing import Protocol

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


class Embedder(Protocol):
    """可插拔 embedder 介面;若注入則 Retrieve 使用向量語意相似度。"""

    def embed(self, text: str) -> list[float]: ...


class SemanticRetrieve:
    name = "retrieve"

    def __init__(
        self,
        top_k: int = 3,
        similarity_weight: float = 0.5,
        recency_weight: float = 0.3,
        importance_weight: float = 0.2,
        embedder: Embedder | None = None,
    ) -> None:
        self._top_k = top_k
        self._similarity_weight = similarity_weight
        self._recency_weight = recency_weight
        self._importance_weight = importance_weight
        self._embedder = embedder

    def __call__(self, state: WorkflowState) -> NodeOutput:
        store = state.memory_store
        if store is None:
            snippet = (
                "(no memory store) MemoryStore 未注入,Retrieve 退回空結果。"
                "請在 Workflow.from_config(..., memory_store=MemoryStore(...)) 注入。"
            )
            entry = ContextEntry(
                type=ContextEntryType.RETRIEVED,
                content=snippet,
                metadata={"hit_count": 0, "source": "no_memory"},
            )
            return NodeOutput(
                next_node="plan",
                payload={"retrieved_snippet": snippet},
                context_updates=[entry],
            )

        query_text = state.user_message
        query_embedding = self._embedder.embed(query_text) if self._embedder else None

        results = store.search(
            workflow_name=state.workflow_name,
            query_text=query_text,
            query_embedding=query_embedding,
            top_k=self._top_k,
            similarity_weight=self._similarity_weight,
            recency_weight=self._recency_weight,
            importance_weight=self._importance_weight,
        )

        if not results:
            snippet = "(memory empty) Memory Stream 中尚無此 workflow 的紀錄。"
            metadata = {"hit_count": 0, "source": "memory_stream"}
        else:
            lines = [f"- [{r.entry.entry_type}] {r.entry.content}" for r in results]
            snippet = "從 Memory Stream 撈回 top-{} 條目:\n{}".format(len(results), "\n".join(lines))
            metadata = {
                "hit_count": len(results),
                "source": "memory_stream",
                "scores": [
                    {
                        "entry_id": r.entry.entry_id,
                        "score": r.score,
                        "similarity": r.similarity,
                        "recency": r.recency,
                        "importance": r.importance,
                    }
                    for r in results
                ],
            }

        entry = ContextEntry(
            type=ContextEntryType.RETRIEVED,
            content=snippet,
            metadata=metadata,
        )

        return NodeOutput(
            next_node="plan",
            payload={"retrieved_snippet": snippet},
            context_updates=[entry],
        )
