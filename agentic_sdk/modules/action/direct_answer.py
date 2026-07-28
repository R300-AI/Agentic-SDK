from __future__ import annotations

from agentic_sdk.core import ContextEntry, ContextEntryType, ModuleOutput, WorkflowState
from agentic_sdk.defaults import DEFAULT_NO_MATCHING_ENTRIES_MESSAGE, DEFAULT_RETRIEVED_CONTENT_KEY


class DirectAnswerAction:
    name = "action"

    def __init__(
        self,
        memory_key: str = DEFAULT_RETRIEVED_CONTENT_KEY,
        fallback: str = DEFAULT_NO_MATCHING_ENTRIES_MESSAGE,
        prefix: str = "",
    ) -> None:
        self._memory_key = memory_key
        self._fallback = fallback
        self._prefix = prefix

    def __call__(self, state: WorkflowState) -> ModuleOutput:
        content = f"{self._prefix}{state.lookup(self._memory_key) or self._fallback}"
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