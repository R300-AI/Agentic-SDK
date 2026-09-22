from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.defaults import SEMANTIC_RETRIEVE_DEFAULT_TOP_K


class BaseRetrieve(ABC):
    """What every retrieve module hands back, in one place.

    Retrieve modules differ in how they search external sources. What they
    hand back does not vary: the passage they found, that same passage under
    the key the next module reads, and one retrieved entry on the context
    saying which module produced it. Before this class, that shape was written
    out once per module, so a fourth module had to copy all three of them to be
    read correctly by anything downstream.

    A subclass names itself in ``produced_by`` and calls :meth:`_retrieved`
    with whatever it found. ``produced_by`` has no default: a subclass that
    forgets it fails rather than labelling its entry with someone else's name.
    """

    name = "retrieve"
    produced_by: str
    # How many remembered passages one lookup brings back.
    memory_top_k = SEMANTIC_RETRIEVE_DEFAULT_TOP_K

    @abstractmethod
    def __call__(self, state: WorkflowState) -> ModuleOutput:
        """Search, then hand the result back through :meth:`_retrieved`."""

    # --- what this agent already knows ---------------------------------

    def _memory_hits(self, state: WorkflowState, query: str) -> list[Any]:
        """Look the query up in what earlier conversations left behind.

        Every retrieve module can do this, because memory is not one of
        the things a person picks between — it is what this agent
        already knows. What the modules differ in is the external source
        they search. A module with a better way to match, such as one
        holding an embedder, overrides this.
        """
        memory = state.cross_context_memory()
        if memory is None:
            return []
        return memory.search(
            workflow_name=state.workflow_name,
            query_text=query,
            top_k=self.memory_top_k,
        )

    def _with_memory(
        self, sections: list[str], state: WorkflowState, query: str
    ) -> "tuple[list[str], int]":
        """Add what is remembered to what this module found."""
        hits = self._memory_hits(state, query)
        if not hits:
            return sections, 0
        return [*sections, format_memory_hits(hits)], len(hits)

    def _retrieved(
        self,
        snippet: str,
        *,
        query: str | None = None,
        items: list[dict] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModuleOutput:
        """Shape one search result.

        ``query`` and ``items`` are left out of the payload entirely when a
        module has nothing to put there. A module that collects hits and found
        none reports an empty list; a module that never collects them at all
        reports nothing, and a reader can tell the two apart.

        The producing module's name is written last, so a caller's metadata
        cannot overwrite it.
        """
        payload: dict[str, Any] = {}
        if query is not None:
            payload["query"] = query
        if items is not None:
            payload["retrieved_items"] = items
        payload["retrieved_snippet"] = snippet
        payload["latest_retrieved_content"] = snippet

        entry_metadata = dict(metadata or {})
        entry_metadata["source"] = self.produced_by

        return ModuleOutput(
            next_module="plan",
            payload=payload,
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.RETRIEVED,
                    content=snippet,
                    metadata=entry_metadata,
                )
            ],
        )


def format_memory_hits(results: list[Any]) -> str:
    lines = ["Memory hits:"]
    for index, result in enumerate(results, start=1):
        entry = getattr(result, "entry", None)
        if entry is None:
            lines.append(f"{index}. {result}")
            continue
        role = str(getattr(entry, "role", "") or "memory")
        content = str(getattr(entry, "content", "") or "")
        lines.append(f"{index}. {role}: {content}")
    return "\n".join(lines)
