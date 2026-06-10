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
from agentic_sdk.knowledge import KnowledgeBase
from agentic_sdk.workflow.node import NodeOutput, WorkflowState
from agentic_sdk.workflow.nodes.retrieve.vision_query import VisionQueryBuilder


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
        knowledge_base: KnowledgeBase | None = None,
        vision_query: VisionQueryBuilder | None = None,
    ) -> None:
        self._top_k = top_k
        self._similarity_weight = similarity_weight
        self._recency_weight = recency_weight
        self._importance_weight = importance_weight
        self._embedder = embedder
        self._knowledge_base = knowledge_base
        self._vision_query = vision_query

    def __call__(self, state: WorkflowState) -> NodeOutput:
        query_text = state.user_message
        sections: list[str] = []
        metadata: dict = {}
        sources: list[str] = []

        # 多模態查詢改寫：若 state 帶 image 附件且有 vision_query，
        # 先讓圖文模型把（文字+圖）摘成關鍵字，再丟給 KB / Memory 搜尋。
        if self._vision_query is not None and state.attachments:
            try:
                rewritten = self._vision_query(query_text, state.attachments)
            except Exception:
                rewritten = query_text
            if rewritten and rewritten.strip() and rewritten != query_text:
                metadata["vision_augmented"] = True
                metadata["vision_query_text"] = rewritten
                query_text = rewritten
            else:
                metadata["vision_augmented"] = False

        # KB 優先：靜態領域知識（non-parametric memory）
        if self._knowledge_base is not None:
            kb_hits = self._knowledge_base.search(query_text, top_k=self._top_k)
            metadata["kb_name"] = self._knowledge_base.name
            metadata["kb_hit_count"] = len(kb_hits)
            metadata["kb_scores"] = [{"id": h.entry.id, "score": h.score} for h in kb_hits]
            if kb_hits:
                lines = [f"- 【{h.entry.title}】{h.entry.content}" for h in kb_hits]
                sections.append("從知識庫撈回 top-{} 條目:\n{}".format(len(kb_hits), "\n".join(lines)))
                sources.append("knowledge_base")

        # Memory Stream：執行中累積的對話記憶（recall storage）
        store = state.memory_store
        memory_results = []
        if store is not None:
            query_embedding = self._embedder.embed(query_text) if self._embedder else None
            memory_results = store.search(
                workflow_name=state.workflow_name,
                query_text=query_text,
                query_embedding=query_embedding,
                top_k=self._top_k,
                similarity_weight=self._similarity_weight,
                recency_weight=self._recency_weight,
                importance_weight=self._importance_weight,
            )
            metadata["scores"] = [
                {
                    "entry_id": r.entry.entry_id,
                    "score": r.score,
                    "similarity": r.similarity,
                    "recency": r.recency,
                    "importance": r.importance,
                }
                for r in memory_results
            ]
            if memory_results:
                lines = [f"- [{r.entry.entry_type}] {r.entry.content}" for r in memory_results]
                sections.append("從對話記憶撈回 top-{} 條目:\n{}".format(len(memory_results), "\n".join(lines)))
                sources.append("memory_stream")

        # source 標籤：向下相容單一字串
        if sources:
            metadata["source"] = "+".join(sources)
        elif store is None and self._knowledge_base is None:
            metadata["source"] = "no_memory"
        else:
            metadata["source"] = "memory_stream" if store is not None else "knowledge_base"

        metadata["hit_count"] = len(memory_results) + metadata.get("kb_hit_count", 0)

        if not sections:
            if self._knowledge_base is None and store is None:
                snippet = (
                    "(no source) 未注入 KnowledgeBase 或 MemoryStore，Retrieve 退回空結果。"
                )
            else:
                snippet = "(no hit) 知識庫與對話記憶皆未命中此查詢。"
        else:
            snippet = "\n\n".join(sections)

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
