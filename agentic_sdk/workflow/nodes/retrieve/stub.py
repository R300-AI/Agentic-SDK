"""Retrieve stub baseline — PoC 階段不引入向量索引依賴。

以內建關鍵字字典回傳固定片段;真正的 RAG(chromadb + sentence-transformers)
留給 Phase 5 的 `vanilla_rag.py`,與此檔並列、共享 Node 契約。

下一站固定為 "plan",讓 Plan 節點以新取回的上下文重新決策(對應 ReAct 的
Thought→Action→Observation→Thought 迴環)。
"""

from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


_DEFAULT_CORPUS: dict[str, str] = {
    "tsip": "TSiP 是工研院主導的國產 AI 晶片落地藍圖,涵蓋 SLA 認證與資源調度兩條主軸。",
    "agentic": "Agentic SDK 提供五節點工作流(Perceive/Plan/Retrieve/Reflect/Action)並對外維持 OpenAI 相容 API。",
    "model card": "Model Card 由 amd-ryzen-ai-benchmark 產出,涵蓋 TTFT、Peak Memory、Soak Test 等 SLA 履歷。",
}

_FALLBACK_SNIPPET = (
    "(stub retrieve)目前知識庫無命中項目。Phase 5 將切換到 vanilla_rag(chromadb + "
    "sentence-transformers)後即會回傳真實向量檢索結果。"
)


class StubRetrieve:
    name = "retrieve"

    def __init__(self, corpus: dict[str, str] | None = None) -> None:
        self._corpus = corpus or _DEFAULT_CORPUS

    def __call__(self, state: WorkflowState) -> NodeOutput:
        query = state.user_message.lower()
        hits = [snippet for keyword, snippet in self._corpus.items() if keyword in query]
        snippet = hits[0] if hits else _FALLBACK_SNIPPET

        entry = ContextEntry(
            type=ContextEntryType.RETRIEVED,
            content=snippet,
            metadata={"hit_count": len(hits), "source": "stub"},
        )

        return NodeOutput(
            next_node="plan",
            payload={"retrieved_snippet": snippet},
            context_updates=[entry],
        )
