from agentic_sdk.workflow.module import ModuleOutput, WorkflowState
from agentic_sdk.workflow.modules.retrieve.keyword import KeywordRetrieve
from agentic_sdk.workflow.modules.retrieve.semantic import SemanticRetrieve


class HybridRetrieve(SemanticRetrieve):
    def __init__(self, items: list[dict] | None = None, fallback: str = "沒有命中任何條目。", **kwargs) -> None:
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
        snippets = [snippet for snippet in (keyword_snippet, semantic_snippet) if snippet]
        combined_snippet = "\n\n".join(snippets)
        payload = dict(semantic_output.get("payload", {}))
        payload.update(
            {
                "retrieved_items": keyword_hits,
                "retrieved_snippet": combined_snippet,
                "latest_retrieved_content": combined_snippet,
            }
        )
        return ModuleOutput(
            next_module=semantic_output.get("next_module"),
            payload=payload,
            context_updates=[*keyword_output.get("context_updates", []), *semantic_output.get("context_updates", [])],
        )