from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


class PassThroughRetrieve:
    name = "retrieve"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = str(state.lookup("perceived_input") or state.lookup("query") or state.user_message).strip()
        return ModuleOutput(
            next_module="action",
            payload={
                "retrieved_items": [],
                "retrieved_snippet": content,
                "latest_retrieved_content": content,
            },
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.RETRIEVED,
                    content=content,
                    metadata={"source": "pass_through_retrieve"},
                )
            ],
        )