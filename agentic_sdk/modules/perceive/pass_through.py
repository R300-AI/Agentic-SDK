from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState


class PassThroughPerceive:
    name = "perceive"

    def __init__(self, input_label: str = "") -> None:
        self._input_label = input_label

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = state.latest_user_message().strip()
        metadata = {"source": "pass_through_perceive"}
        if self._input_label:
            metadata["input_label"] = self._input_label
        return ModuleOutput(
            next_module="retrieve",
            payload={"perceived_input": content, "query": content},
            context_updates=[ContextEntry(type=ContextEntryType.PERCEIVED, content=content, metadata=metadata)],
        )