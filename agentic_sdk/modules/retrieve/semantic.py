from __future__ import annotations

from typing import Protocol

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class SemanticRetrieve:
    name = "retrieve"

    def __init__(
        self,
        top_k: int = 3,
        embedder: Embedder | None = None,
        knowledge_base=None,
        vision_query=None,
    ) -> None:
        self._top_k = top_k
        self._embedder = embedder
        self._knowledge_base = knowledge_base
        self._vision_query = vision_query

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        query = str(state.lookup("query") or state.lookup("perceived_input") or state.user_message)
        sections: list[str] = []
        metadata: dict = {}
        if self._vision_query is not None and state.attachments:
            rewritten = self._vision_query(query, state.attachments)
            metadata["vision_augmented"] = bool(rewritten and rewritten != query)
            if rewritten:
                query = rewritten
        if self._knowledge_base is not None:
            hits = self._knowledge_base.search(query, top_k=self._top_k)
            metadata["kb_hit_count"] = len(hits)
            if hits:
                sections.append("\n".join(str(hit) for hit in hits))
        if state.memory_store is not None:
            query_embedding = self._embedder.embed(query) if self._embedder else None
            results = state.memory_store.search(
                workflow_name=state.workflow_name,
                query_text=query,
                query_embedding=query_embedding,
                top_k=self._top_k,
            )
            metadata["memory_hit_count"] = len(results)
            if results:
                sections.append("\n".join(result.entry.content for result in results))
        snippet = "\n\n".join(sections) if sections else "No matching memory or knowledge entries."
        metadata["source"] = "semantic_retrieve"
        return ModuleOutput(
            next_module="action",
            payload={"retrieved_snippet": snippet, "latest_retrieved_content": snippet},
            context_updates=[ContextEntry(type=ContextEntryType.RETRIEVED, content=snippet, metadata=metadata)],
        )