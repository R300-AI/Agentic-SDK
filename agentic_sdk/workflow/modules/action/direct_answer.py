from __future__ import annotations

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.module import ModuleOutput, WorkflowState


class DirectAnswerAction:
    name = "action"

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = str(state.lookup("latest_retrieved_content") or "沒有命中任何條目。")
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": "direct-answer"}
        return ModuleOutput(
            next_module=None,
            payload={"latest_final_message": content},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.ACTION_RESULT,
                    content=content,
                    metadata={"ok": True, "model": "direct-answer"},
                )
            ],
        )