from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


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

    @abstractmethod
    def __call__(self, state: WorkflowState) -> ModuleOutput:
        """Search, then hand the result back through :meth:`_retrieved`."""

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
