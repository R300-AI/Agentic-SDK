from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState


class PassThroughPerceive:
    name = "perceive"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = state.user_message.strip()
        return ModuleOutput(
            next_module="retrieve",
            payload={
                "perceived_input": content,
                "query": content,
            },
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.PERCEIVED,
                    content=content,
                    metadata={"source": "pass_through_perceive"},
                )
            ],
        )