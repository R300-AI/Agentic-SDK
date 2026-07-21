from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


class KeywordRetrieve:
    name = "retrieve"

    def __init__(self, items: list[dict] | None = None, fallback: str = "No matching entries.") -> None:
        self._items = items or []
        self._fallback = fallback

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        query = str(state.lookup("query") or state.lookup("perceived_input") or state.user_message).lower()
        hits: list[dict] = []
        for item in self._items:
            keywords = [str(keyword).lower() for keyword in item.get("keywords", [])]
            if any(keyword and keyword in query for keyword in keywords):
                hits.append(item)
        contents = [str(item.get("content", "")) for item in hits if item.get("content")]
        snippet = "\n".join(contents) if contents else self._fallback
        return ModuleOutput(
            next_module="action",
            payload={
                "query": query,
                "retrieved_items": hits,
                "retrieved_snippet": snippet,
                "latest_retrieved_content": snippet,
            },
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.RETRIEVED,
                    content=snippet,
                    metadata={"hit_count": len(hits), "source": "keyword_retrieve"},
                )
            ],
        )