from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.node import NodeOutput, WorkflowState


class InputPerceive:
    name = "perceive"

    def __call__(self, state: WorkflowState) -> NodeOutput:
        content = state.user_message.strip()
        return NodeOutput(
            next_node="retrieve",
            payload={
                "perceived_input": content,
                "query": content,
            },
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.PERCEIVED,
                    content=content,
                    metadata={"source": "input_perceive"},
                )
            ],
        )