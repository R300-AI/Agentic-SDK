from __future__ import annotations

from agentic_sdk.core import ModuleOutput, WorkflowState
from agentic_sdk.modules.retrieve.keyword import KeywordRetrieve
from agentic_sdk.modules.retrieve.semantic import SemanticRetrieve


class HybridRetrieve(SemanticRetrieve):
    def __init__(self, items: list[dict] | None = None, fallback: str = "No matching entries.", **kwargs) -> None:
        super().__init__(**kwargs)
        self._keyword = KeywordRetrieve(items=items, fallback=fallback)

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        semantic_output = super().__call__(state)
        keyword_output = self._keyword(state)
        keyword_hits = keyword_output.get("payload", {}).get("retrieved_items") or []
        if not keyword_hits:
            return semantic_output
        keyword_snippet = str(keyword_output.get("payload", {}).get("latest_retrieved_content", ""))
        semantic_snippet = str(semantic_output.get("payload", {}).get("retrieved_snippet", ""))
        combined = "\n\n".join(snippet for snippet in (keyword_snippet, semantic_snippet) if snippet)
        payload = dict(semantic_output.get("payload", {}))
        payload.update(
            {
                "retrieved_items": keyword_hits,
                "retrieved_snippet": combined,
                "latest_retrieved_content": combined,
            }
        )
        return ModuleOutput(
            next_module=semantic_output.get("next_module"),
            payload=payload,
            context_updates=[*keyword_output.get("context_updates", []), *semantic_output.get("context_updates", [])],
        )